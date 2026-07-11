"""Action Items API (T606).

Lightweight CRUD over an "action item" table that the daily-journal agent
populates after each submission. Items carry:
  - title, optional description
  - due_date (optional, ISO)
  - state  → "open" | "in_progress" | "done" | "dismissed"
  - origin → "agent" (recommended by the AI) | "user" (self-added)

Storage: we don't add a migration here — the helper falls back to the
`ai_action_items` JSON column on `daily_journals` when the table doesn't
yet exist, so this endpoint also works against the current schema and
provides a clean migration path to a dedicated table later.

Schema (when table exists):
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4()
  user_id         UUID NOT NULL
  journal_id      UUID NULL
  title           TEXT NOT NULL
  description     TEXT NULL
  state           TEXT NOT NULL DEFAULT 'open'
  origin          TEXT NOT NULL DEFAULT 'user'
  due_date        DATE NULL
  source_text     TEXT NULL       -- the original sentence from the journal
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.action_items")
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ActionItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None  # ISO date "YYYY-MM-DD"
    origin: str = "user"
    journal_id: Optional[str] = None
    source_text: Optional[str] = None


class ActionItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    state: Optional[str] = None  # "open" | "in_progress" | "done" | "dismissed"


class ActionItemState(BaseModel):
    state: str


# Allowed state transitions — mirrors the frontend state machine.
ALLOWED_STATES = {"open", "in_progress", "done", "dismissed"}

STATE_TRANSITIONS: Dict[str, List[str]] = {
    "open": ["in_progress", "done", "dismissed"],
    "in_progress": ["open", "done", "dismissed"],
    "done": ["open"],
    "dismissed": ["open"],
}

# ---------------------------------------------------------------------------
# Endpoints — everything routes through service-level helpers so storage
# strategy can be swapped without touching the HTTP layer.
# ---------------------------------------------------------------------------


def _storage():
    """Return the supabase admin client."""
    return get_supabase_admin()


@router.get("")
async def list_action_items(
    state: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
):
    """List all action items for the current user.

    Falls back to the JSON column on `daily_journals.ai_action_items` when
    the dedicated table isn't present, so the endpoint stays useful before
    the migration lands.
    """
    supabase = _storage()
    table = getattr(supabase, "table", None)
    if not table:
        return {"items": [], "fallback": True}

    try:
        # First try the dedicated table.
        query = (
            supabase.table("action_items")
            .select("*")
            .eq("user_id", str(user.id))
        )
        if state:
            query = query.eq("state", state)
        result = (
            query.order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
        return {"items": rows, "fallback": False}
    except Exception as e:  # table likely doesn't exist
        logger.info(f"action_items table unavailable; using fallback: {e}")

    # Fallback path — flatten the JSON column on daily_journals.
    rows = (
        supabase.table("daily_journals")
        .select("id, journal_date, ai_action_items")
        .eq("user_id", str(user.id))
        .order("journal_date", desc=True)
        .limit(max(1, limit // 3))
        .execute()
    ).data or []

    items: List[Dict[str, Any]] = []
    for r in rows:
        for idx, raw in enumerate(r.get("ai_action_items") or []):
            if not raw:
                continue
            items.append(
                {
                    "id": f"{r['id']}::{idx}",
                    "user_id": str(user.id),
                    "journal_id": r["id"],
                    "title": raw if isinstance(raw, str) else str(raw),
                    "description": None,
                    "state": "open",
                    "origin": "agent",
                    "due_date": None,
                    "source_text": raw if isinstance(raw, str) else None,
                    "created_at": r["journal_date"],
                    "updated_at": r["journal_date"],
                }
            )
    if state:
        items = [it for it in items if it.get("state") == state]
    return {"items": items[:limit], "fallback": True}


@router.post("", status_code=201)
async def create_action_item(
    body: ActionItemCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new action item (either from agent suggestion or user-added)."""
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    if body.origin not in ("agent", "user"):
        raise HTTPException(status_code=422, detail="origin must be 'agent' or 'user'")

    supabase = _storage()

    record = {
        "id": str(uuid4()),
        "user_id": str(user.id),
        "journal_id": body.journal_id,
        "title": body.title.strip(),
        "description": body.description,
        "state": "open",
        "origin": body.origin,
        "due_date": body.due_date,
        "source_text": body.source_text,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    try:
        resp = (
            supabase.table("action_items")
            .insert(record)
            .execute()
        )
        return {"item": resp.data[0] if resp.data else record, "created": True}
    except Exception as e:
        logger.warning(f"action_items insert failed (table missing?): {e}")

    # Fallback: append to the latest journal's ai_action_items.
    latest = (
        supabase.table("daily_journals")
        .select("id, ai_action_items")
        .eq("user_id", str(user.id))
        .order("journal_date", desc=True)
        .limit(1)
        .execute()
    ).data or []
    if not latest:
        raise HTTPException(status_code=404, detail="No journal to attach action to")

    items = list(latest[0].get("ai_action_items") or [])
    items.append(body.title.strip())
    supabase.table("daily_journals").update(
        {"ai_action_items": items}
    ).eq("id", latest[0]["id"]).execute()
    record["id"] = f"{latest[0]['id']}::{len(items) - 1}"
    record["journal_id"] = latest[0]["id"]
    return {"item": record, "created": True, "fallback": True}


@router.patch("/{item_id}")
async def update_action_item(
    item_id: str,
    body: ActionItemUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """Update title / description / due_date / state of a single item."""
    supabase = _storage()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=422, detail="No fields to update")

    if "state" in patch and patch["state"] not in ALLOWED_STATES:
        raise HTTPException(
            status_code=422,
            detail=f"state must be one of {sorted(ALLOWED_STATES)}",
        )

    patch["updated_at"] = datetime.utcnow().isoformat()

    try:
        # Dedicated table update.
        existing = (
            supabase.table("action_items")
            .select("id, state")
            .eq("id", item_id)
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        ).data
        if existing is None:
            raise HTTPException(status_code=404, detail="Action item not found")
        if (
            "state" in patch
            and existing["state"] != patch["state"]
            and patch["state"] not in STATE_TRANSITIONS.get(existing["state"], [])
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot transition from {existing['state']} to {patch['state']}",
            )

        resp = (
            supabase.table("action_items")
            .update(patch)
            .eq("id", item_id)
            .eq("user_id", str(user.id))
            .execute()
        )
        return {"item": resp.data[0] if resp.data else None, "updated": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"action_items update fallback: {e}")

    # Fallback: item_id is "{journal_id}::{idx}"
    if "::" in item_id:
        journal_id, idx = item_id.split("::", 1)
        try:
            idx_int = int(idx)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid fallback id")
        journal = (
            supabase.table("daily_journals")
            .select("id, user_id, ai_action_items")
            .eq("id", journal_id)
            .maybe_single()
            .execute()
        ).data
        if not journal or journal["user_id"] != str(user.id):
            raise HTTPException(status_code=404, detail="Action item not found")
        items = list(journal.get("ai_action_items") or [])
        if idx_int >= len(items):
            raise HTTPException(status_code=404, detail="Action item index out of range")
        # Fallback only supports done / dismissed; everything else is a no-op.
        new_state = patch.get("state")
        if new_state in ("done", "dismissed"):
            items[idx_int] = f"[{new_state}] " + (
                items[idx_int].lstrip()
                if isinstance(items[idx_int], str)
                else str(items[idx_int])
            )
            supabase.table("daily_journals").update(
                {"ai_action_items": items}
            ).eq("id", journal_id).execute()
        elif new_state == "open":
            cleaned = (
                items[idx_int]
                if isinstance(items[idx_int], str)
                else str(items[idx_int])
            )
            for marker in ("[done] ", "[dismissed] ", "[in_progress] "):
                if cleaned.startswith(marker):
                    cleaned = cleaned[len(marker):]
                    break
            items[idx_int] = cleaned
            supabase.table("daily_journals").update(
                {"ai_action_items": items}
            ).eq("id", journal_id).execute()

        return {
            "item": {
                "id": item_id,
                "title": items[idx_int],
                "state": new_state or "open",
                "user_id": str(user.id),
                "journal_id": journal_id,
                "origin": "agent",
            },
            "updated": True,
            "fallback": True,
        }

    raise HTTPException(status_code=404, detail="Action item not found")


@router.post("/{item_id}/state")
async def transition_action_item(
    item_id: str,
    body: ActionItemState,
    user: CurrentUser = Depends(get_current_user),
):
    """Convenience endpoint — just toggle state, leverages the PATCH above."""
    if body.state not in ALLOWED_STATES:
        raise HTTPException(
            status_code=422,
            detail=f"state must be one of {sorted(ALLOWED_STATES)}",
        )
    return await update_action_item(
        item_id,
        ActionItemUpdate(state=body.state),
        user,
    )


@router.delete("/{item_id}")
async def delete_action_item(
    item_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete by transitioning to `dismissed`."""
    supabase = _storage()
    try:
        existing = (
            supabase.table("action_items")
            .select("id, state")
            .eq("id", item_id)
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        ).data
        if existing is None:
            raise HTTPException(status_code=404, detail="Action item not found")
        supabase.table("action_items").update(
            {"state": "dismissed", "updated_at": datetime.utcnow().isoformat()}
        ).eq("id", item_id).eq("user_id", str(user.id)).execute()
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"action_items delete fallback: {e}")

    # Fallback path
    if "::" in item_id:
        return await transition_action_item(
            item_id,
            ActionItemState(state="dismissed"),
            user,
        )
    raise HTTPException(status_code=404, detail="Action item not found")
