"""End-to-end Supabase write check.

Inserts one prospect + one scoring session + one candidate row + one event +
one lead, then prints the rows back. Confirms .env keys + RLS work for the
service role. No OpenAI/LlamaParse spend.

    uv run python scripts/smoke_supabase.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.repositories import events as events_repo  # noqa: E402
from src.db.repositories import leads as leads_repo  # noqa: E402
from src.db.repositories import prospects as prospects_repo  # noqa: E402
from src.db.repositories import sessions as sessions_repo  # noqa: E402
from src.db.supabase import get_client, is_configured  # noqa: E402
from src.schemas.common import JobSummary  # noqa: E402
from src.schemas.score import (  # noqa: E402
    CandidateScore,
    ExperienceMatch,
    LocationMatch,
    ScoreResponse,
    ScoringMetadata,
)


async def main() -> int:
    if not is_configured():
        print("Supabase not configured — fix SUPABASE_URL/SUPABASE_SERVICE_KEY in .env")
        return 1

    pid = f"smoke-prospect-{uuid.uuid4().hex[:8]}"
    sid = f"smoke-session-{uuid.uuid4().hex[:8]}"
    print(f"Using prospect_id={pid}, session_id={sid}")

    # 1. Prospect
    await prospects_repo.ensure_exists(pid, {"smoke": True})

    # 2. Build a fake ScoreResponse + persist session + candidates
    fake_response = ScoreResponse(
        job_summary=JobSummary(
            title="Smoke Test Forklift",
            location="Atlanta, GA",
            required_certifications=["OSHA"],
            key_skills=["forklift"],
        ),
        candidates=[
            CandidateScore(
                candidate_id=str(uuid.uuid4()),
                name="Smoke Candidate",
                score=82,
                score_band="strong",
                one_line_summary="smoke-test candidate",
                strengths=["s"],
                gaps=["g"],
                interview_questions=["q1", "q2", "q3"],
                location_match=LocationMatch(
                    candidate_location="Atlanta", distance_estimate_miles=5, commute_risk="low"
                ),
                experience_match=ExperienceMatch(
                    years_relevant=5.0, matches_requirement=True, notes="smoke"
                ),
                raw_resume_text="this should NOT land in candidate_scores.scoring_details",
            )
        ],
        metadata=ScoringMetadata(
            processing_time_ms=42,
            model_parser="gpt-4o-mini",
            model_scorer="gpt-4o",
        ),
        session_id=sid,
    )

    await sessions_repo.record_session(
        session_id=sid,
        prospect_id=pid,
        response=fake_response,
        ip_address="127.0.0.1",
        user_agent="smoke",
    )
    await prospects_repo.increment_tool_use(pid, 1)
    await events_repo.record_event(
        prospect_id=pid, event_type="tool_used", event_data={"smoke": True}
    )
    await leads_repo.record_lead(
        email="smoke@example.com", prospect_id=pid, source="smoke_test", metadata={"smoke": True}
    )

    # 3. Read back what we wrote (service-role bypasses RLS)
    client = get_client()
    assert client is not None
    print("\n--- prospect row ---")
    print(client.table("prospects").select("*").eq("prospect_id", pid).execute().data)
    print("\n--- scoring_session row ---")
    print(client.table("scoring_sessions").select("*").eq("session_id", sid).execute().data)
    print("\n--- candidate_scores rows ---")
    cs = client.table("candidate_scores").select("*").eq("session_id", sid).execute().data
    print(cs)
    if cs:
        details = cs[0].get("scoring_details", {})
        assert "raw_resume_text" not in details, (
            "PII LEAK: raw_resume_text persisted to candidate_scores.scoring_details"
        )
        print("  -> raw_resume_text correctly redacted from scoring_details")
    print("\n--- events row ---")
    print(client.table("prospect_events").select("*").eq("prospect_id", pid).execute().data)
    print("\n--- lead row ---")
    print(client.table("leads").select("*").eq("prospect_id", pid).execute().data)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
