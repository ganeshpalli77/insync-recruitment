"""leads — captured emails from the post-results hooks."""

from __future__ import annotations

from typing import Any

from src.db.supabase import safe_table_insert


async def record_lead(
    *,
    email: str,
    prospect_id: str | None,
    source: str,  # "email_capture" | "leads_request"
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    return await safe_table_insert(
        "leads",
        {
            "email": email,
            "prospect_id": prospect_id,
            "source": source,
            "metadata": metadata or {},
        },
    )
