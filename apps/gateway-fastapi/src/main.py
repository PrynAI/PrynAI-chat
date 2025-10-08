from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import AsyncGenerator, Any
import os, json, time

from langgraph.pregel.remote import RemoteGraph
from langgraph_sdk import get_client

# OpenAI Moderation (modern SDK)
from openai import OpenAI

# ---------- Moderation config ----------
OAI = OpenAI()  # Reads OPENAI_API_KEY from env (Key Vault -> SecretRef -> env)
MOD_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
MOD_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

# ---------- FastAPI app ----------
app = FastAPI()

# ---------- LangGraph remote config ----------
LANGGRAPH_URL = os.environ["LANGGRAPH_URL"]
GRAPH_NAME = os.environ.get("LANGGRAPH_GRAPH", "chat")

client = get_client(url=LANGGRAPH_URL)
remote = RemoteGraph(GRAPH_NAME, client=client)

# ---------- Models ----------
class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None

# ---------- Helpers: flatten LangChain/LangGraph content to text ----------
def _blocks_to_text(blocks: Any) -> str:
    """Flatten LangChain content blocks to a plain string."""
    if isinstance(blocks, str):
        return blocks
    if isinstance(blocks, list):
        parts: list[str] = []
        for b in blocks:
            if isinstance(b, dict):
                t = b.get("text") or b.get("input_text") or b.get("output_text")
            else:
                t = getattr(b, "text", None)
            if t:
                parts.append(t)
        return "".join(parts)
    return ""

def _chunk_to_text(chunk: Any) -> str:
    """
    Coerce whatever LangGraph gives us to a plain text token:
    - AIMessageChunk-like object with .content
    - dict serialized across RemoteGraph with keys like 'content' or 'messages' or 'delta'
    - plain string (rare)
    """
    # 1) AIMessageChunk or similar with .content
    c = getattr(chunk, "content", None)
    if c is not None:
        return _blocks_to_text(c)

    # 2) Dict representations from RemoteGraph
    if isinstance(chunk, dict):
        if "content" in chunk:  # direct content list/string
            return _blocks_to_text(chunk["content"])
        if "delta" in chunk:    # some providers use delta objects
            d = chunk["delta"]
            if isinstance(d, dict):
                return _blocks_to_text(d.get("content") or d.get("text") or d)
            return _blocks_to_text(d)
        if "messages" in chunk and chunk["messages"]:
            m = chunk["messages"][-1]
            if isinstance(m, dict):
                return _blocks_to_text(m.get("content", m))
            return _blocks_to_text(getattr(m, "content", m))

    # 3) Fallback: raw string
    if isinstance(chunk, str):
        return chunk

    return ""

# ---------- Helpers: moderation & crisis routing ----------
CRISIS_MSG = (
    "I'm really sorry you're feeling this way. I can't assist with anything that could harm you, "
    "but you deserve support. If you're in immediate danger, please contact local emergency services. "
    "If you want supportive resources, tell me your country/region and I can share crisis options."
)

def _is_self_harm_categories(categories: Any) -> bool:
    """Detect self-harm categories across naming variants."""
    # categories can be an object or dict depending on SDK repr
    def _get(k: str) -> bool:
        if isinstance(categories, dict):
            return bool(categories.get(k, False))
        return bool(getattr(categories, k.replace("-", "_").replace("/", "_"), False))

    keys = [
        "self-harm", "self-harm/intent", "self-harm/instructions",
        "self_harm", "self_harm_intent", "self_harm_instructions",
    ]
    return any(_get(k) for k in keys)

def _moderate_or_raise(text: str) -> dict:
    """Run moderation. Return result dict when OK; raise ValueError if flagged."""
    if not MOD_ENABLED:
        return {"flagged": False}
    resp = OAI.moderations.create(model=MOD_MODEL, input=text)
    result = resp.results[0]
    if result.flagged:
        cats = result.categories
        # Log a compact JSON line for observability
        print(json.dumps({
            "type": "moderation_input_flag",
            "ts": round(time.time(), 3),
            "categories": getattr(cats, "__dict__", cats),
        }), flush=True)
        raise ValueError("blocked_by_moderation")
    return {"flagged": False}

# ---------- Health ----------
@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})

# ---------- Streaming chat with guardrails ----------
@app.post("/api/chat/stream")
async def stream_chat(payload: ChatIn, request: Request):
    """SSE: input moderation -> stream model tokens -> (optional) output moderation -> [DONE]"""
    user_msg = {"role": "user", "content": payload.message}
    config = {"configurable": {"thread_id": payload.thread_id}} if payload.thread_id else {}

    # ---- Input moderation (pre-LLM) ----
    if MOD_ENABLED:
        try:
            _moderate_or_raise(payload.message)
        except ValueError:
            # Short-circuit with a policy event and a supportive message (crisis-aware)
            async def blocked():
                yield b"event: policy\n"
                try:
                    r = OAI.moderations.create(model=MOD_MODEL, input=payload.message).results[0]
                    if _is_self_harm_categories(r.categories):
                        yield f"data: {CRISIS_MSG}\n\n".encode("utf-8")
                    else:
                        yield b"data: Your message appears unsafe. I can't help with that.\n\n"
                except Exception:
                    yield b"data: Your message appears unsafe. I can't help with that.\n\n"
                yield b"event: done\n"
                yield b"data: [DONE]\n\n"
            return StreamingResponse(blocked(), media_type="text/event-stream")

    # ---- Stream tokens from LangGraph; accumulate for a final (post) check ----
    acc: list[str] = []

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            async for item in remote.astream(
                {"messages": [user_msg]},
                config=config,
                stream_mode="messages",
            ):
                # item is usually (message_chunk, metadata); handle both tuple/non-tuple
                if isinstance(item, tuple) and len(item) == 2:
                    msg_chunk, _meta = item
                else:
                    msg_chunk = item

                text = _chunk_to_text(msg_chunk)
                if text:
                    acc.append(text)
                    safe = text.replace("\r\n", "\n").replace("\r", "\n")
                    for line in safe.split("\n"):
                        yield f"data: {line}\n\n".encode("utf-8")

            # ---- Output moderation (post-LLM, final pass) ----
            # Note: This runs after streaming completes. If you need mid-stream checks,
            # you can re-check every N chars—but it increases cost/latency.
            if MOD_ENABLED and acc:
                try:
                    out = "".join(acc)
                    r = OAI.moderations.create(model=MOD_MODEL, input=out).results[0]
                    if r.flagged:
                        yield b"event: policy\n"
                        if _is_self_harm_categories(r.categories):
                            yield f"data: {CRISIS_MSG}\n\n".encode("utf-8")
                        else:
                            yield b"data: A safety filter replaced part of the output.\n\n"
                except Exception as e:
                    # Don't fail the response if the post-check errors
                    print(json.dumps({"type": "moderation_output_error", "err": str(e)}), flush=True)

        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n".encode("utf-8")
        finally:
            yield b"event: done\n"
            yield b"data: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # avoid proxy buffering
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)
