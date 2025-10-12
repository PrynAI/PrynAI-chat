# apps/chainlit-ui/src/main.py
import os
import httpx
import chainlit as cl
from chainlit.action import Action

from settings_websearch import inject_settings_ui, is_web_search_enabled
from threads_client import ensure_active_thread, create_new_thread

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

def _active_thread_id() -> str | None:
    return cl.user_session.get("thread_id")

def _set_active_thread_id(tid: str) -> None:
    cl.user_session.set("thread_id", tid)

async def _render_controls():
    # A tiny control row so testers can always start a truly new backend thread
    await cl.Message(
        content="**Controls:** Start a fresh chat thread (won't carry over context).",
        actions=[Action(name="new_chat", payload={"value": "new"}, label="➕ New Chat")],
    ).send()

@cl.on_chat_start
async def start():
    await inject_settings_ui()  # Web Search toggle (unchanged)
    app_user = cl.user_session.get("user")
    if not app_user:
        await cl.Message("You're not signed in. [Go to sign in](/auth)").send()
        return

    # Resume newest thread or create one if none (keeps your passing tests 1–3)
    ts = await ensure_active_thread()
    if ts and ts.thread_id:
        _set_active_thread_id(ts.thread_id)
        await cl.Message(content=f"Resuming thread `{ts.thread_id[:8]}`.").send()
    else:
        await cl.Message(content="Ready. (No threads yet; your first message will create one.)").send()

    await _render_controls()

@cl.action_callback("new_chat")
async def _new_chat_action(action: Action):
    ts = await create_new_thread()
    if not ts:
        await cl.Message(content="Could not create a new thread. Try again.").send()
        return
    _set_active_thread_id(ts.thread_id)
    await cl.Message(content=f"Started new thread `{ts.thread_id[:8]}`.").send()

@cl.on_message
async def handle_message(message: cl.Message):
    # Defensive: if the session lost the thread, ensure one exists now.
    if not _active_thread_id():
        ts = await ensure_active_thread()
        if ts and ts.thread_id:
            _set_active_thread_id(ts.thread_id)

    endpoint = f"{GATEWAY_BASE.rstrip('/')}/api/chat/stream"
    payload = {
        "message": message.content,
        "thread_id": _active_thread_id(),
        "web_search": is_web_search_enabled(),
    }

    # Pull the Entra access token from the authenticated user metadata.
    app_user = cl.user_session.get("user")
    token = None
    if app_user and getattr(app_user, "metadata", None):
        token = app_user.metadata.get("access_token")

    # Placeholder assistant message to stream into
    out = cl.Message(content="")
    await out.send()

    headers = {"accept": "text/event-stream"}
    if token:
        headers["authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                # Helpful error surface (otherwise you'd see a silent empty message)
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