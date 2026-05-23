"""Phase 5 hardening: magic-bytes, sanitizer, rate limits."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from src.services.file_validator import matches_extension
from src.services.sanitizer import clean_text


# ---- magic-bytes -------------------------------------------------------


def test_magic_accepts_real_pdf_header() -> None:
    assert matches_extension("resume.pdf", b"%PDF-1.4\n...")


def test_magic_rejects_pdf_with_html_body() -> None:
    assert not matches_extension("resume.pdf", b"<html><body>hi</body></html>")


def test_magic_accepts_docx_zip_signature() -> None:
    assert matches_extension("resume.docx", b"PK\x03\x04\x14\x00...")


def test_magic_rejects_docx_with_pdf_header() -> None:
    assert not matches_extension("resume.docx", b"%PDF-1.7\n...")


def test_magic_permits_any_txt() -> None:
    assert matches_extension("notes.txt", b"anything goes here")


def test_magic_rejects_unknown_extension() -> None:
    assert not matches_extension("malware.exe", b"MZ\x90\x00")


# ---- sanitizer ---------------------------------------------------------


def test_clean_text_strips_html_and_nul() -> None:
    raw = "Hello <script>alert(1)</script>\x00 world"
    assert clean_text(raw) == "Hello alert(1) world"


def test_clean_text_truncates_to_max_length() -> None:
    assert clean_text("a" * 1000, max_length=50) == "a" * 50


def test_clean_text_handles_empty() -> None:
    assert clean_text("") == ""


# ---- /api/score: magic-bytes rejection at the route -------------------


def test_score_rejects_pdf_with_wrong_magic(client: TestClient) -> None:
    jd = "Forklift Operator at Atlanta cross-dock. " * 5
    r = client.post(
        "/api/score",
        params={"stream": "false"},
        data={"job_description": jd, "session_id": "magic-test"},
        files=[("resumes", ("resume.pdf", io.BytesIO(b"<html>not a pdf</html>"), "application/pdf"))],
    )
    assert r.status_code == 400
    assert "extension" in r.json()["detail"].lower() or "contents" in r.json()["detail"].lower()


# ---- /api/sample-data rate limit (30/hour) ----------------------------


def test_sample_data_rate_limit_enforced(client: TestClient) -> None:
    """The 31st request from the same IP within an hour returns 429.

    Uses the standard `client` fixture — the autouse `_reset_limiter_storage`
    fixture clears the in-memory counters before each test so the budget
    starts fresh.
    """
    statuses = [client.get("/api/sample-data").status_code for _ in range(31)]
    assert statuses.count(200) == 30
    assert statuses[-1] == 429


@pytest.mark.skip(reason="exercises the real Redis-backed limiter; needs docker compose up redis")
def test_score_rate_limit_with_redis() -> None:
    """Placeholder for an integration test that asserts /api/score 6th call returns 429."""


# ---- real-client-IP extraction -----------------------------------------


def _make_request(headers: dict[str, str], remote: str = "1.2.3.4"):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (remote, 12345),
        "path": "/",
        "query_string": b"",
        "scheme": "http",
        "server": ("test", 80),
    }
    return Request(scope)


def test_real_client_ip_prefers_cloudflare_header() -> None:
    from src.services.limiter import real_client_ip

    r = _make_request({"cf-connecting-ip": "8.8.8.8", "x-forwarded-for": "100.64.0.3"})
    assert real_client_ip(r) == "8.8.8.8"


def test_real_client_ip_skips_railway_cgnat_proxy() -> None:
    from src.services.limiter import real_client_ip

    # Realistic Railway scenario: user IP first, then a CGNAT hop, then the
    # Envoy proxy hop. We must pick the user IP, not the CGNAT one.
    r = _make_request({"x-forwarded-for": "100.64.0.3, 8.8.8.8, 10.0.0.5"})
    assert real_client_ip(r) == "8.8.8.8"


def test_real_client_ip_skips_only_internal_chain() -> None:
    from src.services.limiter import real_client_ip

    r = _make_request({"x-forwarded-for": "10.0.0.5, 100.64.0.3, 192.168.1.1"}, remote="9.9.9.9")
    # No public IP in the chain — fall back to remote address.
    assert real_client_ip(r) == "9.9.9.9"
