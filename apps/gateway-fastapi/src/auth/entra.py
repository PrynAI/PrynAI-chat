# apps/gateway-fastapi/src/auth/entra.py
"""
Token validation for Microsoft Entra External ID (CIAM) access tokens.

We validate:
- Signature via JWKS fetched from the OIDC discovery document
- Issuer equals the discovery 'issuer'
- Audience equals OIDC_AUDIENCE (Application ID URI or API client id)

Env you must set:
  OIDC_DISCOVERY_URL = https://<subdomain>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration
  OIDC_AUDIENCE      = api://<gateway-api-app-id>/chat.fullaccess    (or the API app client id)
Optional:
  AUTH_DEV_BYPASS=true   (only for local dev) + header X-Debug-Sub: <user-id>
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import os, time, httpx
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError, JWKError

class AuthError(Exception):
    pass

_OIDC: Dict[str, Any] = {"cfg": None, "cfg_exp": 0, "jwks": None, "jwks_exp": 0}

DISCOVERY = os.getenv("OIDC_DISCOVERY_URL")
AUDIENCE  = os.getenv("OIDC_AUDIENCE")

def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization: return None
    p = authorization.split()
    return p[1] if len(p) == 2 and p[0].lower() == "bearer" else None

async def _get_openid_config() -> Dict[str, Any]:
    if not DISCOVERY:
        raise AuthError("OIDC_DISCOVERY_URL not configured")
    if _OIDC["cfg"] and _OIDC["cfg_exp"] > time.time():
        return _OIDC["cfg"]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(DISCOVERY)
        r.raise_for_status()
        cfg = r.json()
    _OIDC["cfg"] = cfg
    _OIDC["cfg_exp"] = time.time() + 3600
    return cfg

async def _get_jwks() -> Dict[str, Any]:
    if _OIDC["jwks"] and _OIDC["jwks_exp"] > time.time():
        return _OIDC["jwks"]
    cfg = await _get_openid_config()
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(cfg["jwks_uri"])
        r.raise_for_status()
        jwks = r.json()
    _OIDC["jwks"] = jwks
    _OIDC["jwks_exp"] = time.time() + 3600
    return jwks

async def verify_jwt(token: str) -> Dict[str, Any]:
    cfg  = await _get_openid_config()
    jwks = await _get_jwks()

    unverified = jwt.get_unverified_header(token)
    kid = unverified.get("kid")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        # Key rotation retry
        jwks = await _get_jwks()
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            raise AuthError("JWK for token kid not found")

    options = {"verify_aud": bool(AUDIENCE)}
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256", "RS512"],
            audience=AUDIENCE,
            issuer=cfg["issuer"],  # issuer comes from the discovery doc
            options=options,
        )
        return claims
    except ExpiredSignatureError as e:
        raise AuthError("token_expired") from e
    except JWTClaimsError as e:
        raise AuthError("invalid_claims") from e
    except (JWKError, JWTError) as e:
        raise AuthError("invalid_token") from e

async def get_current_user(request) -> Optional[Dict[str, Any]]:
    # Dev bypass for local smoke tests
    if os.getenv("AUTH_DEV_BYPASS", "false").lower() == "true":
        dev = request.headers.get("x-debug-sub")
        if dev:
            return {"sub": dev, "name": request.headers.get("x-user-name")}
    token = extract_bearer_token(request.headers.get("authorization"))
    if not token:
        return None
    return await verify_jwt(token)

def user_id_from_claims(claims: Dict[str, Any]) -> str:
    return claims.get("sub")
