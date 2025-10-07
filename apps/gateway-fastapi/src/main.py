from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import AsyncGenerator, Any
import os

from langgraph.pregel.remote import RemoteGraph
from langgraph_sdk import get_client

app = FastAPI()

LANGGRAPH_URL = os.environ["LANGGRAPH_URL"]
GRAPH_NAME = os.environ.get("LANGGRAPH_GRAPH", "chat")

client = get_client(url=LANGGRAPH_URL)
remote = RemoteGraph(GRAPH_NAME, client=client)

class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None

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
    # 1) AIMessageChunk or similar
    c = getattr(chunk, "content", None)
    if c is not None:
        return _blocks_to_text(c)

    # 2) Dict representations from RemoteGraph
    if isinstance(chunk, dict):
        if "content" in chunk:                # direct content list/string
            return _blocks_to_text(chunk["content"])
        if "delta" in chunk:                  # some providers use delta objects
            d = chunk["delta"]
            if isinstance(d, dict):
                return _blocks_to_text(d.get("content") or d.get("text") or d)
            return _blocks_to_text(d)
        if "messages" in chunk and chunk["messages"]:
            m = chunk["messages"][-1]
            # m may be dict or message-like object
            if isinstance(m, dict):
                return _blocks_to_text(m.get("content", m))
            return _blocks_to_text(getattr(m, "content", m))

    # 3) Fallback: raw string
    if isinstance(chunk, str):
        return chunk

    return ""

@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})

@app.post("/api/chat/stream")
async def stream_chat(payload: ChatIn, request: Request):
    user_msg = {"role": "user", "content": payload.message}
    config = {"configurable": {"thread_id": payload.thread_id}} if payload.thread_id else {}

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            # messages mode => (message_chunk, metadata) tuples with token deltas
            async for item in remote.astream(
                {"messages": [user_msg]},
                config=config,
                stream_mode="messages",
            ):
                # Debug: inspect raw stream item
                print("STREAM ITEM TYPE:", type(item))
                print("STREAM ITEM REPR:", repr(item)[:300], flush=True)


                # Handle both tuple and non-tuple shapes defensively
                if isinstance(item, tuple) and len(item) == 2:
                    msg_chunk, _meta = item
                else:
                    msg_chunk = item

                text = _chunk_to_text(msg_chunk)
                if text:
                    # Split embedded newlines per SSE spec (each line prefixed with data:)
                    safe = text.replace("\r\n", "\n").replace("\r", "\n")
                    for line in safe.split("\n"):
                        yield f"data: {line}\n\n".encode("utf-8")
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n".encode("utf-8")
        finally:
            yield b"event: done\ndata: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # avoid proxy buffering; recommended in SSE guides
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)
