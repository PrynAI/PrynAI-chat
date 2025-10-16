# apps/gateway-fastapi/src/features/uploads.py
from __future__ import annotations
import io, os, re, json, zipfile, html
from typing import List, Tuple, Optional, AsyncGenerator, Any

from fastapi import APIRouter, UploadFile, HTTPException, Request, File, Form
from fastapi.responses import StreamingResponse

from langgraph_sdk import get_client
from langgraph.pregel.remote import RemoteGraph
from openai import OpenAI

from src.features.websearch import ChatIn, build_langgraph_config
from src.features.profiles import ensure_profile
from src.features.transcript import append_transcript, TranscriptMessage
from src.auth.entra import AuthError

# ----------------------------- Limits & helpers ------------------------------

MAX_FILES = 5
MAX_FILE_MB = 10
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
CHUNK = 512 * 1024  # 512 KiB

# Keep the attachments context compact for TTFT/TPOT and model tokens
MAX_CHARS_PER_FILE = 12000
MAX_TOTAL_CHARS = 24000

# OCR controls (OFF by default)
OCR_BACKEND = (os.getenv("UPLOADS_OCR", "none") or "none").strip().lower()  # "none" | "tesseract"
OCR_MAX_PAGES = int(os.getenv("UPLOADS_OCR_MAX_PAGES", "10"))
OCR_DPI = int(os.getenv("UPLOADS_OCR_DPI", "180"))
OCR_LANG = os.getenv("UPLOADS_OCR_LANG", "eng")

# Allowed extensions (lowercased, with dot)
ALLOWED_EXTS = {
    # Documents & Data
    ".pdf", ".docx", ".txt", ".csv", ".pptx", ".xlsx", ".json", ".xml",
    # Images (OCR optional)
    ".png", ".jpg", ".jpeg", ".gif",
    # Code/text
    ".py", ".js", ".html", ".css", ".yaml", ".yml", ".sql", ".ipynb", ".md",
}

# Disallowed (explicit) in addition to audio/video MIME check
BLOCKED_EXTS = {".exe", ".dll", ".bin", ".dmg", ".iso", ".apk", ".msi", ".so"}
AUDIO_PREFIX = "audio/"
VIDEO_PREFIX = "video/"

