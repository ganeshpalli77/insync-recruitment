"""Prospect table — first-seen tracking + status transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.db.supabase import get_client, safe_table_upsert


async def ensure_exists(prospect_id: str, metadata: dict[str, Any] | None = None) -> None:
    """INSERT-or-no-op a prospect row. Bumps last_active_at on every call."""
    if not prospect_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    await safe_table_upsert(
        "prospects",
        {
            "prospect_id": prospect_id,
            "last_active_at": now,
            "metadata": metadata or {},
        },
        on_conflict="prospect_id",
    )


async def increment_tool_use(prospect_id: str, resumes_scored: int) -> None:
    """Bump tool_use_count + total_resumes_scored. Skips if prospect_id is blank."""
    if not prospect_id:
        return
    client = get_client()
    if client is None:
        return
    try:
        # supabase-py doesn't expose a portable atomic increment; read-modify-write
        # is fine for low-contention free-tier traffic.
        current = (
            client.table("prospects").select("tool_use_count, total_resumes_scored")
            .eq("prospect_id", prospect_id).limit(1).execute()
        )
        if not current.data:
            return
        row = current.data[0]
        client.table("prospects").update(
            {
                "tool_use_count": (row.get("tool_use_count") or 0) + 1,
                "total_resumes_scored": (row.get("total_resumes_scored") or 0) + resumes_scored,
                "last_active_at": datetime.now(timezone.utc).isoformat(),
                "status": "tool_user",
            }
        ).eq("prospect_id", prospect_id).execute()
    except Exception:  # noqa: BLE001
        # Already logged inside safe_*; silent here so we don't double-log.
        return


async def upgrade_status(prospect_id: str, status: str) -> None:
    """Move a prospect to a higher-intent status."""
    if not prospect_id:
        return
    client = get_client()
    if client is None:
        return
    try:
        client.table("prospects").update(
            {"status": status, "last_active_at": datetime.now(timezone.utc).isoformat()}
        ).eq("prospect_id", prospect_id).execute()
    except Exception:  # noqa: BLE001
        return


async def get_by_id(prospect_id: str) -> dict[str, Any] | None:
    """Read the full prospect row by prospect_id. None if missing or DB off."""
    if not prospect_id:
        return None
    client = get_client()
    if client is None:
        return None
    try:
        resp = (
            client.table("prospects")
            .select("*")
            .eq("prospect_id", prospect_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception:  # noqa: BLE001
        return None


async def update_lead_info(
    *, prospect_id: str, name: str, email: str, company_name: str
) -> dict[str, Any] | None:
    """Set name+email+company on a prospect (upsert) + status='engaged'.

    Returns the resulting row (with updated total_resumes_scored, etc.) so
    the caller can feed the totals into a Slack alert without a second
    round trip.
    """
    if not prospect_id:
        return None
    now = datetime.now(timezone.utc).isoformat()
    await safe_table_upsert(
        "prospects",
        {
            "prospect_id": prospect_id,
            "name": name,
            "email": email,
            "company_name": company_name,
            "status": "engaged",
            "last_active_at": now,
        },
        on_conflict="prospect_id",
    )
    return await get_by_id(prospect_id)
