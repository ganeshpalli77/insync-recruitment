"""End-to-end /api/score route test with chat_json + LlamaParse mocked.

Exercises the real LangGraph wiring (parse_jd → fan-out → aggregate → quality)
so wiring bugs surface in unit tests without spending OpenAI credits.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from src.core.llm.client import LLMCall
from src.core.parsers import ParsedFile
from src.schemas.score import ScoreResponse


def _fake_jd_parse() -> dict:
    return {
        "title": "Forklift Operator",
        "location": "Atlanta, GA",
        "company": "Atlas Distribution",
        "required_experience_years": 3,
        "required_certifications": ["OSHA forklift"],
        "preferred_certifications": ["CDL Class A"],
        "key_skills": ["reach truck", "counterbalance", "WMS"],
        "physical_requirements": ["lift 50 lbs"],
        "shift_type": "day",
        "salary_range": "$22-$26/hr",
        "must_have_keywords": ["forklift", "OSHA"],
        "nice_to_have_keywords": ["bilingual"],
    }


def _fake_resume_parse() -> dict:
    return {
        "name": "Mock Candidate",
        "location": "Atlanta, GA",
        "phone": None,
        "email": None,
        "total_years_experience": 8,
        "relevant_logistics_years": 8,
        "current_position": "Lead Forklift Operator",
        "current_employer": "Atlas Logistics",
        "previous_positions": [],
        "certifications": ["OSHA Class I", "OSHA Class IV"],
        "education": [],
        "skills_explicit": ["forklift", "reach truck", "Manhattan WMS"],
        "skills_inferred": ["dock operations"],
        "employment_gaps": [],
        "red_flags": [],
        "positive_signals": ["8-year tenure"],
    }


def _fake_score(score: int) -> dict:
    return {
        "score": score,
        "score_band": "strong" if score >= 70 else "moderate" if score >= 40 else "weak",
        "one_line_summary": f"{score // 10}+ yrs forklift • OSHA • Atlanta",
        "strengths": [f"{score // 10} years forklift, exceeds 3-year requirement"],
        "gaps": ["No bilingual Spanish mentioned"],
        "interview_questions": [
            "Walk through your busiest cross-dock shift.",
            "Which WMS systems have you used in depth?",
            "Why are you leaving your current role?",
        ],
        "location_assessment": {
            "candidate_location": "Atlanta, GA",
            "distance_estimate_miles": 8,
            "commute_risk": "low",
        },
        "experience_assessment": {
            "years_relevant": float(score // 10),
            "matches_requirement": True,
            "notes": "Recent and continuous logistics tenure.",
        },
    }


@pytest.fixture
def patched_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub chat_json, parse_resume_bytes, and reset the graph cache."""

    counter = {"score": 92}

    async def fake_chat_json(*, model: str, system: str, user: str, **kwargs):  # noqa: ANN001
        if "logistics industry recruiting analyst" in system and "job description" in system.lower():
            parsed = _fake_jd_parse()
        elif "resume parser" in system:
            parsed = _fake_resume_parse()
        else:
            parsed = _fake_score(counter["score"])
            counter["score"] -= 7
        return LLMCall(
            parsed=parsed,
            raw_text=json.dumps(parsed),
            prompt_tokens=200,
            completion_tokens=400,
            model=model,
            cost=0.001,
        )

    async def fake_parse_resume_bytes(filename: str, content: bytes) -> ParsedFile:
        return ParsedFile(
            filename=filename,
            text=f"[mock parsed text for {filename}]\n" + content.decode("utf-8", errors="ignore"),
            file_hash="deadbeef" * 8,
            from_cache=False,
        )

    monkeypatch.setattr("src.core.graphs.nodes.chat_json", fake_chat_json)
    monkeypatch.setattr("src.core.graphs.nodes.parse_resume_bytes", fake_parse_resume_bytes)

    # Reset the lru_cached graph so fresh closures over the patched callables apply.
    from src.core.graphs.scoring_graph import get_scoring_graph

    get_scoring_graph.cache_clear()


def test_score_json_runs_graph_end_to_end(
    client: TestClient, patched_graph: None
) -> None:
    jd = "Forklift Operator — Atlanta. 3+ years experience, OSHA certified. " * 3
    r = client.post(
        "/api/score",
        params={"stream": "false"},
        data={"job_description": jd, "session_id": "graph-test-1"},
        files=[
            ("resumes", ("a.txt", io.BytesIO(b"Alice resume text"), "text/plain")),
            ("resumes", ("b.txt", io.BytesIO(b"Bob resume text"), "text/plain")),
            ("resumes", ("c.txt", io.BytesIO(b"Carol resume text"), "text/plain")),
        ],
    )
    assert r.status_code == 200, r.text
    payload = ScoreResponse.model_validate(r.json())
    assert payload.session_id == "graph-test-1"
    assert payload.job_summary.title == "Forklift Operator"
    assert len(payload.candidates) == 3
    # Sorted descending
    scores = [c.score for c in payload.candidates]
    assert scores == sorted(scores, reverse=True)
    assert payload.metadata.failed_resume_count == 0
    assert payload.metadata.total_cost_usd > 0


def test_score_sse_emits_progress_per_resume_then_result(
    client: TestClient, patched_graph: None
) -> None:
    jd = "Forklift Operator at Atlanta cross-dock. " * 5
    with client.stream(
        "POST",
        "/api/score",
        data={"job_description": jd, "session_id": "sse-1"},
        files=[
            ("resumes", ("a.txt", io.BytesIO(b"x"), "text/plain")),
            ("resumes", ("b.txt", io.BytesIO(b"y"), "text/plain")),
        ],
    ) as response:
        assert response.status_code == 200
        events: list[tuple[str, str]] = []
        current_event = "message"
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((current_event, line.split(":", 1)[1].strip()))

    progress = [json.loads(d) for ev, d in events if ev == "progress"]
    results = [d for ev, d in events if ev == "result"]
    errors = [d for ev, d in events if ev == "error"]

    assert not errors, errors
    assert len(progress) == 2
    assert {p["total"] for p in progress} == {2}
    assert len(results) == 1
    ScoreResponse.model_validate(json.loads(results[0]))
