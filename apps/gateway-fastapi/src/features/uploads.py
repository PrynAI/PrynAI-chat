# apps/gateway-fastapi/src/features/uploads.py
from __future__ import annotations
import io, os, re, json, zipfile, html
from typing import List, Tuple, Optional
from fastapi import UploadFile, HTTPException

MAX_FILES = 5
MAX_FILE_MB = 10
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
CHUNK = 512 * 1024  # 512 KiB
# Keep the attachments context compact for TTFT/TPOT and model tokens
MAX_CHARS_PER_FILE = 12000
MAX_TOTAL_CHARS = 24000

# Allowed extensions (lowercased, with dot)
ALLOWED_EXTS = {
    # Documents & Data
    ".pdf", ".docx", ".txt", ".csv", ".pptx", ".xlsx", ".json", ".xml",
    # Images (we don't OCR; we only list metadata)
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
            raise HTTPException(status_code=413, detail=f"file_too_large:{file.filename}")
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

def extract_text(name: str, mime: str, data: bytes) -> str:
    """Best-effort, pure-Python extraction (semantic-only)."""
    e = _ext(name)
    t = (mime or "").lower()
    s: Optional[str] = None

    if e in {".txt", ".md", ".py", ".js", ".html", ".css", ".yaml", ".yml", ".sql"}:
        s = data.decode("utf-8", errors="ignore")
        # crude HTML to text if needed
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
        s = _try_pdf_text(data)
    elif e == ".docx":
        s = _try_docx_text(data)
    elif e == ".pptx":
        s = _try_pptx_text(data)
    elif e == ".xlsx":
        s = _try_xlsx_text(data)

    if s is None:
        # Non-text (images) or unsupported → include filename only
        return ""
    return s

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