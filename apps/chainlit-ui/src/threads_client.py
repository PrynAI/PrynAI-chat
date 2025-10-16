# apps/chainlit-ui/src/threads_client.py
from __future__ import annotations

import os
import httpx
from typing import List, Dict, Any, Optional

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080").rstrip("/")

def _hdr(token: Optional[str]) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}

async def ensure_active_thread(token: Optional[str]) -> str:
    """
    Return newest thread id (create one if none).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{GATEWAY}/api/threads?limit=1", headers=_hdr(token))
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]["thread_id"]
        # create
        r = await client.post(f"{GATEWAY}/api/threads", json={}, headers=_hdr(token))
        r.raise_for_status()
        return r.json()["thread_id"]

async def list_messages(token: Optional[str], thread_id: str) -> List[Dict[str, Any]]:
    """
    Return [{role, content}, ...] persisted for thread_id.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GATEWAY}/api/threads/{thread_id}/messages", headers=_hdr(token))
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []