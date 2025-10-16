# apps/chainlit-ui/src/main.py
from __future__ import annotations

import os
import asyncio
import httpx
import chainlit as cl
from typing import List, Dict, Any, Optional

from src.threads_client import (
    ensure_active_thread,
    list_messages,
)

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080").rstrip("/")

def _user_token() -> Optional[str]:
    u = cl.user_session.get("user")
    if not u:
        return None
    return (u.metadata or {}).get("access_token")

def _active_thread_from_metadata() -> Optional[str]:
    u = cl.user_session.get("user")
    if not u:
        return None
    return (u.metadata or {}).get("active_thread_id")

@cl.on_chat_start
async def _on_start():
    """
    1) Resolve the active thread id from header-auth metadata (cookie or deep link).
    2) Fallback to newest thread (creates one if none).
    3) Fetch transcript from Gateway and replay it.
    """
    token = _user_token()
    tid = _active_thread_from_metadata()

    # Fallback to newest if metadata had no thread (or cookie race)
    if not tid:
        tid = await ensure_active_thread(token)

    cl.user_session.set("thread_id", tid)

    # Small banner so users know which thread we resumed
    await cl.Message(content=f"Resuming thread `{tid[:8]}`.", author="system").send()

    # Load and replay persisted transcript so refresh never shows a blank screen
    try:
        messages = await list_messages(token, tid)
    except Exception:
        messages = []

    if messages:
        for m in messages:
            role = (m or {}).get("role")
            content = (m or {}).get("content") or ""
            # Guard against streaming artifacts or empty placeholders
            if not content.strip():
                continue
            author = "You" if role == "user" else "Assistant"
            msg = cl.Message(author=author, content=content)
            await msg.send()

@cl.on_message
async def _on_message(message: cl.Message):
    """
    Stream via Gateway -> LangGraph. We include the thread_id so the Gateway
    writes the transcript and the agent runs on the right thread context.
    """
    token = _user_token()
    tid = cl.user_session.get("thread_id")
    payload = {"message": message.content, "thread_id": tid}

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    stream_url = f"{GATEWAY}/api/chat/stream"

    # Stream chunks into one Chainlit message
    assistant = cl.Message(author="Assistant", content="")
    await assistant.send()

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", stream_url, json=payload, headers=headers) as r:
            async for line in r.aiter_lines():
                if not line:
                    continue
                # SSE spec: multiple 'data:' lines form one event. We treat each line atomically here
                # because the server already does the right multi-line framing.
                if line.startswith("data: "):
                    await assistant.stream_token(line[6:])
                elif line == "event: done":
                    break

    await assistant.update()