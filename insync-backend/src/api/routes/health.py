from __future__ import annotations

import time

from fastapi import APIRouter

from src.schemas.common import HealthResponse

router = APIRouter(tags=["health"])

_PROCESS_START = time.monotonic()
_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # Phase 1: report ok for all services; Phase 4 wires real probes.
    return HealthResponse(
        status="ok",
        services={"database": "unknown", "openai": "unknown", "llamaparse": "unknown"},
        version=_VERSION,
        uptime_seconds=int(time.monotonic() - _PROCESS_START),
    )
