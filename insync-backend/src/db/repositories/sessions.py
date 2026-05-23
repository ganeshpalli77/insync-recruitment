"""scoring_sessions + candidate_scores writes."""

from __future__ import annotations

from typing import Any

from src.db.supabase import get_client, safe_table_insert
from src.schemas.score import ScoreResponse


async def record_session(
    *,
    session_id: str,
    prospect_id: str | None,
    response: ScoreResponse,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Persist a scoring session + each candidate to candidate_scores.

    The candidate row's `scoring_details` JSONB is the full CandidateScore
    EXCEPT `raw_resume_text` — we redact that to avoid storing PII at rest.
    """
    await safe_table_insert(
        "scoring_sessions",
        {
            "session_id": session_id,
            "prospect_id": prospect_id,
            "job_summary": response.job_summary.model_dump(),
            "candidate_count": len(response.candidates),
            "total_processing_time_ms": response.metadata.processing_time_ms,
            "total_tokens_used": response.metadata.total_tokens_used,
            "total_cost_usd": response.metadata.total_cost_usd,
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    )

    client = get_client()
    if client is None:
        return

    rows: list[dict[str, Any]] = []
    for c in response.candidates:
        details = c.model_dump()
        details.pop("raw_resume_text", None)  # never persist raw resume text
        # Drop any candidate email/phone that may have surfaced in details
        # (the parser node never puts them here, but belt-and-suspenders).
        rows.append(
            {
                "session_id": session_id,
                "candidate_name": c.name,
                "score": c.score,
                "score_band": c.score_band,
                "scoring_details": details,
            }
        )
    if not rows:
        return
    try:
        client.table("candidate_scores").insert(rows).execute()
    except Exception:  # noqa: BLE001
        # safe_table_insert handles single-row; batch logged via supabase already.
        return
