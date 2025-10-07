# apps/gateway-fastapi/src/main.py
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

def _flatten_content(content: Any) -> str:
    """Coerce LangChain/LangGraph content into plain text."""
    # 1) Simple string
    if isinstance(content, str):
        return content
    # 2) List of content blocks (standard)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                # text blocks are common; fall back to other typical keys
                t = block.get("text") or block.get("input_text") or block.get("output_text")
            else:
                # some providers expose objects with a .text attribute
                t = getattr(block, "text", None)
            if t:
                parts.append(t)
        return "".join(parts)
    # 3) AIMessageChunk or similar with .content and sometimes .additional_kwargs
    c = getattr(content, "content", None)
    if c:
        return _flatten_content(c)
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
            # Token-level streaming from the remote graph
            async for msg_chunk, meta in remote.astream(
                {"messages": [user_msg]},
                config=config,
                stream_mode="messages",
            ):
                # msg_chunk is an AIMessageChunk-like object
                text = _flatten_content(getattr(msg_chunk, "content", None))
                if text:
                    yield f"data: {text}\n\n".encode("utf-8")
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n".encode("utf-8")
        finally:
            yield b"event: done\ndata: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)
