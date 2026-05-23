"""prospect_events — every meaningful action a prospect takes."""

from __future__ import annotations

from typing import Any

from src.db.supabase import safe_table_insert


async def record_event(
    *,
    prospect_id: str | None,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    triggered_crm_webhook: bool = False,
) -> dict[str, Any] | None:
    if not prospect_id:
        return None
    return await safe_table_insert(
        "prospect_events",
        {
            "prospect_id": prospect_id,
            "event_type": event_type,
            "event_data": event_data or {},
            "triggered_crm_webhook": triggered_crm_webhook,
        },
    )
