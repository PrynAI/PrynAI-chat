from __future__ import annotations
import os
import httpx
import chainlit as cl
from dataclasses import dataclass
from typing import Optional, Dict, List

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080").rstrip("/")

@dataclass
class ThreadSummary:
    thread_id: str
    title: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class APIError(Exception):
    def __init__(self, status: int, body: str = ""):
        super().__init__(f"gateway_status_{status}")
        self.status = status
        self.body = body

def _auth_headers() -> Dict[str, str]:
    app_user = cl.user_session.get("user")
    token = None
    if app_user and getattr(app_user, "metadata", None):
        token = app_user.metadata.get("access_token")
    h = {"accept": "application/json"}
    if token:
        h["authorization"] = f"Bearer {token}"
    return h

# ---------- Threads CRUD ----------

async def list_threads(limit: int = 50) -> List[ThreadSummary]:
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GATEWAY_BASE}/api/threads?limit={limit}", headers=headers)
        if r.status_code in (401, 403):
            raise APIError(r.status_code, r.text or "")
        if r.status_code != 200:
            return []
        items = r.json() or []
        return [
            ThreadSummary(
                thread_id=i.get("thread_id"),
                title=i.get("title"),
                created_at=i.get("created_at"),
                updated_at=i.get("updated_at"),
            )
            for i in items
        ]

async def get_thread(thread_id: str) -> Optional[ThreadSummary]:
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GATEWAY_BASE}/api/threads/{thread_id}", headers=headers)
        if r.status_code in (401, 403):
            raise APIError(r.status_code, r.text or "")
        if r.status_code != 200:
            return None
        t = r.json()
        return ThreadSummary(
            thread_id=t.get("thread_id"),
            title=t.get("title"),
            created_at=t.get("created_at"),
            updated_at=t.get("updated_at"),
        )

async def ensure_active_thread() -> Optional[ThreadSummary]:
    """Resume newest thread or create one if none exists."""
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.get(f"{GATEWAY_BASE}/api/threads?limit=1", headers=headers)
            if r.status_code == 200:
                items = r.json() or []
                if items:
                    t = items[0]
                    return ThreadSummary(
                        thread_id=t["thread_id"],
                        title=t.get("title"),
                        created_at=t.get("created_at"),
                        updated_at=t.get("updated_at"),
                    )
        except Exception:
            pass
        try:
            r = await client.post(f"{GATEWAY_BASE}/api/threads", json={}, headers=headers)
            if r.status_code == 200:
                t = r.json()
                return ThreadSummary(
                    thread_id=t["thread_id"],
                    title=t.get("title"),
                    created_at=t.get("created_at"),
                    updated_at=t.get("updated_at"),
                )
        except Exception:
            pass
    return None

async def create_new_thread(title: Optional[str] = None) -> Optional[ThreadSummary]:
    headers = _auth_headers()
    payload = {"title": title} if title else {}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{GATEWAY_BASE}/api/threads", json=payload, headers=headers)
        if r.status_code == 200:
            t = r.json()
            return ThreadSummary(
                thread_id=t["thread_id"],
                title=t.get("title"),
                created_at=t.get("created_at"),
                updated_at=t.get("updated_at"),
            )
    return None

# ---------- Auto-title (first user prompt) ----------

def _suggest_title_from_text(text: str) -> str:
    import re
    words = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-’'?!.,]", "", text)).strip().split(" ")
    base = " ".join(words[:7]).strip()
    title = base[:60].rstrip(" .,:;")
    return title.title() if title else "New Chat"

async def ensure_title(thread_id: str, user_prompt: str) -> Optional[str]:
    """If thread has no title, set one derived from the user's first prompt."""
    t = await get_thread(thread_id)
    if not t:
        return None
    if (t.title or "").strip():
        return t.title

    new_title = _suggest_title_from_text(user_prompt)
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.put(
            f"{GATEWAY_BASE}/api/threads/{thread_id}",
            json={"title": new_title},
            headers=headers,
        )
        if r.status_code == 200:
            return new_title
    return None

# ---------- Transcript ----------

async def list_messages(thread_id: str) -> list[dict]:
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GATEWAY_BASE}/api/threads/{thread_id}/messages", headers=headers)
        if r.status_code in (401, 403):
            raise APIError(r.status_code, r.text or "")
        if r.status_code != 200:
            return []
        return r.json() or []