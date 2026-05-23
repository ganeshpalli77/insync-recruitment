"""Email + leads capture. Writes to Supabase, sends email, fires Slack + CRM."""

from __future__ import annotations

from fastapi import APIRouter, Request
from loguru import logger

from src.db.repositories import events as events_repo
from src.db.repositories import leads as leads_repo
from src.db.repositories import prospects as prospects_repo
from src.schemas.capture import (
    EmailCaptureRequest,
    EmailCaptureResponse,
    LeadsRequestBody,
    LeadsRequestResponse,
)
from src.services.crm_webhook import post_event as crm_post_event
from src.services.email_sender import send_results_email
from src.services.limiter import get_limiter
from src.services.slack import alert_hot_lead

router = APIRouter(prefix="/api/capture", tags=["capture"])
_limiter = get_limiter()


@router.post("/email", response_model=EmailCaptureResponse)
@_limiter.limit("3/hour")
async def capture_email(request: Request, payload: EmailCaptureRequest) -> EmailCaptureResponse:
    # 1. Send the email (Resend + jinja + WeasyPrint PDF if available)
    sent, detail = await send_results_email(
        to=str(payload.email),
        job_summary=payload.job_summary,
        candidates=payload.top_candidates,
        session_id=payload.session_id,
    )

    # 2. Always record the lead, even if email send failed — the user gave us
    #    their email; the failure to deliver is our problem, not their data loss.
    await leads_repo.record_lead(
        email=str(payload.email),
        prospect_id=payload.prospect_id,
        source="email_capture",
        metadata={"session_id": payload.session_id, "email_sent": sent, "detail": detail},
    )

    # 3. Track B
    if payload.prospect_id:
        await prospects_repo.ensure_exists(payload.prospect_id, {"email": str(payload.email)})
        await prospects_repo.upgrade_status(payload.prospect_id, "engaged")
        event_data = {"email": str(payload.email), "session_id": payload.session_id}
        await events_repo.record_event(
            prospect_id=payload.prospect_id,
            event_type="email_captured",
            event_data=event_data,
            triggered_crm_webhook=True,
        )
        await crm_post_event(
            prospect_id=payload.prospect_id, event_type="email_captured", event_data=event_data
        )

    logger.info(
        "email_capture | session_id={} prospect_id={} sent={} top_candidates={}",
        payload.session_id,
        payload.prospect_id,
        sent,
        len(payload.top_candidates),
    )

    if sent:
        return EmailCaptureResponse(
            success=True, message="We'll email you a copy shortly."
        )
    return EmailCaptureResponse(
        success=False,
        message=(
            "We saved your address but couldn't send the email right now. "
            "An Insync recruiter will follow up."
        ),
    )


@router.post("/leads-request", response_model=LeadsRequestResponse)
@_limiter.limit("3/hour")
async def capture_leads_request(
    request: Request, payload: LeadsRequestBody
) -> LeadsRequestResponse:
    # 1. Record the lead immediately
    await leads_repo.record_lead(
        email=str(payload.email),
        prospect_id=payload.prospect_id,
        source="leads_request",
        metadata={
            "company_name": payload.company_name,
            "metro": payload.metro,
            "role_focus": payload.role_focus,
            "session_id": payload.session_id,
        },
    )

    # 2. Immediate ops notification — this is the high-intent signal
    await alert_hot_lead(
        email=str(payload.email),
        company=payload.company_name,
        metro=payload.metro,
        role_focus=payload.role_focus,
        prospect_id=payload.prospect_id,
    )

    # 3. Track B (promote to hot_lead)
    if payload.prospect_id:
        await prospects_repo.ensure_exists(
            payload.prospect_id,
            {"email": str(payload.email), "company_name": payload.company_name},
        )
        await prospects_repo.upgrade_status(payload.prospect_id, "hot_lead")
        event_data = {
            "email": str(payload.email),
            "company_name": payload.company_name,
            "metro": payload.metro,
            "role_focus": payload.role_focus,
        }
        await events_repo.record_event(
            prospect_id=payload.prospect_id,
            event_type="leads_requested",
            event_data=event_data,
            triggered_crm_webhook=True,
        )
        await crm_post_event(
            prospect_id=payload.prospect_id,
            event_type="leads_requested",
            event_data=event_data,
        )

    logger.info(
        "leads_request | session_id={} prospect_id={} metro={} roles={}",
        payload.session_id,
        payload.prospect_id,
        payload.metro,
        payload.role_focus,
    )

    return LeadsRequestResponse(
        success=True,
        next_steps_message=(
            "Got it — an Insync recruiter will reach out within one business day "
            "with a shortlist of candidates matching your focus."
        ),
    )
