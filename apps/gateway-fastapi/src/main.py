# apps/gateway-fastapi/src/main.py
from __future__ import annotations

import os
import json
from typing import AsyncGenerator, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from langgraph.pregel.remote import RemoteGraph
from langgraph_sdk import get_client

from openai import OpenAI

from src.features.websearch import ChatIn, build_langgraph_config
from src.features.profiles import make_profiles_router, ensure_profile
from src.features.threads import make_threads_router
from src.features.transcript import (
    make_transcript_router,
    append_transcript,
    TranscriptMessage,
)
from src.auth.entra import get_current_user, user_id_from_claims, AuthError

app = FastAPI(title="PrynAI Gateway", version="1.3")

# ---- CORS --------------------------------------------------------------------

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://chat.prynai.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Moderation --------------------------------------------------------------

OAI = OpenAI()
MOD_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
MOD_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

# ---- LangGraph client --------------------------------------------------------

LANGGRAPH_URL = os.environ["LANGGRAPH_URL"]
GRAPH_NAME = os.environ.get("LANGGRAPH_GRAPH", "chat")

client = get_client(url=LANGGRAPH_URL)
remote = RemoteGraph(GRAPH_NAME, client=client)

# ---- Routers -----------------------------------------------------------------

app.include_router(make_profiles_router(client, get_current_user, user_id_from_claims))
app.include_router(make_threads_router(client, get_current_user, user_id_from_claims))
app.include_router(make_transcript_router(client, get_current_user, user_id_from_claims))

# Optional uploads router (if present)
try:
    from src.features.uploads import make_uploads_router  # type: ignore
    app.include_router(make_uploads_router(get_current_user, user_id_from_claims))
except Exception:
    pass


# ---- Helpers to extract text from streamed LangGraph items -------------------

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

# ---- SSE framing (spec-compliant) -------------------------------------------

def _sse_event_from_text(text: str) -> bytes:
    """
    Build one SSE event for a whole text chunk.
    - Normalize to '\n'
    - Emit multiple 'data:' lines inside a single event to preserve line breaks
      (per SSE spec: consecutive 'data:' lines are joined with '\n').
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    payload = "data: " + t.replace("\n", "\ndata: ")
    return (payload + "\n\n").encode("utf-8")  # blank line ends the event (spec)
# Spec refs: MDN + WHATWG. :contentReference[oaicite:6]{index=6}

# ---- Health & identity -------------------------------------------------------

@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})

@app.get("/api/whoami")
async def whoami(request: Request):
    try:
        claims = await get_current_user(request)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    if not claims:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return {"sub": claims.get("sub"), "iss": claims.get("iss"), "aud": claims.get("aud")}

def _moderate_or_raise(text: str) -> dict:
    if not MOD_ENABLED:
        return {"flagged": False}
    resp = OAI.moderations.create(model=MOD_MODEL, input=text)
    result = resp.results[0]
    if result.flagged:
        print(json.dumps({"type": "moderation_input_flag"}), flush=True)
        raise ValueError("blocked_by_moderation")
    return {"flagged": False}

# ---- Chat streaming ----------------------------------------------------------

@app.post("/api/chat/stream")
async def stream_chat(payload: ChatIn, request: Request):
    # 1) AUTHN
    try:
        claims = await get_current_user(request)
    except AuthError as e:
        async def auth_error_stream():
            yield b"event: error\n"
            yield f"data: auth_error:{str(e)}\n\n".encode("utf-8")
            yield b"event: done\n"
            yield b"data: [DONE]\n\n"
        return StreamingResponse(auth_error_stream(), media_type="text/event-stream")

    if not claims:
        async def noauth_stream():
            yield b"event: error\n"
            yield b"data: unauthenticated\n\n"
            yield b"event: done\n"
            yield b"data: [DONE]\n\n"
        return StreamingResponse(noauth_stream(), media_type="text/event-stream")

    user_id = user_id_from_claims(claims)

    # 2) Build LangGraph config (thread_id + web_search); attach user_id for agent-side scoping.
    config = build_langgraph_config(payload)
    config.setdefault("configurable", {})["user_id"] = user_id

    # 2b) Ensure a profile exists (best-effort)
    try:
        await ensure_profile(client, user_id, claims=claims)
    except Exception:
        pass

    # 3) Prepare user message
    user_msg = {"role": "user", "content": payload.message}

    # 4) Input moderation (unchanged)
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
    thread_id = (config.get("configurable") or {}).get("thread_id")

    # NEW: resolve a thread id if still missing (defensive)
    if not thread_id:
        try:
            # Try newest for this user
            results = await client.threads.search(metadata={"user_id": user_id}, limit=1)
            if results:
                thread_id = results[0]["thread_id"]
            else:
                created = await client.threads.create(metadata={"user_id": user_id})
                thread_id = created["thread_id"]
            config.setdefault("configurable", {})["thread_id"] = thread_id
        except Exception:
            # If this ever fails, we still stream the model but skip transcript write
            thread_id = None

    # Write the user turn immediately so it shows after reload
    if thread_id:
        try:
            await append_transcript(
                client, user_id, thread_id,
                TranscriptMessage(role="user", content=payload.message)
            )
        except Exception as e:
            print(json.dumps({"type": "transcript_write_error", "when": "user", "tid": thread_id, "err": str(e)}), flush=True)

    async def event_gen():
        try:
            async for item in remote.astream({"messages": [user_msg]}, config=config, stream_mode="messages"):
                msg_chunk = item[0] if isinstance(item, tuple) and len(item) == 2 else item
                text = _chunk_to_text(msg_chunk)
                if text:
                    acc.append(text)
                    yield _sse_event_from_text(text)

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
            if thread_id and acc:
                try:
                    await append_transcript(
                        client, user_id, thread_id,
                        TranscriptMessage(role="assistant", content="".join(acc))
                    )
                except Exception as e:
                    print(json.dumps({"type": "transcript_write_error", "when": "assistant", "tid": thread_id, "err": str(e)}), flush=True)
            yield b"event: done\n"
            yield b"data: [DONE]\n\n"

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)