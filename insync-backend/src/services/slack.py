"""Hot-lead Slack alerter. Fire-and-forget; never blocks the request."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger

from src.config import get_settings


async def post_message(text: str, *, extra: dict[str, Any] | None = None) -> bool:
    """Post a single message to the configured Slack incoming webhook.

    Returns True on 2xx, False otherwise (including when SLACK_WEBHOOK_URL
    is not configured). Errors are logged, never raised.
    """
    settings = get_settings()
    if not settings.slack_webhook_url:
        logger.info("slack_not_configured | skipping post")
        return False

    payload: dict[str, Any] = {"text": text}
    if extra:
        payload.update(extra)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(settings.slack_webhook_url, json=payload)
        if r.is_success:
            return True
        logger.warning("slack_post_non_2xx | status={} body={}", r.status_code, r.text[:200])
        return False
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("slack_post_failed | err={}", e)
        return False


async def alert_hot_lead(
    *,
    email: str,
    company: str,
    metro: str,
    role_focus: list[str],
    prospect_id: str | None,
) -> None:
    """Post a structured hot-lead alert with the lead's contact + intent."""
    bullets = "\n".join(
        [
            f"• *Email:* {email}",
            f"• *Company:* {company}",
            f"• *Metro:* {metro}",
            f"• *Roles:* {', '.join(role_focus) or '(none)'}",
            f"• *Prospect ID:* {prospect_id or '(none)'}",
        ]
    )
    await post_message(f":fire: *Hot lead requested intros*\n{bullets}")


async def alert_scoring_completed(
    *,
    name: str,
    company: str,
    email: str | None,
    prospect_id: str | None,
    this_run_count: int,
    total_count: int,
    first_time: bool,
) -> None:
    """Fired after every scoring run by a registered lead. Includes a
    'NEW LEAD' tag on the first run after gate submission."""
    header = ":sparkles: *NEW LEAD*" if first_time else ":green_circle: *Scoring run*"
    bullets = "\n".join(
        [
            f"• *Who:* {name} @ {company}",
            f"• *Email:* {email or '(unknown)'}",
            f"• *This run:* {this_run_count} resume(s)",
            f"• *Lifetime total:* {total_count}",
            f"• *Prospect:* {prospect_id or '(none)'}",
        ]
    )
    await post_message(f"{header}\n{bullets}")
