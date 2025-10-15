## Scope:
 - Users can attach up to 5 files (≤ 10 MB each) per message.
 - Supported types: PDF, DOCX, TXT, CSV, PPTX, XLSX, JSON, XML, PNG/JPG/JPEG/GIF, and common code/text files (.py, .js, .html, .css, .yaml/.yml, .sql, .ipynb, .md). - Audio/video and executables are rejected early.
 - Extraction is text‑only (no code execution).
 - PDFs/images can optionally use OCR via env flags


 ## How it works (high level)

 ### Chainlit UI

- The chat supports drag‑and‑drop; when a user sends a message, we collect file elements that Chainlit saved in a temp folder and POST multipart to the Gateway at /api/chat/stream_files.

- The UI then consumes SSE tokens and renders streaming output.

- Temp files are deleted immediately after the request completes (ephemeral ingestion).

### Gateway (FastAPI)

- Validates the user (Entra External ID), rejects early on file count/type/size, performs pure‑Python text extraction (optionally OCR), builds a compact system message (“ATTACHMENTS CONTEXT”) and streams the model response via SSE.

- The route is mounted at POST /api/chat/stream_files by an uploads router; this is included from src/main.py.

### LangGraph agent

- Receives messages=[ system(attachments tip), user(...) ] plus configurable.user_id and (if provided) configurable.thread_id for short‑term memory. Output streams straight back over SSE. (Agent wiring unchanged.)

### Transcript + resume

- The Gateway appends user & assistant turns to a per‑thread transcript in the LangGraph Store, so page reloads can replay history in the UI.

## UI behavior (Chainlit)

### Collect uploads:
 - we read the local file paths for the dropped elements and send them as files[]=... with a JSON payload form field. If no files are attached, the UI uses the existing JSON streaming endpoint.

### SSE parsing:
- a tiny parser handles event: + data: frames; special events policy, error, and done are handled.

### Ephemeral cleanup:
-  finally: removes all temp files right after the request completes. (No persistence on disk beyond the single turn.)

### Chainlit config:
- file uploads are enabled in config.toml; the server still enforces our stricter rules server‑side.

## Gateway API (FastAPI)

### Route

```
POST /api/chat/stream_files    (multipart/form-data)
  form field: payload = JSON string { message, thread_id?, web_search? }
  form field: files   = one or more files (max 5; ≤10 MB each)

```
- The router is created by make_uploads_router(...) and included from src/main.py (inside a try so the app boots even if the feature module is missing). If you see 404 Not Found on /api/chat/stream_files, verify this inclusion

### Early rejection (before processing)

- Count: > 5 files → 413

- Type: audio/video MIME, or BLOCKED_EXTS (.exe, .dll, .bin, .dmg, .iso, .apk, .msi, .so) → 415

- Size: any file > 10 MB → 413

- The server reads streamed chunks in memory (512 KiB per read) and enforces the limit as it goes—no writing to disk

## Extraction pipeline (semantic‑only)

### Text & code:
-  .txt/.md/.py/.js/.html/.css/.yaml/.yml/.sql → decode UTF‑8 (HTML tags stripped).

- CSV/JSON/XML: decoded/pretty‑printed; XML tags stripped to text.

- DOCX/PPTX/XLSX: unzip and read relevant XML parts; tags stripped.

- PDF: try pure‑Python text extraction (PyPDF); if empty and OCR enabled, render first N pages with PyMuPDF and Tesseract and OCR them.

- Images (PNG/JPG/JPEG/GIF): OCR only if enabled; otherwise noted as “no extractable text.”

- Everything is normalized (whitespace folded) and truncated to 12 k chars per file and 24 k chars total to keep context small and TTFT/TPOT high.

- No code is executed; we only treat content as text.

## OCR

- Off by default. Turn on by env:

- UPLOADS_OCR=tesseract

- UPLOADS_OCR_MAX_PAGES=10 (default)

- UPLOADS_OCR_DPI=180 (default)

- UPLOADS_OCR_LANG=eng

- When enabled, scanned PDFs and images get OCR’d; when disabled, scanned PDFs will yield “no extractable text” (matching your earlier observation).

## System message shape

- We inject one compact system message with an explicit instruction and a bulleted list of file summaries:

