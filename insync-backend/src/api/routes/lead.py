"""POST /api/lead/register — frontend email-gate submission.

Called once per prospect (the first time they submit name+email+company on
the gate after a scoring run). Persists to prospects + leads, records a
Track B event, and fires the *NEW LEAD* Slack alert with the just-completed
scoring's resume count.

Subsequent scorings by the same prospect skip this route — they're already
known to the backend, so `_persist_after_scoring` fires Slack directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from loguru import logger

from src.db.repositories import events as events_repo
from src.db.repositories import leads as leads_repo
from src.db.repositories import prospects as prospects_repo
from src.db.supabase import get_client
from src.schemas.capture import LeadRegisterRequest, LeadRegisterResponse
from src.services.crm_webhook import post_event as crm_post_event
from src.services.limiter import get_limiter
from src.services.slack import alert_scoring_completed

router = APIRouter(prefix="/api/lead", tags=["lead"])
_limiter = get_limiter()


async def _session_candidate_count(session_id: str) -> int:
    """Look up the just-completed session's candidate_count for the Slack alert."""
    client = get_client()
    if client is None:
        return 0
    try:
        resp = (
            client.table("scoring_sessions")
            .select("candidate_count")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return int(resp.data[0].get("candidate_count") or 0)
    except Exception:  # noqa: BLE001
        pass
    return 0


@router.post("/register", response_model=LeadRegisterResponse)
@_limiter.limit("10/hour")
async def register_lead(
    request: Request, payload: LeadRegisterRequest
) -> LeadRegisterResponse:
    # 1. Persist name+email+company on the prospects row.
    updated = await prospects_repo.update_lead_info(
        prospect_id=payload.prospect_id,
        name=payload.name,
        email=str(payload.email),
        company_name=payload.company_name,
    )

    # 2. Record the lead (separate denormalized table for ops reads).
    await leads_repo.record_lead(
        email=str(payload.email),
        prospect_id=payload.prospect_id,
        source="email_gate",
        metadata={
            "name": payload.name,
            "company_name": payload.company_name,
            "session_id": payload.session_id,
        },
    )

    # 3. Track B event + CRM webhook fan-out.
    event_data = {
        "name": payload.name,
        "email": str(payload.email),
        "company_name": payload.company_name,
        "session_id": payload.session_id,
    }
    await events_repo.record_event(
        prospect_id=payload.prospect_id,
        event_type="lead_captured",
        event_data=event_data,
        triggered_crm_webhook=True,
    )
    await crm_post_event(
        prospect_id=payload.prospect_id,
        event_type="lead_captured",
        event_data=event_data,
    )

    # 4. Slack: *NEW LEAD* alert with the just-completed scoring's metrics.
    this_run = await _session_candidate_count(payload.session_id)
    total = int((updated or {}).get("total_resumes_scored") or 0)
    await alert_scoring_completed(
        name=payload.name,
        company=payload.company_name,
        email=str(payload.email),
        prospect_id=payload.prospect_id,
        this_run_count=this_run,
        total_count=total,
        first_time=True,
    )

    logger.info(
        "lead_registered | prospect_id={} email={} company={!r} this_run={} total={}",
        payload.prospect_id,
        str(payload.email),
        payload.company_name,
        this_run,
        total,
    )

    return LeadRegisterResponse(success=True, total_resumes_scored=total)