def _ext(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()

async def read_limited(file: UploadFile) -> bytes:
    """Stream read an UploadFile into memory with per-file size cap. Don't touch disk."""
    total = 0
    buf = io.BytesIO()
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large. Max allowed size is: {MAX_FILE_MB} MB")
        buf.write(chunk)
    return buf.getvalue()

def _clean_text(s: str) -> str:
    # normalize newlines, collapse some whitespace
    return re.sub(r"[ \t\r]+", " ", s.replace("\r\n", "\n")).strip()

def _xml_to_text(b: bytes) -> str:
    # Brutal but effective: strip tags and unescape entities
    s = b.decode("utf-8", errors="ignore")
    s = re.sub(r"<[^>]+>", " ", s)
    return _clean_text(html.unescape(s))

# ---------- lightweight parsers (no OCR) ----------

def _try_pdf_text(b: bytes) -> Optional[str]:
    try:
        from pypdf import PdfReader  # pure python
        r = PdfReader(io.BytesIO(b))
        pages = []
        for p in r.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pass
        return _clean_text("\n".join(pages))
    except Exception:
        return None

def _try_docx_text(b: bytes) -> Optional[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            xml = z.read("word/document.xml")
        return _xml_to_text(xml)
    except Exception:
        return None

def _try_pptx_text(b: bytes) -> Optional[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            names = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            slides = []
            for n in sorted(names):
                try:
                    slides.append(_xml_to_text(z.read(n)))
                except Exception:
                    pass
        return _clean_text("\n\n".join(slides))
    except Exception:
        return None

def _try_xlsx_text(b: bytes) -> Optional[str]:
    # Light pass: pull sharedStrings and first sheet XML, strip tags
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            out = []
            if "xl/sharedStrings.xml" in z.namelist():
                out.append(_xml_to_text(z.read("xl/sharedStrings.xml")))
            for n in z.namelist():
                if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"):
                    out.append(_xml_to_text(z.read(n)))
                    break
        return _clean_text("\n\n".join(out))
    except Exception:
        return None

def _try_ipynb_text(b: bytes) -> Optional[str]:
    try:
        nb = json.loads(b.decode("utf-8", errors="ignore"))
        out = []
        for cell in nb.get("cells", []):
            src = cell.get("source", [])
            if isinstance(src, list):
                out.append("".join(src))
            elif isinstance(src, str):
                out.append(src)
        return _clean_text("\n\n".join(out))
    except Exception:
        return None

# ---------- OCR helpers (optional) ----------

def _ocr_image_tesseract(img_bytes: bytes) -> str:
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(img_bytes))
        txt = pytesseract.image_to_string(img, lang=OCR_LANG)
        return _clean_text(txt or "")
    except Exception:
        return ""

def _ocr_pdf_tesseract(b: bytes, *, max_pages: int, dpi: int) -> str:
    # Render first N pages with PyMuPDF and OCR them
    try:
        import fitz  # PyMuPDF
    except Exception:
        return ""
    out: List[str] = []
    try:
        doc = fitz.open("pdf", b)
        pages = min(len(doc), max_pages)
        for i in range(pages):
            page = doc.load_page(i)
            # Only OCR when text extraction is empty
            if (page.get_text("text") or "").strip():
                out.append(_clean_text(page.get_text("text")))
                continue
            pm = page.get_pixmap(dpi=dpi, alpha=False)
            ocr_txt = _ocr_image_tesseract(pm.tobytes("png"))
            if ocr_txt:
                out.append(ocr_txt)
    except Exception:
        pass
    return _clean_text("\n\n".join([t for t in out if t]))

# ---------- public: extract_text() ----------

def extract_text(name: str, mime: str, data: bytes) -> str:
    """Best-effort, pure-Python extraction with optional OCR fallback."""
    e = _ext(name)
    s: Optional[str] = None

    if e in {".txt", ".md", ".py", ".js", ".html", ".css", ".yaml", ".yml", ".sql"}:
        s = data.decode("utf-8", errors="ignore")
        if e == ".html":
            s = re.sub(r"<[^>]+>", " ", s or "")
    elif e == ".csv":
        s = data.decode("utf-8", errors="ignore")
    elif e in {".json", ".xml"}:
        try:
            if e == ".json":
                obj = json.loads(data.decode("utf-8", errors="ignore"))
                s = json.dumps(obj, indent=2, ensure_ascii=False)
            else:
                s = _xml_to_text(data)
        except Exception:
            s = data.decode("utf-8", errors="ignore")
    elif e == ".ipynb":
        s = _try_ipynb_text(data)
    elif e == ".pdf":
        s = _try_pdf_text(data)  # non-OCR path
        # OCR fallback (opt-in) if empty
        if OCR_BACKEND == "tesseract" and not (s or "").strip():
            s = _ocr_pdf_tesseract(data, max_pages=OCR_MAX_PAGES, dpi=OCR_DPI)
    elif e == ".docx":
        s = _try_docx_text(data)
    elif e == ".pptx":
        s = _try_pptx_text(data)
    elif e == ".xlsx":
        s = _try_xlsx_text(data)
    elif e in {".png", ".jpg", ".jpeg", ".gif"}:
        # No non-OCR text here; optionally OCR
        if OCR_BACKEND == "tesseract":
            s = _ocr_image_tesseract(data)

    return "" if s is None else s

def validate_file_accept(name: str, mime: str) -> None:
    e = _ext(name)
    if e in BLOCKED_EXTS:
        raise HTTPException(status_code=415, detail=f"blocked_type:{name}")
    if (mime or "").lower().startswith((AUDIO_PREFIX, VIDEO_PREFIX)):
        raise HTTPException(status_code=415, detail=f"blocked_media:{name}")
    if e not in ALLOWED_EXTS:
        raise HTTPException(status_code=415, detail=f"unsupported_type:{name}")

def build_attachments_system_message(items: List[Tuple[str, str]]) -> str:
    """
    items = [(filename, extracted_text), ...]  (text may be empty for images/unsupported)
    Keep it compact and explicit about “semantic-only”.
    """
    blocks = []
    total = 0
    for name, txt in items:
        trimmed = (txt or "")[:MAX_CHARS_PER_FILE].strip()
        total += len(trimmed)
        info = f"• {name}"
        if trimmed:
            blocks.append(f"{info}\n---\n{trimmed}")
        else:
            blocks.append(f"{info} (no extractable text)")
        if total >= MAX_TOTAL_CHARS:
            blocks.append("… (truncated across files)")
            break

    header = (
        "ATTACHMENTS CONTEXT\n"
        "Use only the content below for semantic understanding (no code execution).\n"
        "Do not assume a file ran; treat it as text provided by the user."
    )
    return header + "\n\n" + "\n\n".join(blocks)

# ----------------------------- Router factory --------------------------------

def make_uploads_router(get_current_user, user_id_from_claims) -> APIRouter:
    """
    Returns an APIRouter mounted by main.py at /api/chat.
    Adds: POST /api/chat/stream_files  (multipart: payload(JSON string) + files[])
    """
    router = APIRouter(prefix="/api/chat", tags=["chat+uploads"])

    # Local client/remote (not imported from main.py to avoid circular imports)
    LANGGRAPH_URL = os.environ["LANGGRAPH_URL"]
    GRAPH_NAME = os.environ.get("LANGGRAPH_GRAPH", "chat")
    client = get_client(url=LANGGRAPH_URL)
    remote = RemoteGraph(GRAPH_NAME, client=client)

    OAI = OpenAI()
    MOD_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
    MOD_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

    # (local copies of small helpers identical to /api/chat/stream for SSE)
    def _blocks_to_text(blocks: Any) -> str:
        if isinstance(blocks, str):
            return blocks
        if isinstance(blocks, list):
            parts: list[str] = []
            for b in blocks:
                if isinstance(b, dict):
                    t = b.get("text") or b.get("input_text") or b.get("output_text")
                else:
                    t = getattr(b, "text", None)
                if t:
                    parts.append(t)
            return "".join(parts)
        return ""

    def _chunk_to_text(chunk: Any) -> str:
        c = getattr(chunk, "content", None)
        if c is not None:
            return _blocks_to_text(c)
        if isinstance(chunk, dict):
            if "content" in chunk:
                return _blocks_to_text(chunk["content"])
            if "delta" in chunk:
                d = chunk["delta"]
                if isinstance(d, dict):
                    return _blocks_to_text(d.get("content") or d.get("text") or d)
                return _blocks_to_text(d)
            if "messages" in chunk and chunk["messages"]:
                m = chunk["messages"][-1]
                if isinstance(m, dict):
                    return _blocks_to_text(m.get("content", m))
                return _blocks_to_text(getattr(m, "content", m))
        if isinstance(chunk, str):
            return chunk
        return ""

    def _sse_event_from_text(text: str) -> bytes:
        t = text.replace("\r\n", "\n").replace("\r", "\n")
        payload = "data: " + t.replace("\n", "\ndata: ")
        return (payload + "\n\n").encode("utf-8")

    @router.post("/stream_files")
    async def stream_chat_with_files(
        request: Request,
        payload: str = Form(...),                 # JSON string -> ChatIn
        files: list[UploadFile] = File(default=[]),
    ):
        # ---- AUTHN ----
        try:
            claims = await get_current_user(request)
        except AuthError as e:
            async def auth_error_stream():
                yield b"event: error\n"
                yield f"data: auth_error:{str(e)}\n\n".encode("utf-8")
                yield b"event: done\n"
                yield b"data: [DONE]\n\n"
            return StreamingResponse(auth_error_stream(), media_type="text/event-stream")

        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")

        user_id = user_id_from_claims(claims)

        # ---- Parse payload ----
        try:
            body = json.loads(payload or "{}")
            p = ChatIn(**body)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_payload")

        # ---- Early rejection: count & types/sizes ----
        if len(files) > MAX_FILES:
            raise HTTPException(status_code=413, detail=f"Too many files uploaded. Maximum allowed is: {MAX_FILES}.")

        attachments: list[tuple[str, str]] = []
        for f in files:
            validate_file_accept(f.filename or "file", f.content_type or "")
            data = await read_limited(f)  # raises 413 on >10MB
            txt = extract_text(f.filename, f.content_type or "", data)
            attachments.append((f.filename, txt))

        # ---- Ensure minimal profile ----
        try:
            await ensure_profile(client, user_id, claims=claims)
        except Exception:
            pass

        # ---- Build agent config & messages ----
        config = build_langgraph_config(p)
        config.setdefault("configurable", {})["user_id"] = user_id

        system_msg = {"role": "system", "content": build_attachments_system_message(attachments)}
        user_msg   = {"role": "user",   "content": p.message}
        thread_id  = (config.get("configurable") or {}).get("thread_id")

        if thread_id:
            try:
                await append_transcript(client, user_id, thread_id,
                                       TranscriptMessage(role="user", content=p.message))
            except Exception:
                pass

        # ---- Optional moderation of input ----
        if MOD_ENABLED:
            try:
                _ = OAI.moderations.create(model=MOD_MODEL, input=p.message).results[0]
            except Exception:
                pass  # best-effort; don't block

        async def event_gen() -> AsyncGenerator[bytes, None]:
            acc: list[str] = []
            try:
                async for item in remote.astream(
                    {"messages": [system_msg, user_msg]},
                    config=config,
                    stream_mode="messages",
                ):
                    msg_chunk = item[0] if isinstance(item, tuple) and len(item) == 2 else item
                    text = _chunk_to_text(msg_chunk)
                    if text:
                        acc.append(text)
                        yield _sse_event_from_text(text)

                if MOD_ENABLED and acc:
                    try:
                        out = "".join(acc)
                        r = OAI.moderations.create(model=MOD_MODEL, input=out).results[0]
                        if r.flagged:
                            yield b"event: policy\n"
                            yield b"data: A safety filter replaced part of the output.\n\n"
                    except Exception:
                        pass
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n".encode("utf-8")
            finally:
                if thread_id and acc:
                    try:
                        await append_transcript(client, user_id, thread_id,
                                                TranscriptMessage(role="assistant", content="".join(acc)))
                    except Exception:
                        pass
                yield b"event: done\n"
                yield b"data: [DONE]\n\n"

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)

    return router