# apps/chainlit-ui/src/server.py
from __future__ import annotations

import os
from typing import Optional, Dict
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse

from chainlit.utils import mount_chainlit
import chainlit as cl

# --- FastAPI parent that hosts:
#  • /auth static SPA (MSAL)
#  • /auth/token to set HttpOnly cookie with the CIAM access token
#  • /chat  -> the Chainlit app (mounted)
#
# Why header auth? Chainlit recommends delegating auth to the parent FastAPI app when mounted. 
# We read the token from the Cookie header and set cl.user_session["access_token"].

APP_COOKIE = "prynai_at"

app = FastAPI(title="PrynAI Chat UI (with MSAL)")

# 1) Serve the MSAL SPA under /auth
AUTH_DIR = os.path.join(os.path.dirname(__file__), "..", "auth")
app.mount("/auth", StaticFiles(directory=AUTH_DIR, html=True), name="auth")

@app.get("/")
def _root():
    # Nice landing: if cookie is set, go to chat; otherwise go to /auth
    return RedirectResponse(url="/chat/")

@app.post("/auth/token")
async def _save_token(body: Dict[str, str], response: Response):
    tok = (body or {}).get("access_token")
    if not tok:
        return JSONResponse({"ok": False, "error": "missing_token"}, status_code=400)
    # Set HttpOnly cookie; the gateway will still verify JWT signature & audience.
    response.set_cookie(
        key=APP_COOKIE,
        value=tok,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,  # match your API access token lifetime
        path="/",
    )
    return {"ok": True}

@app.post("/auth/logout")
async def _logout(response: Response):
    response.delete_cookie(APP_COOKIE, path="/")
    return {"ok": True}

# 2) Chainlit header auth callback: parse Cookie header to identify user + stash token
def _parse_cookies(cookie_header: Optional[str]) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    if not cookie_header:
        return cookies
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

@cl.header_auth_callback
def header_auth_callback(headers: Dict[str, str]) -> Optional[cl.User]:
    cookie = headers.get("cookie") or headers.get("Cookie")
    jar = _parse_cookies(cookie)
    token = jar.get(APP_COOKIE)
    if not token:
        return None
    # Keep it simple: gateway will do full verification. We stash the token in the session.
    cl.user_session.set("access_token", token)
    # Provide a stable id (unverified here) to let Chainlit show a name. You can decode JWT for name if you want.
    return cl.User(identifier="extern-id-user", metadata={"src": "cookie"})

# 3) Mount chainlit at /chat (subpath). The target is your existing app's entry.
mount_chainlit(app=app, target="src/main.py", path="/chat")