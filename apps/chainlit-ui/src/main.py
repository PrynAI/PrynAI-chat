# apps/chainlit-ui/src/main.py
import os
import httpx
import chainlit as cl

from settings_websearch import inject_settings_ui, is_web_search_enabled
from threads_client import (
    ensure_active_thread, get_thread, ensure_title, list_messages
)

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")
# Internal loopback for calling our own FastAPI helpers (used to read the active cookie deterministically)
UI_INTERNAL_BASE = os.environ.get("UI_INTERNAL_BASE", "http://127.0.0.1:8000")

def _active_thread_id() -> str | None:
    return cl.user_session.get("thread_id")

def _set_active_thread_id(tid: str | None) -> None:
    if tid:
        cl.user_session.set("thread_id", tid)
    else:
        cl.user_session.set("thread_id", None)

async def _cookie_active_thread_id() -> str | None:
    """
    Ask the UI server which thread_id is in the cookie. This avoids any race
    between the sidebar click → /open/t/* and Chat start.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{UI_INTERNAL_BASE}/ui/active_thread")
            if r.status_code == 200:
                return (r.json() or {}).get("thread_id")
    except Exception:
        pass
    return None

async def _render_transcript(thread_id: str):
    """
    Replay persisted transcript so the page isn't empty after refresh.
    """
    msgs = await list_messages(thread_id)
    if not msgs:
        return
    for m in msgs:
        role = (m.get("role") or "").lower()
        content = m.get("content") or ""
        # Render in the UI (no tool calls here; just display)
        if role == "user":
            await cl.Message(author="You", content=content).send()
        else:
            await cl.Message(author="Assistant", content=content).send()

@cl.on_chat_start
async def start():
    await inject_settings_ui()

    app_user = cl.user_session.get("user")
    if not app_user:
        await cl.Message("You're not signed in. [Go to sign in](/auth)").send()
        return

    # 1) Strong source of truth: cookie set by /open/t/<thread_id>
    tid_from_cookie = await _cookie_active_thread_id()

    # 2) Secondary: value surfaced by header_auth_callback
    meta_tid = None
    if getattr(app_user, "metadata", None):
        meta_tid = app_user.metadata.get("active_thread_id")

    target_tid = tid_from_cookie or meta_tid

    if target_tid:
        t = await get_thread(target_tid)
        if t:
            _set_active_thread_id(target_tid)
            await cl.Message(content=f"Resuming thread `{target_tid[:8]}`.").send()
            await _render_transcript(target_tid)
            return  # We're done; don't override with 'newest'
        # If unknown/forbidden, fall through to resume-newest

    # Fallback: newest or create
    ts = await ensure_active_thread()
    if ts and ts.thread_id:
        _set_active_thread_id(ts.thread_id)
        await cl.Message(content=f"Resuming thread `{ts.thread_id[:8]}`.").send()
        await _render_transcript(ts.thread_id)
    else:
        await cl.Message(content="Ready. (No threads yet; your first message will create one.)").send()

@cl.on_message
async def handle_message(message: cl.Message):
    # Defensive: ensure an active thread exists
    if not _active_thread_id():
        ts = await ensure_active_thread()
        if ts and ts.thread_id:
            _set_active_thread_id(ts.thread_id)

    # Auto-title on first user turn if untitled
    if _active_thread_id():
        _ = await ensure_title(_active_thread_id(), message.content)

    endpoint = f"{GATEWAY_BASE.rstrip('/')}/api/chat/stream"
    payload = {
        "message": message.content,
        "thread_id": _active_thread_id(),
        "web_search": is_web_search_enabled(),
    }

    app_user = cl.user_session.get("user")
    token = None
    if app_user and getattr(app_user, "metadata", None):
        token = app_user.metadata.get("access_token")

    out = cl.Message(content="")
    await out.send()

    headers = {"accept": "text/event-stream"}
    if token:
        headers["authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="ignore")[:500]
                    await cl.Message(content=f"**Gateway error {resp.status_code}:** {body}").send()
                    return

                current_event = "message"
                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue
                    if raw_line.startswith("event: "):
                        current_event = raw_line.split("event: ", 1)[1].strip()
                        if current_event == "done":
                            break
                        continue
                    if raw_line.startswith("data: "):
                        data = raw_line[6:]
                        if current_event == "policy":
                            await cl.Message(content=f"**Safety notice:** {data}").send()
                        elif current_event == "error":
                            await cl.Message(content=f"**Error:** {data}").send()
                        else:
                            await out.stream_token(data)
        await out.update()
    except Exception as e:
        await cl.Message(content=f"**Error:** {e}").send()