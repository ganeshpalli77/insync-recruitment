"""Send one test email via Resend to verify RESEND_API_KEY + EMAIL_FROM.

Renders the real jinja template with a fake 3-candidate ScoreResponse so you
can eyeball the actual production formatting in your inbox.

    uv run python scripts/smoke_resend.py <to-address>
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schemas.common import JobSummary  # noqa: E402
from src.schemas.score import (  # noqa: E402
    CandidateScore,
    ExperienceMatch,
    LocationMatch,
    ScoringMetadata,
)
from src.services.email_sender import send_results_email  # noqa: E402


def _fake_candidate(rank: int, score: int, band: str, name: str) -> CandidateScore:
    return CandidateScore(
        candidate_id=str(uuid.uuid4()),
        name=name,
        score=score,
        score_band=band,  # type: ignore[arg-type]
        one_line_summary=f"{8 - rank} yrs forklift • OSHA Class I, IV • Atlanta, GA",
        strengths=[
            f"{8 - rank} years forklift operation, exceeds 3-year requirement",
            "OSHA Class I and IV certifications, meets requirement",
        ],
        gaps=["No bilingual Spanish mentioned", "No CDL Class A noted"],
        interview_questions=[
            "Walk through your busiest cross-dock shift.",
            "Which WMS systems have you used in depth?",
            "Why are you considering leaving your current role?",
        ],
        location_match=LocationMatch(
            candidate_location="Atlanta, GA",
            distance_estimate_miles=8 + rank * 4,
            commute_risk="low",
        ),
        experience_match=ExperienceMatch(
            years_relevant=float(8 - rank),
            matches_requirement=True,
            notes="Recent and continuous logistics tenure.",
        ),
        raw_resume_text="",
    )


async def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/smoke_resend.py <to-address>")
        return 2
    to = sys.argv[1]

    job_summary = JobSummary(
        title="Forklift Operator",
        location="Atlanta, GA",
        company="Atlas Distribution",
        required_experience_years=3,
        required_certifications=["OSHA forklift"],
        key_skills=["reach truck", "counterbalance", "WMS"],
    )
    candidates = [
        _fake_candidate(0, 95, "strong", "Marcus Williams"),
        _fake_candidate(1, 78, "strong", "Sarah Johnson"),
        _fake_candidate(2, 52, "moderate", "Derek Chen"),
    ]
    metadata = ScoringMetadata(
        processing_time_ms=18_400,
        model_parser="gpt-4o-mini",
        model_scorer="gpt-4o",
        total_tokens_used=4830,
        total_cost_usd=0.0117,
    )

    print(f"Sending test results email to {to}...")
    ok, detail = await send_results_email(
        to=to,
        job_summary=job_summary,
        candidates=candidates,
        session_id=f"resend-smoke-{uuid.uuid4().hex[:8]}",
        metadata=metadata,
    )
    if ok:
        print(f"OK — Resend message id: {detail}")
        print("Check your inbox (and spam folder). If running on Windows the PDF")
        print("attachment will be skipped (WeasyPrint needs GTK); HTML body still arrives.")
        return 0
    else:
        print(f"FAILED — {detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
