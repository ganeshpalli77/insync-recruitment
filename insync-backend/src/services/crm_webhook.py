"""Outbound CRM webhook poster. Signs payloads with CRM_WEBHOOK_SECRET if set."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from src.config import get_settings


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


async def post_event(
    *,
    prospect_id: str,
    event_type: str,
    event_data: dict[str, Any] | None = None,
) -> bool:
    """Fire a single event to the configured CRM webhook URL."""
    settings = get_settings()
    if not settings.crm_webhook_url:
        return False

    payload = {
        "prospect_id": prospect_id,
        "event_type": event_type,
        "metadata": event_data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "insync.screener",
    }
    body = json.dumps(payload, default=str).encode("utf-8")
    headers = {"content-type": "application/json"}
    if settings.crm_webhook_secret:
        headers["x-insync-signature"] = _sign(body, settings.crm_webhook_secret)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(settings.crm_webhook_url, content=body, headers=headers)
        if r.is_success:
            return True
        logger.warning(
            "crm_webhook_non_2xx | status={} url={} body={}",
            r.status_code,
            settings.crm_webhook_url,
            r.text[:200],
        )
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("crm_webhook_failed | err={}", e)
        return False
