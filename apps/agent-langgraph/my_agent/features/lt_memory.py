# my_agent/features/lt_memory.py
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field, ConfigDict  # <-- add ConfigDict
from langgraph.store.base import BaseStore
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage


# ----- Namespaces (per-user) -------------------------------------------------
def ns_user(user_id: str) -> Tuple[str, ...]:
    return ("users", user_id, "memories", "user")

def ns_episodic(user_id: str) -> Tuple[str, ...]:
    return ("users", user_id, "memories", "episodic")


# ----- LLM for small classification/summarization tasks ----------------------
def _memory_llm() -> ChatOpenAI:
    # Responses API so we can use structured outputs.
    return ChatOpenAI(
        model="gpt-5-mini",
        temperature=0.0,
        streaming=False,
        use_responses_api=True,
        output_version="responses/v1",
        reasoning={"effort": "low"},
    )


# ----- Schemas for structured extraction ------------------------------------
class ExtractedMemories(BaseModel):
    """Model for extracting stable, durable user memories."""
    # STRICT: force "additionalProperties": false at the root for Responses API
    model_config = ConfigDict(extra="forbid")

    memories: List[str] = Field(
        default_factory=list,
        description="Short, durable facts or preferences. Leave empty if nothing stable to store.",
    )


# ----- Public API ------------------------------------------------------------
@dataclass
class RetrievedMemory:
    key: str
    text: str
    score: float
    kind: str  # "user" | "episodic"

def search_relevant_memories(
    store: BaseStore,
    user_id: str,
    query: str,
    *,
    k_user: int = 4,
    k_episodic: int = 4,
) -> List[RetrievedMemory]:
    results: List[RetrievedMemory] = []

    try:
        user_hits = store.search(ns_user(user_id), query=query, limit=k_user) or []
        for it in user_hits:
            txt = (it.value or {}).get("text") or ""
            results.append(RetrievedMemory(key=str(it.key), text=txt, score=float(getattr(it, "score", 0.0)), kind="user"))
    except Exception:
        pass

    try:
        epi_hits = store.search(ns_episodic(user_id), query=query, limit=k_episodic) or []
        for it in epi_hits:
            txt = (it.value or {}).get("text") or ""
            results.append(RetrievedMemory(key=str(it.key), text=txt, score=float(getattr(it, "score", 0.0)), kind="episodic"))
    except Exception:
        pass

    results.sort(key=lambda r: r.score, reverse=True)
    return results

def memory_context_system_message(items: Iterable[RetrievedMemory], max_chars: int = 900) -> Optional[SystemMessage]:
    bulleted: List[str] = []
    for r in items:
        prefix = "•" if r.kind == "user" else "–"
        bulleted.append(f"{prefix} {r.text.strip()}")
    txt = "\n".join(bulleted).strip()
    if not txt:
        return None
    if len(txt) > max_chars:
        txt = txt[: max_chars - 20].rstrip() + " …"
    out = (
        "You have durable memory about this user and prior episodes. "
        "Use it to personalize and stay consistent when relevant.\n\n"
        f"{txt}"
    )
    return SystemMessage(content=out)

def maybe_write_user_memories(
    store: BaseStore,
    user_id: str,
    thread_id: Optional[str],
    last_user_text: str,
) -> int:
    """
    Extract at-most-a-few durable facts/preferences and store them in user memory.
    Returns the number of memories written.
    """
    if not last_user_text or not user_id:
        return 0

    llm = _memory_llm()
    instr = (
        "Extract at most 3 short, durable facts or preferences about the SPEAKER "
        "(the human user). Only include items likely to remain true later "
        "(e.g., timezone, roles, tools, formatting preference, likes/dislikes, "
        "recurring goals). Skip anything transient or speculative. "
        "Return JSON with a 'memories' list."
    )
    doc = [{"role": "system", "content": instr}, {"role": "user", "content": last_user_text}]

    # STRICT schema + Responses API
    parsed = llm.with_structured_output(ExtractedMemories, strict=True).invoke(doc)

    added = 0
    for m in (parsed.memories or [])[:3]:
        text = m.strip()
        if not text:
            continue
        key = str(uuid.uuid4())
        value = {
            "text": text,
            "type": "user",
            "source_thread": thread_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            store.put(ns_user(user_id), key=key, value=value, index=["text"])
            added += 1
        except Exception:
            pass
    return added

def write_episodic_summary(
    store: BaseStore,
    user_id: str,
    thread_id: Optional[str],
    user_text: str,
    assistant_text: str,
) -> Optional[str]:
    if not (user_id and user_text and assistant_text):
        return None

    llm = _memory_llm()
    instr = (
        "Summarize this exchange in one short sentence for future search. "
        "Focus on the user's goal/topic or task, not the wording."
    )
    doc = [
        {"role": "system", "content": instr},
        {"role": "user", "content": f"User: {user_text}\nAssistant: {assistant_text}"},
    ]
    summ = (llm.invoke(doc).content or "").strip()
    if not summ:
        return None

    key = str(uuid.uuid4())
    value = {
        "text": summ,
        "type": "episodic",
        "source_thread": thread_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        store.put(ns_episodic(user_id), key=key, value=value, index=["text"])
    except Exception:
        return None
    return summ