# apps/chainlit-ui/src/server.py
from __future__ import annotations

import os, json, base64
from typing import Optional, Dict, List
from importlib.resources import files as pkg_files

import httpx
import chainlit as cl
from chainlit.utils import mount_chainlit
from fastapi import FastAPI, Response, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from http.cookies import SimpleCookie

APP_COOKIE = "prynai_at"   # HttpOnly Entra access token (from /auth)
TID_COOKIE = "prynai_tid"  # Active LangGraph thread id (UI-selected)
TOKEN_API = "/_auth/token"
LOGOUT_API = "/_auth/logout"
GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080").rstrip("/")

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
        key=APP_COOKIE, value=tok, httponly=True, secure=True, samesite="lax",
        max_age=3600, path="/", domain=domain if domain else None,
    )
    return {"ok": True}

@app.post(LOGOUT_API)
async def logout(response: Response):
    """Clear both the host-only and domain-scoped variants."""
    domain = os.getenv("COOKIE_DOMAIN") or None
    response.delete_cookie(APP_COOKIE, path="/")
    response.delete_cookie(TID_COOKIE, path="/")
    if domain:
        response.delete_cookie(APP_COOKIE, path="/", domain=domain)
        response.delete_cookie(TID_COOKIE, path="/", domain=domain)
    # Defensive overwrite
    response.set_cookie(key=APP_COOKIE, value="", httponly=True, secure=True,
                        samesite="lax", max_age=0, expires=0, path="/", domain=domain)
    response.set_cookie(key=TID_COOKIE, value="", httponly=False, secure=True,
                        samesite="lax", max_age=0, expires=0, path="/", domain=domain)
    return {"ok": True}

# ---------- Helpers ----------
def _parse_cookies(header: Optional[str]) -> Dict[str, str]:
    c = SimpleCookie()
    c.load(header or "")
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

def _bearer_from_request(request: Request) -> Optional[str]:
    token = _parse_cookies(request.headers.get("cookie")).get(APP_COOKIE)
    if token:
        return f"Bearer {token}"
    authz = request.headers.get("authorization")
    if authz and authz.lower().startswith("bearer "):
        return authz
    return None

# ---------- UI helper APIs (proxy to Gateway with cookie auth) ----------
@app.get("/ui/threads")
async def ui_list_threads(request: Request):
    authz = _bearer_from_request(request)
    if not authz:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{GATEWAY}/api/threads?limit=50", headers={"authorization": authz})
    return JSONResponse(r.json(), status_code=r.status_code)

@app.post("/ui/threads")
async def ui_create_thread(request: Request):
    authz = _bearer_from_request(request)
    if not authz:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{GATEWAY}/api/threads", json={}, headers={"authorization": authz})
    return JSONResponse(r.json(), status_code=r.status_code)

@app.put("/ui/threads/{thread_id}")
async def ui_rename_thread(thread_id: str, request: Request):
    authz = _bearer_from_request(request)
    if not authz:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    payload = await request.json()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.put(f"{GATEWAY}/api/threads/{thread_id}", json=payload, headers={"authorization": authz})
    return JSONResponse(r.json(), status_code=r.status_code)

@app.delete("/ui/threads/{thread_id}")
async def ui_delete_thread(thread_id: str, request: Request):
    """Proxy delete; used by the sidebar '🗑' action."""
    authz = _bearer_from_request(request)
    if not authz:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.delete(f"{GATEWAY}/api/threads/{thread_id}", headers={"authorization": authz})
    try:
        data = r.json()
    except Exception:
        data = {"ok": False}
    return JSONResponse(data, status_code=r.status_code)

@app.post("/ui/clear_thread")
async def ui_clear_thread(response: Response):
    """Clear the active thread cookie (used if a deleted thread was active)."""
    domain = os.getenv("COOKIE_DOMAIN") or None
    response.delete_cookie(TID_COOKIE, path="/")
    if domain:
        response.delete_cookie(TID_COOKIE, path="/", domain=domain)
    response.set_cookie(key=TID_COOKIE, value="", httponly=False, secure=True,
                        samesite="lax", max_age=0, expires=0, path="/", domain=domain)
    return {"ok": True}

@app.get("/ui/active_thread")
async def ui_active_thread(request: Request):
    tid = _parse_cookies(request.headers.get("cookie")).get(TID_COOKIE)
    return {"thread_id": tid}

# ---------- Deep link route (sets cookie first; then redirect) ----------
@app.get("/open/t/{thread_id}")
async def open_thread(thread_id: str):
    domain = os.getenv("COOKIE_DOMAIN") or None
    resp = RedirectResponse(url=f"/chat/?t={thread_id}", status_code=302)
    resp.set_cookie(
        key=TID_COOKIE, value=thread_id, httponly=False, secure=True,
        samesite="lax", max_age=60*60*24*7, path="/", domain=domain
    )
    return resp

# ---------- Chainlit header-auth bridge ----------
@cl.header_auth_callback
def header_auth_callback(headers: Dict[str, str]) -> Optional[cl.User]:
    cookie = headers.get("cookie") or headers.get("Cookie")
    tokens = _parse_cookies(cookie if cookie else "")
    token = tokens.get(APP_COOKIE)

    if not token:
        authz = headers.get("authorization") or headers.get("Authorization")
        if authz and authz.lower().startswith("bearer "):
            token = authz.split(" ", 1)[1]

    if not token:
        return None

    claims = _jwt_claims_unverified(token)

    # Prefer a real email: `email`, then first of `emails` (array). Fall back to name/UPN/sub.
    emails_claim = claims.get("emails")
    primary_email = claims.get("email")
    if not primary_email and isinstance(emails_claim, (list, tuple)) and emails_claim:
        primary_email = emails_claim[0]

    identifier = (
        claims.get("name")
        or primary_email
        or claims.get("preferred_username")
        or claims.get("sub")
        or "user"
    )
    meta = {
        "src": "cookie_or_header",
        "access_token": token,
        "sub": claims.get("sub"),
        "name": claims.get("name"),
        "email": primary_email,
        "emails": emails_claim if isinstance(emails_claim, (list, tuple)) else None,
        "preferred_username": claims.get("preferred_username"),
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
        "active_thread_id": tokens.get(TID_COOKIE),
    }
    return cl.User(identifier=identifier, metadata=meta)

@cl.on_logout
async def _on_logout(request: Request, response: Response):
    domain = os.getenv("COOKIE_DOMAIN") or None
    response.delete_cookie(APP_COOKIE, path="/")
    response.delete_cookie(TID_COOKIE, path="/")
    if domain:
        response.delete_cookie(APP_COOKIE, path="/", domain=domain)
        response.delete_cookie(TID_COOKIE, path="/", domain=domain)

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