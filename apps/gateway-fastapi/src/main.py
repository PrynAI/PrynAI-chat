# apps/gateway-fastapi/src/main.py
import os
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import AsyncGenerator
from langgraph.pregel.remote import RemoteGraph
from langgraph_sdk import get_client

app = FastAPI()

LANGGRAPH_URL = os.environ["https://chat-prynai-ba72941c6b695692a635ca6f42fb57b4.us.langgraph.app"]  # e.g. https://<your-deployment>
GRAPH_NAME = os.environ.get("LANGGRAPH_GRAPH", "chat")

# RemoteGraph can be created via URL or client; we’ll use client for async stream
client = get_client(url=LANGGRAPH_URL)
remote = RemoteGraph(GRAPH_NAME, client=client)

class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None  # enable persistence later

@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})

@app.post("/api/chat/stream")
async def stream_chat(payload: ChatIn, request: Request):
    """Streams model tokens as SSE (text/event-stream)"""
    user_msg = {"role": "user", "content": payload.message}
    config = {}
    if payload.thread_id:
        config = {"configurable": {"thread_id": payload.thread_id}}

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in remote.astream({"messages": [user_msg]}, config=config):
                # “chunk” objects vary; we’ll pull any delta text safely
                text = ""
                if isinstance(chunk, dict):
                    # look for message deltas from LangGraph
                    msg = chunk.get("messages") or chunk.get("output")
                    if isinstance(msg, list) and msg:
                        part = msg[-1]
                        if isinstance(part, dict):
                            text = part.get("content", "") or ""
                if text:
                    yield f"data: {text}\n\n".encode("utf-8")

            # signal completion
            yield b"event: done\ndata: [DONE]\n\n"
        except Exception as e:
            # SSE-friendly error
            err = f'event: error\ndata: {str(e)}\n\n'
            yield err.encode("utf-8")

    return StreamingResponse(event_gen(), media_type="text/event-stream")
