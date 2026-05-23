"""POST /api/webhook/track-b-trigger — write prospect_events + fan out to CRM."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from loguru import logger

from src.db.repositories import events as events_repo
from src.db.repositories import prospects as prospects_repo
from src.schemas.capture import TrackBEvent, TrackBEventResponse
from src.services.crm_webhook import post_event as crm_post_event
from src.services.slack import post_message as slack_post

router = APIRouter(prefix="/api/webhook", tags=["webhook"])


@router.post("/track-b-trigger", response_model=TrackBEventResponse)
async def track_b_trigger(event: TrackBEvent) -> TrackBEventResponse:
    fallback_id = str(uuid.uuid4())

    # Ensure the prospect exists so the FK in prospect_events resolves.
    await prospects_repo.ensure_exists(event.prospect_id)

    crm_ok = await crm_post_event(
        prospect_id=event.prospect_id,
        event_type=event.event_type,
        event_data=event.metadata,
    )

    inserted = await events_repo.record_event(
        prospect_id=event.prospect_id,
        event_type=event.event_type,
        event_data=event.metadata,
        triggered_crm_webhook=crm_ok,
    )

    # Hot-lead events also tap ops in Slack immediately.
    if event.event_type == "leads_requested":
        await slack_post(
            f":fire: leads_requested event for prospect `{event.prospect_id}` "
            f"(metadata: {event.metadata})"
        )

    event_id = (inserted or {}).get("id") or fallback_id
    logger.info(
        "track_b_event | event_id={} prospect_id={} event_type={} crm_ok={}",
        event_id,
        event.prospect_id,
        event.event_type,
        crm_ok,
    )
    return TrackBEventResponse(success=True, event_id=str(event_id))
