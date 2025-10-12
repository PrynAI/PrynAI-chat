# apps/agent-langgraph/my_agent/utils/checkpointer.py
from __future__ import annotations
import os
from typing import Optional

try:
    # Local/dev-only checkpointer (not used on LangGraph Cloud)
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
except Exception:
    MemorySaver = None  # type: ignore


def make_checkpointer() -> Optional[object]:
    """
    Return a local checkpointer if LG_USE_LOCAL_MEMORY=true.
    On LangGraph Cloud/Server, DO NOT pass a custom checkpointer; the platform
    provides a durable Postgres checkpointer automatically.
    """
    use_local = os.getenv("LG_USE_LOCAL_MEMORY", "false").lower() in ("1", "true", "yes")
    if use_local and MemorySaver is not None:
        return MemorySaver()
    return None