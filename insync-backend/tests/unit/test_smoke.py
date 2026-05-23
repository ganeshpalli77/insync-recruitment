"""Contract smoke for endpoints that don't require LLM/Redis — health, sample
data, capture stubs, webhook, and the upfront validators on /api/score."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from src.schemas.capture import (
    EmailCaptureResponse,
    LeadsRequestResponse,
    SampleDataResponse,
    TrackBEventResponse,
)
from src.schemas.common import HealthResponse


def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    HealthResponse.model_validate(r.json())


def test_sample_data_returns_jd_and_resumes(client: TestClient) -> None:
    r = client.get("/api/sample-data")
    assert r.status_code == 200
    payload = SampleDataResponse.model_validate(r.json())
    assert len(payload.job_description) > 200
    assert len(payload.sample_resumes) == 5
    bands = {sr.expected_score_band for sr in payload.sample_resumes}
    assert {"strong", "moderate", "weak"}.issubset(bands)


def test_score_rejects_short_jd(client: TestClient) -> None:
    r = client.post(
        "/api/score",
        params={"stream": "false"},
        data={"job_description": "too short", "session_id": "x"},
        files=[("resumes", ("a.txt", io.BytesIO(b"x"), "text/plain"))],
    )
    assert r.status_code in (400, 422)


def test_score_rejects_unsupported_extension(client: TestClient) -> None:
    jd = "Forklift Operator. " * 10
    r = client.post(
        "/api/score",
        params={"stream": "false"},
        data={"job_description": jd, "session_id": "x"},
        files=[("resumes", ("a.exe", io.BytesIO(b"x"), "application/octet-stream"))],
    )
    assert r.status_code == 400


def test_email_capture_stub(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock Resend so the test doesn't depend on a valid API key.
    async def fake_send(**kwargs):  # noqa: ANN001
        return True, "test-msg-id"

    monkeypatch.setattr("src.api.routes.capture.send_results_email", fake_send)

    body = {
        "email": "owner@agency.example",
        "session_id": "s1",
        "prospect_id": None,
        "job_summary": {
            "title": "Forklift Operator",
            "location": "Atlanta, GA",
            "required_certifications": [],
            "key_skills": [],
        },
        "top_candidates": [],
    }
    r = client.post("/api/capture/email", json=body)
    assert r.status_code == 200
    assert EmailCaptureResponse.model_validate(r.json()).success is True


def test_leads_request_stub(client: TestClient) -> None:
    body = {
        "email": "owner@agency.example",
        "company_name": "Acme Staffing",
        "metro": "atlanta",
        "role_focus": ["forklift", "warehouse"],
        "session_id": "s1",
    }
    r = client.post("/api/capture/leads-request", json=body)
    assert r.status_code == 200
    assert LeadsRequestResponse.model_validate(r.json()).success is True


def test_webhook_track_b_stub(client: TestClient) -> None:
    body = {
        "prospect_id": "p-123",
        "event_type": "tool_used",
        "metadata": {"foo": "bar"},
        "timestamp": "2026-05-23T12:00:00Z",
    }
    r = client.post("/api/webhook/track-b-trigger", json=body)
    assert r.status_code == 200
    parsed = TrackBEventResponse.model_validate(r.json())
    assert parsed.success is True and parsed.event_id
