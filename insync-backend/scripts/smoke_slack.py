"""Posts one test alert to your Slack channel to verify SLACK_WEBHOOK_URL works."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.slack import alert_hot_lead, post_message  # noqa: E402


async def main() -> int:
    ok = await post_message(
        ":wave: Insync Resume Screener — Slack webhook smoke test. "
        "If you see this, alerts are wired correctly."
    )
    print("plain message:", "OK" if ok else "FAILED")

    await alert_hot_lead(
        email="test@example.com",
        company="Test Staffing Co",
        metro="atlanta",
        role_focus=["forklift", "warehouse"],
        prospect_id="smoke-test-prospect",
    )
    print("hot-lead alert: sent (check the channel)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
