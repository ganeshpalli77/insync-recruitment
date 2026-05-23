"""Supabase client wrapper.

All persistence calls go through this module. If SUPABASE_URL is missing or
points at the example placeholder, every repository operation is a no-op
that logs a warning — the rest of the app keeps running. This is deliberate
for free-tier ops simplicity: a Supabase outage shouldn't take scoring down.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from supabase import Client, create_client

from src.config import get_settings

_client: Client | None = None
_disabled_logged = False


def _placeholder(url: str) -> bool:
    return not url or url.startswith("https://xxx") or "example.supabase.co" in url


def is_configured() -> bool:
    s = get_settings()
    return bool(s.supabase_service_key) and not _placeholder(s.supabase_url)


def get_client() -> Client | None:
    """Return the cached service-role Supabase client, or None if disabled."""
    global _client, _disabled_logged
    if _client is not None:
        return _client
    if not is_configured():
        if not _disabled_logged:
            logger.warning(
                "supabase_disabled | SUPABASE_URL or SUPABASE_SERVICE_KEY missing/placeholder; "
                "all repository writes will be no-ops"
            )
            _disabled_logged = True
        return None
    s = get_settings()
    _client = create_client(s.supabase_url, s.supabase_service_key)
    return _client


def reset_client() -> None:
    """Test-only — drop cached client so the next call picks up new settings."""
    global _client, _disabled_logged
    _client = None
    _disabled_logged = False


async def safe_table_insert(table: str, row: dict[str, Any]) -> dict[str, Any] | None:
    """INSERT one row; swallow errors so persistence outages don't break the API."""
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.table(table).insert(row).execute()
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("supabase_insert_failed | table={} err={}", table, e)
        return None


async def safe_table_upsert(
    table: str, row: dict[str, Any], on_conflict: str
) -> dict[str, Any] | None:
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.table(table).upsert(row, on_conflict=on_conflict).execute()
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("supabase_upsert_failed | table={} err={}", table, e)
        return None


async def safe_table_update(
    table: str, match: dict[str, Any], patch: dict[str, Any]
) -> None:
    client = get_client()
    if client is None:
        return None
    try:
        q = client.table(table).update(patch)
        for col, val in match.items():
            q = q.eq(col, val)
        q.execute()
    except Exception as e:  # noqa: BLE001
        logger.warning("supabase_update_failed | table={} err={}", table, e)
