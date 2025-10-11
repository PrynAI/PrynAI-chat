# apps/chainlit-ui/src/server.py
from __future__ import annotations

import os, json, base64
from typing import Optional, Dict, List
from importlib.resources import files as pkg_files

import chainlit as cl
from chainlit.utils import mount_chainlit
from fastapi import FastAPI, Response, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from http.cookies import SimpleCookie

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
# Serve our MSAL SPA at /auth (and all its subpaths)
app.mount("/auth", StaticFiles(directory=AUTH_DIR, html=True), name="auth")

@app.get("/")
def _root():
    # Always land on the chat
    return RedirectResponse(url="/chat/")

# ---------- Token bridge API (NOT under /auth) ----------
@app.post(TOKEN_API)
async def save_token(body: Dict[str, str], response: Response):
    tok = (body or {}).get("access_token")
    if not tok:
        return JSONResponse({"ok": False, "error": "missing_token"}, status_code=400)
    response.set_cookie(
        key=APP_COOKIE,
        value=tok,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
        path="/",
    )
    return {"ok": True}

@app.post(LOGOUT_API)
async def logout(response: Response):
    # Clear our HttpOnly access-token cookie
    response.delete_cookie(APP_COOKIE, path="/")
    return {"ok": True}

# ---------- Helpers ----------
def _parse_cookies(cookie_header: Optional[str]) -> Dict[str, str]:
    c = SimpleCookie()
    c.load(cookie_header or "")
    return {k: morsel.value for k, morsel in c.items()}

def _jwt_claims_unverified(token: str) -> Dict[str, str]:
    """
    Decode JWT payload without verifying signature. Good enough to read display claims.
    Access token is already validated by the Gateway on API calls.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}

# ---------- Chainlit header-auth bridge ----------
@cl.header_auth_callback
def header_auth_callback(headers: Dict[str, str]) -> Optional[cl.User]:
    """
    Called by Chainlit on auth checks. Return a cl.User if authenticated; None to fail.
    Docs: https://docs.chainlit.io/authentication/header
    """
    cookie = headers.get("cookie") or headers.get("Cookie")
    has_cookie = cookie and (f"{APP_COOKIE}=" in cookie)
    print(f"[auth] header_auth_callback: has_cookie={bool(has_cookie)}", flush=True)

    token = _parse_cookies(cookie).get(APP_COOKIE)
    if not token:
        return None

    claims = _jwt_claims_unverified(token)
    # Prefer human-friendly identifier for the top-right UI
    identifier = (
        claims.get("name")
        or claims.get("email")
        or claims.get("preferred_username")
        or claims.get("sub")
        or "user"
    )

    # Attach access token + useful claims to metadata so handlers can use them.
    meta = {
        "src": "cookie",
        "access_token": token,
        "sub": claims.get("sub"),
        "name": claims.get("name"),
        "email": claims.get("email"),
        "preferred_username": claims.get("preferred_username"),
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
    }

    return cl.User(identifier=identifier, metadata=meta)

# Clear our cookie when the built-in Chainlit logout is used.
# Docs: https://docs.chainlit.io/api-reference/lifecycle-hooks/on-logout
@cl.on_logout
async def _on_logout(request: Request, response: Response):
    response.delete_cookie(APP_COOKIE, path="/")

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
