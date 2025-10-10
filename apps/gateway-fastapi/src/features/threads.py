# apps/gateway-fastapi/src/features/threads.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

# We rely on the LangGraph Python SDK you already use in main.py. (client is injected)
# Threads primitives we use are documented here:
#  - create(): make a new thread
#  - search(): list threads with filters (e.g., metadata={"user_id": ...})
#  - get(): fetch a single thread
#  - update(): update thread metadata (title) [available in newer SDKs]
# Docs: Use threads + SDK reference. 

class ThreadCreate(BaseModel):
    title: Optional[str] = Field(default=None, description="Optional friendly title for the thread")

class ThreadSummary(BaseModel):
    thread_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

def _summarize(t: Dict[str, Any]) -> ThreadSummary:
    meta = t.get("metadata") or {}
    return ThreadSummary(
        thread_id=t.get("thread_id"),
        title=meta.get("title"),
        status=t.get("status"),
        created_at=t.get("created_at"),
        updated_at=t.get("updated_at"),
    )

def make_threads_router(client, get_current_user, user_id_from_claims) -> APIRouter:
    """
    Endpoints:
      POST /api/threads         -> create a thread (metadata.user_id + optional title)
      GET  /api/threads         -> list threads for current user (newest first)
      GET  /api/threads/{id}    -> read one thread (403 if not owned by user)
      PUT  /api/threads/{id}    -> update title (best-effort; 405 if SDK lacks 'update')
    """
    router = APIRouter(prefix="/api/threads", tags=["threads"])

    @router.post("", response_model=ThreadSummary)
    async def create_thread(payload: ThreadCreate, request: Request):
        claims = await get_current_user(request)
        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")
        user_id = user_id_from_claims(claims)

        meta = {"user_id": user_id}
        if payload.title:
            meta["title"] = payload.title

        # Create the thread with our metadata
        t = await client.threads.create(metadata=meta)
        return _summarize(t)

    @router.get("", response_model=List[ThreadSummary])
    async def list_threads(request: Request, limit: int = 50):
        claims = await get_current_user(request)
        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")
        user_id = user_id_from_claims(claims)

        # Filter by owner, newest first
        items = await client.threads.search(
            metadata={"user_id": user_id},
            sort_by="updated_at",
            sort_order="desc",
            limit=limit,
        )
        return [_summarize(t) for t in items or []]

    @router.get("/{thread_id}", response_model=ThreadSummary)
    async def get_thread(thread_id: str, request: Request):
        claims = await get_current_user(request)
        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")
        user_id = user_id_from_claims(claims)

        t = await client.threads.get(thread_id)
        if not t or (t.get("metadata") or {}).get("user_id") != user_id:
            # Hide existence from other users
            raise HTTPException(status_code=404, detail="not_found")
        return _summarize(t)

    @router.put("/{thread_id}", response_model=ThreadSummary)
    async def rename_thread(thread_id: str, payload: ThreadCreate, request: Request):
        claims = await get_current_user(request)
        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")
        user_id = user_id_from_claims(claims)

        t = await client.threads.get(thread_id)
        if not t or (t.get("metadata") or {}).get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="not_found")

        if not payload.title:
            return _summarize(t)

        # Some SDK versions provide threads.update(); if not, return 405.
        if not hasattr(client.threads, "update"):
            raise HTTPException(status_code=405, detail="update_not_supported_by_sdk")

        new_meta = dict(t.get("metadata") or {})
        new_meta["title"] = payload.title
        t2 = await client.threads.update(thread_id, metadata=new_meta)
        return _summarize(t2)

    return router
