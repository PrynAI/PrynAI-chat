# apps/gateway-fastapi/src/main.py
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from typing import AsyncGenerator, Any
import os, json, time

from langgraph.pregel.remote import RemoteGraph
from langgraph_sdk import get_client

# OpenAI Moderation
from openai import OpenAI

#  feature module
from src.features.websearch import ChatIn, build_langgraph_config

# ---------- FastAPI app ----------
app = FastAPI()

# ---------- Moderation config ----------
OAI = OpenAI()
MOD_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
MOD_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

# ---------- LangGraph remote config ----------
LANGGRAPH_URL = os.environ["LANGGRAPH_URL"]
GRAPH_NAME = os.environ.get("LANGGRAPH_GRAPH", "chat")

client = get_client(url=LANGGRAPH_URL)
remote = RemoteGraph(GRAPH_NAME, client=client)

def _blocks_to_text(blocks: Any) -> str:
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
    c = getattr(chunk, "content", None)
    if c is not None:
        return _blocks_to_text(c)
    if isinstance(chunk, dict):
        if "content" in chunk:
            return _blocks_to_text(chunk["content"])
        if "delta" in chunk:
            d = chunk["delta"]
            if isinstance(d, dict):
                return _blocks_to_text(d.get("content") or d.get("text") or d)
            return _blocks_to_text(d)
        if "messages" in chunk and chunk["messages"]:
            m = chunk["messages"][-1]
            if isinstance(m, dict):
                return _blocks_to_text(m.get("content", m))
            return _blocks_to_text(getattr(m, "content", m))
    if isinstance(chunk, str):
        return chunk
    return ""

CRISIS_MSG = (
    "I'm really sorry you're feeling this way. I can't assist with anything that could harm you, "
    "but you deserve support. If you're in immediate danger, please contact local emergency services. "
    "If you want supportive resources, tell me your country/region and I can share crisis options."
)

def _is_self_harm_categories(categories: Any) -> bool:
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
    if not MOD_ENABLED:
        return {"flagged": False}
    resp = OAI.moderations.create(model=MOD_MODEL, input=text)
    result = resp.results[0]
    if result.flagged:
        print(json.dumps({"type": "moderation_input_flag"}), flush=True)
        raise ValueError("blocked_by_moderation")
    return {"flagged": False}

@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})

@app.post("/api/chat/stream")
async def stream_chat(payload: ChatIn, request: Request):
    user_msg = {"role": "user", "content": payload.message}
    config = build_langgraph_config(payload)  # <-- NEW

    if MOD_ENABLED:
        try:
            _moderate_or_raise(payload.message)
        except ValueError:
            async def blocked():
                yield b"event: policy\n"
                yield b"data: Your message appears unsafe. I can't help with that.\n\n"
                yield b"event: done\n"
                yield b"data: [DONE]\n\n"
            return StreamingResponse(blocked(), media_type="text/event-stream")

    acc: list[str] = []

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            async for item in remote.astream(
                {"messages": [user_msg]},
                config=config,
                stream_mode="messages",
            ):
                msg_chunk = item[0] if isinstance(item, tuple) and len(item) == 2 else item
                text = _chunk_to_text(msg_chunk)
                if text:
                    acc.append(text)
                    safe = text.replace("\r\n", "\n").replace("\r", "\n")
                    for line in safe.split("\n"):
                        yield f"data: {line}\n\n".encode("utf-8")

            if MOD_ENABLED and acc:
                try:
                    out = "".join(acc)
                    r = OAI.moderations.create(model=MOD_MODEL, input=out).results[0]
                    if r.flagged:
                        yield b"event: policy\n"
                        yield b"data: A safety filter replaced part of the output.\n\n"
                except Exception:
                    pass
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n".encode("utf-8")
        finally:
            yield b"event: done\n"
            yield b"data: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)
