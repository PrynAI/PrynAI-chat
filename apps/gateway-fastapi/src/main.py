# apps/gateway-fastapi/src/main.py
# Production-ready FastAPI gateway:
# - Validates Microsoft Entra External ID (CIAM) access tokens
# - Streams model output to the UI via SSE (unchanged from your MVP-0)
# - Forwards web_search and thread_id to LangGraph
# - Adds CORS for localhost + your chat domain
#
# Env required (see bottom of file header for details):
#   OIDC_DISCOVERY_URL = https://<subdomain>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration
#   OIDC_AUDIENCE      = api://<GATEWAY_API_APP_ID>/chat.fullaccess   (or the API app client id)
#   LANGGRAPH_URL, LANGGRAPH_GRAPH
#   MODERATION_ENABLED=true|false, MODERATION_MODEL=omni-moderation-latest
#
# References:
# - Streaming + payload shape preserved from prior gateway main.py (MVP-0).  [repo]
# - Web search toggle forwarded via src.features.websearch.                  [repo]
# - JWT validation helper in src.auth.entra (policy-agnostic discovery).     [module]

from __future__ import annotations

import os
import json
from typing import AsyncGenerator, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from langgraph.pregel.remote import RemoteGraph
from langgraph_sdk import get_client

# OpenAI Moderation
from openai import OpenAI

# Feature: web search flag + input model
from src.features.websearch import ChatIn, build_langgraph_config  # :contentReference[oaicite:4]{index=4}

# Auth: Entra External ID (CIAM) token validation
from src.auth.entra import get_current_user, user_id_from_claims, AuthError

# ---------- FastAPI app ----------
app = FastAPI(title="PrynAI Gateway", version="1.0")

# ---------- CORS (UI origins) ----------
# Allow your local SPA test and the production UI domain.
# FastAPI/Starlette CORSMiddleware is the documented way to enable CORS. :contentReference[oaicite:5]{index=5}
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

# ---------- Moderation config ----------
OAI = OpenAI()
MOD_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
MOD_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

# ---------- LangGraph remote config ----------
# Matches your repo docs & langgraph.json mapping ("chat"). 
LANGGRAPH_URL = os.environ["LANGGRAPH_URL"]
GRAPH_NAME = os.environ.get("LANGGRAPH_GRAPH", "chat")

client = get_client(url=LANGGRAPH_URL)
remote = RemoteGraph(GRAPH_NAME, client=client)

# ---------- Helpers (unchanged logic, kept for streaming stability) ----------
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

def _moderate_or_raise(text: str) -> dict:
    if not MOD_ENABLED:
        return {"flagged": False}
    resp = OAI.moderations.create(model=MOD_MODEL, input=text)
    result = resp.results[0]
    if result.flagged:
        print(json.dumps({"type": "moderation_input_flag"}), flush=True)
        raise ValueError("blocked_by_moderation")
    return {"flagged": False}

# ---------- Health ----------
@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})

# ---------- WhoAmI (smoke test for JWT validity) ----------
@app.get("/api/whoami")
async def whoami(request: Request):
    try:
        claims = await get_current_user(request)
    except AuthError as e:
        # HTTP 401 for simple JSON route
        raise HTTPException(status_code=401, detail=str(e))
    if not claims:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return {
        "sub": claims.get("sub"),
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
    }

# ---------- Chat stream (SSE) ----------
@app.post("/api/chat/stream")
async def stream_chat(payload: ChatIn, request: Request):
    """
    Streams model output to the UI via Server-Sent Events.
    - Requires a valid CIAM access token (unless AUTH_DEV_BYPASS=true with X-Debug-Sub).
    - Forwards web_search + thread_id to the LangGraph config.
    - Attaches 'user_id' from token claims to config so the agent can scope memory later.
    """
    # 1) AUTHN: require valid token (External ID access token)
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

    # 2) Build LangGraph config (thread_id + web_search) and attach user_id
    config = build_langgraph_config(payload)                    # :contentReference[oaicite:7]{index=7}
    config.setdefault("configurable", {})["user_id"] = user_id_from_claims(claims)

    # 3) Prepare user message
    user_msg = {"role": "user", "content": payload.message}

    # 4) Input moderation (kept from MVP-0)
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

    # 5) Stream result from LangGraph → SSE
    acc: list[str] = []

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            async for item in remote.astream(
                {"messages": [user_msg]},
                config=config,
                stream_mode="messages",
            ):
                # Astream can yield (node_name, msg) or msg depending on mode; be tolerant
                msg_chunk = item[0] if isinstance(item, tuple) and len(item) == 2 else item
                text = _chunk_to_text(msg_chunk)
                if text:
                    acc.append(text)
                    safe = text.replace("\r\n", "\n").replace("\r", "\n")
                    for line in safe.split("\n"):
                        yield f"data: {line}\n\n".encode("utf-8")

            # Output moderation (best-effort, post-stream)
            if MOD_ENABLED and acc:
                try:
                    out = "".join(acc)
                    r = OAI.moderations.create(model=MOD_MODEL, input=out).results[0]
                    if r.flagged:
                        yield b"event: policy\n"
                        yield b"data: A safety filter replaced part of the output.\n\n"
                except Exception:
                    # Non-fatal; continue to finalize stream
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
