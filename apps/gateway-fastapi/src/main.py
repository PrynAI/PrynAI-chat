# apps/gateway-fastapi/src/main.py
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import AsyncGenerator
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

@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})

@app.post("/api/chat/stream")
async def stream_chat(payload: ChatIn, request: Request):
    user_msg = {"role": "user", "content": payload.message}
    config = {"configurable": {"thread_id": payload.thread_id}} if payload.thread_id else {}

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            # Ask LangGraph for token-level streaming
            async for msg_chunk, meta in remote.astream(
                {"messages": [user_msg]},
                config=config,
                stream_mode="messages",   # stream at message chunk level
            ):
                # msg_chunk can be an AIMessageChunk (has .content) or dict-like
                content = getattr(msg_chunk, "content", None)
                if content is None and isinstance(msg_chunk, dict):
                    content = msg_chunk.get("content")

                if content:
                    # SSE: send one data line per token-ish chunk
                    yield f"data: {content}\n\n".encode("utf-8")

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