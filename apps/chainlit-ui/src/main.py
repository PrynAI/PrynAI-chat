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
    # Render a tiny control row so testers can start a truly new backend thread
    await cl.Message(
        content="**Controls:** Start a fresh chat thread (won't carry over context).",
        actions=[Action(name="new_chat", payload={"value": "new"}, label="➕ New Chat")],
    ).send()

@cl.on_chat_start
async def start():
    await inject_settings_ui()  # your existing Web Search toggle
    app_user = cl.user_session.get("user")
    if not app_user:
        await cl.Message("You're not signed in. [Go to sign in](/auth)").send()
        return

    # Resume newest thread for this user (matches tests 1–3)
    ts = await ensure_active_thread()
    if ts and ts.thread_id:
        _set_active_thread_id(ts.thread_id)
        await cl.Message(content=f"Resuming thread `{ts.thread_id[:8]}`.").send()
    else:
        await cl.Message(content="Ready. (No threads yet; your first message will create one.)").send()

    # Show the “New Chat” control every time
    await _render_controls()

@cl.action_callback("new_chat")
async def _new_chat_action(action: Action):
    ts = await create_new_thread()
    if not ts:
        await cl.Message(content="Could not create a new thread. Try again.").send()
        return
    _set_active_thread_id(ts.thread_id)
    await cl.Message(content=f"Started new thread `{ts.thread_id[:8]}`.").send()