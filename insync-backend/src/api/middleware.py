from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.config import get_settings


def install_middleware(app: FastAPI) -> None:
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_logger(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "request_failed | method={} path={} request_id={} duration_ms={}",
                request.method,
                request.url.path,
                request_id,
                duration_ms,
            )
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "request | method={} path={} status={} ip={} request_id={} duration_ms={}",
            request.method,
            request.url.path,
            response.status_code,
            request.client.host if request.client else "-",
            request_id,
            duration_ms,
        )
        response.headers["x-request-id"] = request_id
        return response
