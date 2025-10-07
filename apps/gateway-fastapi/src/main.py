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
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            # block may be dict-like {'type': 'text', 'text': '...'} or an object with .text
            if isinstance(block, dict):
                t = block.get("text") or block.get("input_text") or block.get("output_text")
            else:
                t = getattr(block, "text", None)
            if t:
                parts.append(t)
        return "".join(parts)
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
            # ✅ token-level streaming from LangGraph
            async for msg_chunk, meta in remote.astream(
                {"messages": [user_msg]},
                config=config,
                stream_mode="messages",
            ):
                content = getattr(msg_chunk, "content", None)
                text = _flatten_content(content)
                if text:
                    # SSE requires text lines ending with \n\n
                    yield f"data: {text}\n\n".encode("utf-8")
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n".encode("utf-8")
        finally:
            yield b"event: done\ndata: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # avoid proxy buffering
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)
