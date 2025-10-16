# apps/chainlit-ui/src/main.py
import os, json, mimetypes
import httpx
import chainlit as cl

from settings_websearch import inject_settings_ui, is_web_search_enabled
from threads_client import ensure_active_thread, get_thread, ensure_title, list_messages
from sse_utils import iter_sse_events

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

def _active_thread_id() -> str | None: return cl.user_session.get("thread_id")
def _set_active_thread_id(tid: str | None) -> None: cl.user_session.set("thread_id", tid if tid else None)

async def _render_transcript(thread_id: str):
    msgs = await list_messages(thread_id)
    if not msgs: return
    for m in msgs:
        role = (m.get("role") or "").lower()
        content = m.get("content") or ""
        if role == "user": await cl.Message(author="You", content=content).send()
        else: await cl.Message(content=content).send()

@cl.on_chat_start
async def start():
    await inject_settings_ui()
    app_user = cl.user_session.get("user")
    if not app_user:
        await cl.Message("You're not signed in. [Go to sign in](/auth)").send()
        return
    meta_tid = getattr(app_user, "metadata", None) and app_user.metadata.get("active_thread_id")
    if meta_tid:
        t = await get_thread(meta_tid)
        if t:
            _set_active_thread_id(meta_tid)
            await cl.Message(content=f"Resuming thread `{meta_tid[:8]}`.").send()
            await _render_transcript(meta_tid); return
    ts = await ensure_active_thread()
    if ts and ts.thread_id:
        _set_active_thread_id(ts.thread_id)
        await cl.Message(content=f"Resuming thread `{ts.thread_id[:8]}`.").send()
        await _render_transcript(ts.thread_id)
    else:
        await cl.Message(content="Ready. (No threads yet; your first message will create one.)").send()

def _collect_uploads(message: cl.Message):
    """Return a list of {'name','path','mime'} for files dropped on this message."""
    out = []
    for el in (getattr(message, "elements", None) or []):
        # Accept any element that exposes a local path (Chainlit writes temp files server-side)
        p = getattr(el, "path", None)
        if not p or not os.path.exists(p): continue
        name = getattr(el, "name", os.path.basename(p))
        mime = getattr(el, "mime", None) or (mimetypes.guess_type(name)[0] or "application/octet-stream")
        out.append({"name": name, "path": p, "mime": mime})
    return out

@cl.on_message
async def handle_message(message: cl.Message):
    if not _active_thread_id():
        ts = await ensure_active_thread()
        if ts and ts.thread_id: _set_active_thread_id(ts.thread_id)
    if _active_thread_id():
        _ = await ensure_title(_active_thread_id(), message.content)

    app_user = cl.user_session.get("user")
    token = getattr(app_user, "metadata", {}).get("access_token") if app_user else None
    headers = {"accept": "text/event-stream"}
    if token: headers["authorization"] = f"Bearer {token}"

    payload = {
        "message": message.content,
        "thread_id": _active_thread_id(),
        "web_search": is_web_search_enabled(),
    }

    uploads = _collect_uploads(message)
    out = cl.Message(content=""); await out.send()

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            if uploads:
                # Stream with files (multipart + SSE)
                files = []
                for u in uploads:
                    files.append(("files", (u["name"], open(u["path"], "rb"), u["mime"])))
                # NOTE: do not JSON-encode files; send payload separately in a form field
                form = {"payload": json.dumps(payload)}
                url = f"{GATEWAY_BASE.rstrip('/')}/api/chat/stream_files"
                async with client.stream("POST", url, data=form, files=files, headers=headers) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="ignore")[:500]
                        await cl.Message(content=f"**Gateway error {resp.status_code}:** {body}").send()
                        return
                    async for event, data in iter_sse_events(resp):
                        if event == "done": break
                        elif event == "policy": await cl.Message(content=f"**Safety notice:** {data}").send()
                        elif event == "error": await cl.Message(content=f"**Error:** {data}").send()
                        else: await out.stream_token(data)
            else:
                # Existing JSON streaming path (unchanged)
                url = f"{GATEWAY_BASE.rstrip('/')}/api/chat/stream"
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="ignore")[:500]
                        await cl.Message(content=f"**Gateway error {resp.status_code}:** {body}").send()
                        return
                    async for event, data in iter_sse_events(resp):
                        if event == "done": break
                        elif event == "policy": await cl.Message(content=f"**Safety notice:** {data}").send()
                        elif event == "error": await cl.Message(content=f"**Error:** {data}").send()
                        else: await out.stream_token(data)
        await out.update()
    except Exception as e:
        await cl.Message(content=f"**Error:** {e}").send()
    finally:
        # Clean up Chainlit temp files immediately (session-only ingestion)
        for u in uploads:
            try: os.remove(u["path"])
            except Exception: pass