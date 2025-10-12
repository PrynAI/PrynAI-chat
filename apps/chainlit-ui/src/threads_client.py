# apps/chainlit-ui/src/threads_client.py
from __future__ import annotations
import os
import httpx
import chainlit as cl
from dataclasses import dataclass
from typing import Optional, Dict

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

@dataclass
class ThreadSummary:
    thread_id: str
    title: Optional[str] = None

def _auth_headers() -> Dict[str, str]:
    app_user = cl.user_session.get("user")
    token = None
    if app_user and getattr(app_user, "metadata", None):
        token = app_user.metadata.get("access_token")
    h = {"accept": "application/json"}
    if token:
        h["authorization"] = f"Bearer {token}"
    return h

async def ensure_active_thread() -> Optional[ThreadSummary]:
    """
    Try to resume the newest thread for this user. If none, create one.
    """
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=20) as client:
        # 1) Resume newest
        try:
            r = await client.get(f"{GATEWAY_BASE}/api/threads?limit=1", headers=headers)
            if r.status_code == 200:
                items = r.json() or []
                if items:
                    t = items[0]
                    return ThreadSummary(thread_id=t["thread_id"], title=t.get("title"))
        except Exception:
            pass
        # 2) Create
        try:
            r = await client.post(f"{GATEWAY_BASE}/api/threads", json={}, headers=headers)
            if r.status_code == 200:
                t = r.json()
                return ThreadSummary(thread_id=t["thread_id"], title=t.get("title"))
        except Exception:
            pass
    return None