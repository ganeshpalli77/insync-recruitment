"""slowapi rate limiter with Redis backend + helpers for per-IP daily caps and
rolling cost accounting.

slowapi handles the per-route request-count limits (`/api/score` 5/hour, etc.).
For "100 resumes per IP per day" and "alert when daily cost > $X", we use
plain Redis counters keyed by IP+date and global+date respectively.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from loguru import logger
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from src.config import get_settings
from src.services.cache import get_redis


def _key_func(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


_limiter: Limiter | None = None


def get_limiter() -> Limiter:
    """Process-wide slowapi singleton. Routes import this; main.py installs it.

    Uses in-memory storage by default — fine for a single-instance deploy.
    Set `RATE_LIMIT_STORAGE=redis://...` to share counters across replicas.
    """
    global _limiter
    if _limiter is None:
        _limiter = Limiter(
            key_func=_key_func,
            storage_uri=get_settings().rate_limit_storage,
            strategy="fixed-window",
            # headers_enabled=True trips with endpoints that return a Pydantic
            # model rather than a starlette Response — keep off until we
            # standardize on explicit Response returns.
            headers_enabled=False,
        )
    return _limiter


def reset_limiter() -> None:
    """Test-only — drop the singleton so settings changes take effect."""
    global _limiter
    _limiter = None


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    detail = (
        "You've hit the free-tier limit. Try again later, or get in touch about "
        "expanded access."
    )
    logger.warning(
        "rate_limited | path={} ip={} limit={}",
        request.url.path,
        _key_func(request),
        getattr(exc, "detail", "n/a"),
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "rate_limited", "detail": detail},
    )


# --- Per-IP daily resume cap (independent of slowapi) ---------------------


def _today_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def enforce_daily_resume_cap(ip: str, new_resume_count: int) -> None:
    """INCRBY a per-IP/per-day Redis counter. Reject if it would exceed the cap.

    Cap is `FREE_TIER_DAILY_RESUME_CAP` (default 100). Counter TTL = 26h (a
    little more than a day so it absorbs server-time drift around midnight).
    """
    settings = get_settings()
    cap = settings.free_tier_daily_resume_cap
    if cap <= 0:
        return  # cap disabled

    key = f"ratecap:resumes:{ip}:{_today_utc_str()}"
    try:
        r = get_redis()
        new_total = await r.incrby(key, new_resume_count)
        await r.expire(key, 26 * 3600)
    except Exception as e:  # noqa: BLE001
        logger.warning("ratecap_redis_failed | key={} err={}", key, e)
        return  # fail-open: don't block users if Redis is down

    if new_total > cap:
        # Roll back so legitimate retry attempts aren't permanently capped by
        # the over-cap burst.
        try:
            await get_redis().decrby(key, new_resume_count)
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You've hit today's free-tier limit ({cap} resumes per day per IP). "
                "Get in touch about expanded access."
            ),
        )


# --- Daily cost telemetry + alert -----------------------------------------


async def record_cost_and_maybe_alert(cost_usd: float) -> None:
    """Add to today's rolling cost; log a single warning when threshold crossed."""
    if cost_usd <= 0:
        return
    settings = get_settings()
    key = f"cost:usd:{_today_utc_str()}"
    threshold_key = f"cost:alerted:{_today_utc_str()}"

    try:
        r = get_redis()
        # incrbyfloat is atomic in Redis.
        new_total_str = await r.incrbyfloat(key, cost_usd)
        await r.expire(key, 26 * 3600)
        new_total = float(new_total_str)
        if new_total >= settings.daily_cost_alert_usd:
            alerted = await r.set(threshold_key, "1", ex=26 * 3600, nx=True)
            if alerted:
                logger.warning(
                    "daily_cost_threshold_crossed | date={} total_usd={:.4f} threshold={}",
                    _today_utc_str(),
                    new_total,
                    settings.daily_cost_alert_usd,
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("cost_record_failed | err={}", e)
