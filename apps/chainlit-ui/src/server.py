# apps/chainlit-ui/src/server.py
from __future__ import annotations

import os
from typing import Optional, Dict, List
from importlib.resources import files as pkg_files

import chainlit as cl
from chainlit.utils import mount_chainlit
from fastapi import FastAPI, Response, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_COOKIE = "prynai_at"
TOKEN_API = "/_auth/token"
LOGOUT_API = "/_auth/logout"

app = FastAPI(title="PrynAI Chat UI (with MSAL)")

# ---------- Static assets (/auth) ----------
def _find_auth_dir() -> str:
    candidates: List[str] = []
    if os.getenv("AUTH_DIR"):
        candidates.append(os.getenv("AUTH_DIR"))
    try:
        candidates.append(str(pkg_files("src").joinpath("auth")))
    except Exception:
        pass
    base = os.path.dirname(__file__)
    candidates += [
        os.path.abspath(os.path.join(base, "..", "auth")),
        os.path.abspath(os.path.join(base, "auth")),
    ]
    for p in candidates:
        if p and os.path.isdir(p):
            return p
    raise RuntimeError(f"Auth assets not found. Tried: {candidates}")

AUTH_DIR = _find_auth_dir()
# Mounted static app owns all subpaths of /auth (by design).
app.mount("/auth", StaticFiles(directory=AUTH_DIR, html=True), name="auth")

@app.get("/")
def _root():
    return RedirectResponse(url="/chat/")

# ---------- Token bridge API (NOT under /auth) ----------
@app.post(TOKEN_API)
async def save_token(body: Dict[str, str], response: Response):
    tok = (body or {}).get("access_token")
    if not tok:
        return JSONResponse({"ok": False, "error": "missing_token"}, status_code=400)
    response.set_cookie(
        key=APP_COOKIE, value=tok, httponly=True, secure=True,
        samesite="lax", max_age=3600, path="/",
    )
    return {"ok": True}

@app.post(LOGOUT_API)
async def logout(response: Response):
    response.delete_cookie(APP_COOKIE, path="/")
    return {"ok": True}

# ---------- Chainlit header-auth bridge ----------
def _parse_cookies(cookie_header: Optional[str]) -> Dict[str, str]:
    jar: Dict[str, str] = {}
    if not cookie_header:
        return jar
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            jar[k.strip()] = v.strip()
    return jar

@cl.header_auth_callback
def header_auth_callback(headers: Dict[str, str]) -> Optional[cl.User]:
    cookie = headers.get("cookie") or headers.get("Cookie")
    token = _parse_cookies(cookie).get(APP_COOKIE)
    if not token:
        return None
    cl.user_session.set("access_token", token)
    return cl.User(identifier="extern-id-user", metadata={"src": "cookie"})

# ---------- Mount Chainlit at /chat ----------
def _find_chainlit_target() -> str:
    candidates: List[str] = []
    try:
        candidates.append(str(pkg_files("src").joinpath("main.py")))
    except Exception:
        pass
    base = os.path.dirname(__file__)
    candidates += [
        os.path.abspath(os.path.join(base, "..", "main.py")),
        os.path.abspath(os.path.join(base, "main.py")),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise RuntimeError(f"Chainlit entry file not found. Tried: {candidates}")

CHAINLIT_TARGET = _find_chainlit_target()
mount_chainlit(app=app, target=CHAINLIT_TARGET, path="/chat")
