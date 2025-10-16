# apps/gateway-fastapi/src/features/transcript.py
from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


def _ns(user_id: str, thread_id: str) -> list[str]:
    # Namespace for durable per-thread items
    return ["threads", user_id, thread_id]


class TranscriptMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    ts: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


async def _get_transcript(client, user_id: str, thread_id: str) -> list[dict]:
    """
    Transcript lives as one item: key="transcript" in the thread namespace.
    Shape: {"messages": [ {role, content, ts}, ... ]}
    """
    try:
        item = await client.store.get_item(_ns(user_id, thread_id), key="transcript")
        val = getattr(item, "value", item) if item else None
        if isinstance(val, dict):
            return list(val.get("messages") or [])
    except Exception:
        pass
    return []


async def append_transcript(client, user_id: str, thread_id: str, msg: TranscriptMessage) -> None:
    msgs = await _get_transcript(client, user_id, thread_id)
    msgs.append(msg.model_dump())
    await client.store.put_item(
        _ns(user_id, thread_id),
        key="transcript",
        value={"messages": msgs},
        # allow future filtering if needed
        index=["user_id", "thread_id"],
    )


def make_transcript_router(client, get_current_user, user_id_from_claims) -> APIRouter:
    """
    Adds: GET /api/threads/{thread_id}/messages  (owner-only)
    """
    router = APIRouter(prefix="/api/threads", tags=["threads"])

    @router.get("/{thread_id}/messages")
    async def list_messages(thread_id: str, request: Request) -> list[dict]:
        claims = await get_current_user(request)
        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")
        user_id = user_id_from_claims(claims)

        # Ownership check via Threads API (just like your other endpoints).
        t = await client.threads.get(thread_id)
        if not t or (t.get("metadata") or {}).get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="not_found")

        msgs = await _get_transcript(client, user_id, thread_id)
        # client.store maintains created_at, but we keep it simple and sort by ts asc
        msgs.sort(key=lambda m: m.get("ts") or "")
        return msgs

    return router