# my_agent/graphs/chat.py
from typing import Optional
from langgraph.graph import MessagesState, StateGraph, START
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore  # NEW

from my_agent.features.web_search import llm_and_messages_for_config  # existing
from my_agent.utils.checkpointer import make_checkpointer              # existing

# NEW: long-term memory helpers
from my_agent.features.lt_memory import (
    search_relevant_memories,
    memory_context_system_message,
    maybe_write_user_memories,
    write_episodic_summary,
)

class ChatState(MessagesState):
    # MessagesState already has: messages: list[AnyMessage]
    pass

def _last_user_text(msgs: list[AnyMessage]) -> Optional[str]:
    for m in reversed(msgs):
        role = getattr(m, "type", None) or getattr(m, "role", None)
        if (role or "").lower() in ("human", "user"):
            c = getattr(m, "content", None)
            return c if isinstance(c, str) else getattr(c, "strip", lambda: "")()
    return None

def chat_node(
    state: ChatState,
    config: Optional[RunnableConfig] = None,
    *,
    store: Optional[BaseStore] = None,  # injected by LangGraph Platform
) -> dict:
    """
    Core chat node:
    - Optionally prepends memory system tip based on semantic search (pgvector).
    - Decides which LLM to use (with or without web_search bound).
    - Invokes the LLM and, after completion, writes new memories (user + episodic).
    """
    # 0) Derive config bits (user/thread)
    cfg = (config or {}).get("configurable") or {}
    user_id: Optional[str] = cfg.get("user_id")
    thread_id: Optional[str] = cfg.get("thread_id")

    # 1) Choose LLM (web_search feature unchanged)
    llm, messages = llm_and_messages_for_config(config, state["messages"])

    # 2) Retrieve memories (semantic search) and prepend as a compact system tip
    last_user_text = _last_user_text(state["messages"])
    if store is not None and user_id and last_user_text:
        hits = search_relevant_memories(store, user_id, last_user_text, k_user=4, k_episodic=4)
        tip = memory_context_system_message(hits, max_chars=900)
        if tip is not None:
            messages = [tip] + list(messages)

    # 3) Invoke LLM with full message list (preserve config!)
    ai_msg = llm.invoke(messages, config=config)

    # 4) After completion, write memories (best-effort; never block)
    if store is not None and user_id and last_user_text:
        try:
            maybe_write_user_memories(store, user_id, thread_id, last_user_text)
        except Exception:
            pass
        try:
            ai_text = getattr(ai_msg, "content", "") or ""
            write_episodic_summary(store, user_id, thread_id, last_user_text, ai_text)
        except Exception:
            pass

    return {"messages": [ai_msg]}

# --- Graph wiring (unchanged) ---
builder = StateGraph(ChatState)
builder.add_node("chat", chat_node)
builder.add_edge(START, "chat")

# Local dev can opt-in to MemorySaver; Cloud uses built-in Postgres checkpointer.
_cp = make_checkpointer()
graph = builder.compile(checkpointer=_cp) if _cp else builder.compile()