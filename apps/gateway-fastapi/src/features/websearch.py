# apps/gateway-fastapi/src/features/websearch.py
from __future__ import annotations
from pydantic import BaseModel

WEB_SEARCH_FLAG_KEY = "web_search"

class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None
    # NEW: Optional flag; defaults to False to stay backward compatible
    web_search: bool = False

def build_langgraph_config(payload: ChatIn) -> dict:
    cfg = {"configurable": {}}
    if payload.thread_id:
        cfg["configurable"]["thread_id"] = payload.thread_id
    cfg["configurable"][WEB_SEARCH_FLAG_KEY] = bool(payload.web_search)
    return cfg
