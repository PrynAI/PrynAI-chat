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
app.mount("/auth", StaticFiles(directory=AUTH_DIR, html=True), name="auth")

@app.get("/")
def _root():
    return RedirectResponse(url="/chat/")

# ---------- Token bridge API ----------
@app.post(TOKEN_API)
async def save_token(body: Dict[str, str], response: Response):
    tok = (body or {}).get("access_token")
    if not tok:
        return JSONResponse({"ok": False, "error": "missing_token"}, status_code=400)

    domain = os.getenv("COOKIE_DOMAIN")  # e.g., "chat.prynai.com"
    response.set_cookie(
        key=APP_COOKIE,
        value=tok,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
        path="/",
        domain=domain if domain else None,
    )
    return {"ok": True}

@app.post(LOGOUT_API)
async def logout(response: Response):
    response.delete_cookie(APP_COOKIE, path="/")
    return {"ok": True}

# ---------- Helpers ----------
def _parse_cookies(cookie_header: Optional[str]) -> Dict[str, str]:
    c = SimpleCookie()
    c.load(cookie_header or "")
    return {k: morsel.value for k, morsel in c.items()}

def _jwt_claims_unverified(token: str) -> Dict[str, str]:
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
    cookie = headers.get("cookie") or headers.get("Cookie")
    token = _parse_cookies(cookie).get(APP_COOKIE) if cookie else None

    # Defensive: accept Bearer for the very first probe as well.
    if not token:
        authz = headers.get("authorization") or headers.get("Authorization")
        if authz and authz.lower().startswith("bearer "):
            token = authz.split(" ", 1)[1]

    print(f"[auth] header_auth_callback: has_cookie={bool(cookie and APP_COOKIE in (cookie or ''))}; "
          f"has_authz={'authorization' in {k.lower() for k in (headers or {}).keys()}}", flush=True)

    if not token:
        return None

    claims = _jwt_claims_unverified(token)
    identifier = (
        claims.get("name")
        or claims.get("email")
        or claims.get("preferred_username")
        or claims.get("sub")
        or "user"
    )
    meta = {
        "src": "cookie_or_header",
        "access_token": token,   # Chainlit stores this on cl.user_session["user"].metadata
        "sub": claims.get("sub"),
        "name": claims.get("name"),
        "email": claims.get("email"),
        "preferred_username": claims.get("preferred_username"),
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
    }
    return cl.User(identifier=identifier, metadata=meta)

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
