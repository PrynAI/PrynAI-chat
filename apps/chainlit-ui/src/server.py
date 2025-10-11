# apps/chainlit-ui/src/server.py
from __future__ import annotations

import os
from typing import Optional, Dict, List
from importlib.resources import files as pkg_files

import chainlit as cl
from chainlit.utils import mount_chainlit
from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

"""
FastAPI parent app for Chainlit with MSAL login page:

  • /auth        → serves MSAL SPA (static files)
  • /auth/token  → accepts {"access_token": "..."} and sets an HttpOnly cookie
  • /chat        → Chainlit mounted under FastAPI

Why these changes:
- Starlette's StaticFiles checks the directory exists at startup and will crash
  the app if it doesn't. We resolve the path robustly (package resources or env).
- Chainlit's mount expects a *filesystem path* to the entry file; when packaged,
  we resolve it with importlib.resources so it works from site-packages.
Docs: StaticFiles check, Chainlit FastAPI + header auth, importlib.resources. 
"""

APP_COOKIE = "prynai_at"

app = FastAPI(title="PrynAI Chat UI (with MSAL)")

# ---------- Static assets (/auth) ----------
def _find_auth_dir() -> str:
    """
    Resolve the directory that contains the MSAL SPA assets.
    Order:
      1) AUTH_DIR env (explicit override)
      2) packaged path:   pkg_files('src') / 'auth'      (wheel install)
      3) dev fallbacks:   ../auth   or   ./auth          (repo layout)
    """
    candidates: List[str] = []
    env_dir = os.getenv("AUTH_DIR")
    if env_dir:
        candidates.append(env_dir)

    # Package resource (works when the project is installed as a wheel)
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
# Starlette verifies the directory exists up-front (failing fast if not). :contentReference[oaicite:4]{index=4}
app.mount("/auth", StaticFiles(directory=AUTH_DIR, html=True), name="auth")


@app.get("/")
def _root():
    # If users hit the root, nudge them to the chat app.
    return RedirectResponse(url="/chat/")

@app.post("/auth/token")
async def _save_token(body: Dict[str, str], response: Response):
    """
    Receives { "access_token": "<JWT>" } from the MSAL SPA and sets an
    HttpOnly cookie. The Gateway still fully verifies the JWT.
    """
    tok = (body or {}).get("access_token")
    if not tok:
        return JSONResponse({"ok": False, "error": "missing_token"}, status_code=400)

    response.set_cookie(
        key=APP_COOKIE,
        value=tok,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,  # align with your API access token TTL
        path="/",
    )
    return {"ok": True}

@app.post("/auth/logout")
async def _logout(response: Response):
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
    """
    Chainlit calls this with the request headers; we read the HttpOnly cookie
    and stash the token into cl.user_session so your chat handler can forward it
    to the Gateway. See Chainlit's header auth + FastAPI mounting docs. :contentReference[oaicite:5]{index=5}
    """
    cookie = headers.get("cookie") or headers.get("Cookie")
    token = _parse_cookies(cookie).get(APP_COOKIE)
    if not token:
        return None
    cl.user_session.set("access_token", token)
    # You could decode the JWT for a display name; we keep it minimal here.
    return cl.User(identifier="extern-id-user", metadata={"src": "cookie"})

# ---------- Mount Chainlit at /chat ----------
def _find_chainlit_target() -> str:
    """
    Resolve the absolute file path to the Chainlit entry file.
    Order:
      1) packaged: pkg_files('src') / 'main.py'
      2) dev fallbacks: ../main.py or ./main.py
    """
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
# Chainlit expects a *file path* for target when mounted under FastAPI. :contentReference[oaicite:6]{index=6}
mount_chainlit(app=app, target=CHAINLIT_TARGET, path="/chat")