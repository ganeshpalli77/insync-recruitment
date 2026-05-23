from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _test_env() -> None:
    """Stub secrets so unit tests boot without a .env. Skipped when running
    the real-API quality harness so the .env-loaded keys take effect."""
    if os.environ.get("QUALITY_TESTS") == "1":
        return
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("LLAMA_CLOUD_API_KEY", "llx-test")
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
    os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ.setdefault("RESEND_API_KEY", "re_test")
    os.environ.setdefault("ENVIRONMENT", "development")


@pytest.fixture(autouse=True)
def _reset_limiter_storage() -> None:
    """Clear the in-memory limiter counters between tests so rate limits
    apply fresh per test and don't bleed across cases."""
    from src.services.limiter import get_limiter

    storage = getattr(get_limiter(), "_storage", None) or getattr(get_limiter(), "storage", None)
    if storage is not None and hasattr(storage, "reset"):
        try:
            storage.reset()
        except Exception:
            pass


@pytest.fixture
def client() -> TestClient:
    from src.main import app

    return TestClient(app)
