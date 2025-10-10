# apps/gateway-fastapi/src/features/profiles.py
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

# LangGraph SDK: the gateway creates a client in main.py and passes it here.
# We use the Store API to get/put an item under the namespace ["users", <user_id>].
# SDK reference shows Store operations: get_item / put_item / search_items, etc.
# https://langchain-ai.github.io/langgraph/cloud/reference/sdk/python_sdk_ref/  :contentReference[oaicite:4]{index=4}

# ---- Models ----

DEFAULT_SETTINGS = {
    "web_search_default": False,
    "locale": "en",
    "tz": "UTC",
}

class Profile(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    created_at: str
    updated_at: str

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

# ---- Internal helpers ----

def _ns(user_id: str):
    # Namespace for user-scoped items (durable across threads)
    return ["users", user_id]

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _coerce_item_value(item: Any) -> Optional[dict]:
    """
    LangGraph SDK returns objects with .value (and metadata). Accept dict too for safety.
    """
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get("value") or item
    return getattr(item, "value", None)

async def get_profile(client, user_id: str) -> Optional[Profile]:
    try:
        item = await client.store.get_item(_ns(user_id), key="profile")
        data = _coerce_item_value(item)
        if not data:
            return None
        return Profile(**data)
    except Exception:
        # Treat any 404 / not found as missing profile
        return None

async def put_profile(client, profile: Profile) -> None:
    await client.store.put_item(
        _ns(profile.user_id),
        key="profile",
        value=profile.model_dump(),
        index=["user_id", "display_name"],  # enable future search/filter
    )

async def ensure_profile(client, user_id: str, claims: Optional[dict] = None) -> Profile:
    """
    Idempotent bootstrap: return existing profile or create a minimal one.
    """
    existing = await get_profile(client, user_id)
    if existing:
        return existing

    display_name = None
    if claims:
        # Prefer human-friendly names if available
        display_name = (
            claims.get("name")
            or claims.get("preferred_username")
            or claims.get("email")
        )
    now = _now_iso()
    prof = Profile(
        user_id=user_id,
        display_name=display_name,
        avatar_url=None,
        settings=dict(DEFAULT_SETTINGS),
        created_at=now,
        updated_at=now,
    )
    await put_profile(client, prof)
    return prof

async def update_profile(client, user_id: str, patch: ProfileUpdate) -> Profile:
    current = await ensure_profile(client, user_id)
    data = current.model_dump()

    if patch.display_name is not None:
        data["display_name"] = patch.display_name
    if patch.avatar_url is not None:
        data["avatar_url"] = patch.avatar_url
    if patch.settings is not None:
        new_settings = dict(data.get("settings") or {})
        new_settings.update(patch.settings)
        data["settings"] = new_settings

    data["updated_at"] = _now_iso()
    await client.store.put_item(_ns(user_id), key="profile", value=data, index=["user_id", "display_name"])
    return Profile(**data)

# ---- Router factory ----

def make_profiles_router(client, get_current_user, user_id_from_claims):
    """
    Bind the profiles API to a concrete LangGraph client + auth helpers.
    Endpoints:
      GET  /api/profile  -> read-or-create profile for current user
      PUT  /api/profile  -> update fields/settings for current user
    """
    router = APIRouter(prefix="/api/profile", tags=["profile"])

    @router.get("", response_model=Profile)
    async def read_my_profile(request: Request):
        claims = await get_current_user(request)
        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")
        user_id = user_id_from_claims(claims)
        prof = await ensure_profile(client, user_id, claims=claims)
        return prof

    @router.put("", response_model=Profile)
    async def write_my_profile(patch: ProfileUpdate, request: Request):
        claims = await get_current_user(request)
        if not claims:
            raise HTTPException(status_code=401, detail="unauthenticated")
        user_id = user_id_from_claims(claims)
        prof = await update_profile(client, user_id, patch)
        return prof

    return router