```
ATTACHMENTS CONTEXT
Use only the content below for semantic understanding (no code execution).
Do not assume a file ran; treat it as text provided by the user.

• FileA.pdf
---
<trimmed text...>

• diagram.png (no extractable text)
…

```

- This keeps the model honest about what it “saw,” and makes the behavior predictable across formats

## Moderation, identity, and transcript

### Auth:
- Validates Entra token (JWKS/issuer/audience) and resolves user_id.

### Moderation:
- Best‑effort input/output moderation using OpenAI’s moderation model; policy notices stream as event: policy.

### Transcript:
- User and assistant turns are appended per thread for reload; the UI replays via /api/threads/{id}/messages.

## Persistence & privacy

### Session‑only ingestion:
- UI temp files are deleted after streaming; the Gateway does not store file bytes or parsed text—only the assistant’s answer is stored in the transcript. (Matches the “ephemeral ingestion” requirement.)

- No automatic long‑term file storage and no code execution on uploaded content. The attachments exist purely as additional context to the LLM for that turn

## Configuration knobs

### OCR: 
- UPLOADS_OCR, UPLOADS_OCR_MAX_PAGES, UPLOADS_OCR_DPI, UPLOADS_OCR_LANG.

### Moderation:
- MODERATION_ENABLED, MODERATION_MODEL.

### LangGraph:
- LANGGRAPH_URL, LANGGRAPH_GRAPH.

### Chainlit (UI):
-  file‑upload feature enabled in config.toml (UI permissive; Gateway enforces the strict rules).

## End‑to‑end flow (request)

```
Browser (multipart) → Chainlit → POST /api/chat/stream_files
  ⮑ Gateway:
      - Auth check (Entra)
      - Early reject (count/type/size)
      - Text extraction (opt. OCR)
      - Build "ATTACHMENTS CONTEXT" system message
      - Ensure profile + write user turn to transcript
      - Stream LLM tokens (SSE) → UI
      - Write assistant turn to transcript

```
## Testing

### In the UI

- Open the chat, drop a PDF + XLSX + PNG at once, ask “summarize these.”

- You should see streamed tokens; images show as “no extractable text” unless OCR is enabled.

- Reload the page: transcript replay should show your user/assistant turns.

## Rejection checks

- 6th file → 413 Too many files uploaded…

- 11 MB file → 413 File too large…

- .exe → 415 blocked_type:…

- video/mp4 → 415 blocked_media

## Operational notes

- The uploads router is included in src/main.py under a try…except. If you ship a revision without the feature module, the app will boot but /api/chat/stream_files returns 404. Ensure you deploy a build that includes src/features/uploads.py (the UI surfaces the 404 in a friendly message already).

- Memory footprint: the Gateway streams from UploadFile into memory with a 512 KiB buffer and a strict 10 MB cap per file; it never writes to disk. This aligns with the 2 GiB limits on the container.


## What’s in the code

### Chainlit UI

- apps/chainlit-ui/src/main.py — collects uploads, calls /api/chat/stream_files, parses SSE, deletes temp files.

- apps/chainlit-ui/src/sse_utils.py — minimal SSE parser.
apps/chainlit-ui/config.toml — upload feature enabled; we still enforce server‑side policies.

### Gateway

- apps/gateway-fastapi/src/main.py — mounts uploads router, streams chat, moderation, transcripts.

- apps/gateway-fastapi/src/features/uploads.py — limits, allowed/blocked types, streaming size guard, text extraction + OCR (opt‑in), system message builder, SSE.

- apps/gateway-fastapi/src/features/transcript.py — transcript persistence per thread.

## Known limitations

- Scanned PDFs / images require OCR; we keep it opt‑in to avoid runtime bloat. If your workload is scan‑heavy, enable UPLOADS_OCR=tesseract and ship the Tesseract/PyMuPDF deps in the Gateway image.

- No code execution: notebooks, SQL, JS, etc., are treated purely as text. For executable analysis, add a sandboxed tool in a future slice.

- RAG: This MVP does not persist documents. A later slice can ingest to pgvector for retrieval. (Long‑term memory for user facts/episodic summaries is already in place separately.)

## Future work 

- The next increment would be “OCR‑on‑by‑default builds” and a RAG ingest path for opted‑in, durable documents.