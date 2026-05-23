from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from loguru import logger
from slowapi.errors import RateLimitExceeded

from src.api.middleware import install_middleware
from src.api.routes import capture, health, sample, score, webhook
from src.config import get_settings
from src.services.limiter import get_limiter, rate_limit_exception_handler


def _configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        ),
        backtrace=False,
        diagnose=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    settings = get_settings()
    logger.info(
        "boot | env={} allowed_origins={}",
        settings.environment,
        settings.allowed_origins_list,
    )
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Insync Recruitment — AI Resume Screener",
        description="Free B2B tool: scores resumes against a JD for logistics recruiters.",
        version="1.0.0",
        lifespan=lifespan,
    )
    install_middleware(app)
    app.state.limiter = get_limiter()
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
    app.include_router(health.router)
    app.include_router(score.router)
    app.include_router(capture.router)
    app.include_router(sample.router)
    app.include_router(webhook.router)
    return app


app = create_app()
