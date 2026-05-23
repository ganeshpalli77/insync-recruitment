"""quality_check + normalization for raw LLM candidate outputs.

Two goals:
1. Coerce LLM output to the wire schema (`CandidateScore`) so the frontend never
   sees a malformed object.
2. Sanity-check the score distribution; if every candidate scored 80+, log a
   warning (per spec, would also trigger a stricter re-score — for Phase 2 we
   log and continue; re-scoring is a follow-up if quality regression appears).
"""

from __future__ import annotations

import uuid
from typing import Any

from loguru import logger

from src.schemas.score import (
    CandidateScore,
    ExperienceMatch,
    LocationMatch,
)

_RAW_RESUME_PREVIEW_CHARS = 500


def _band_from_score(score: int) -> str:
    if score >= 70:
        return "strong"
    if score >= 40:
        return "moderate"
    return "weak"


def _ensure_min(items: list[str] | None, fallback: str) -> list[str]:
    items = [s for s in (items or []) if isinstance(s, str) and s.strip()]
    return items if items else [fallback]


def _coerce_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_candidate(
    *,
    raw: dict[str, Any],
    candidate_name: str,
    raw_resume_text: str,
) -> CandidateScore:
    """Turn one raw LLM score JSON into a valid wire-schema CandidateScore."""

    score = _coerce_int(raw.get("score"), 0, 100, default=0)
    band = raw.get("score_band")
    if band not in {"strong", "moderate", "weak"}:
        band = _band_from_score(score)

    one_line = (raw.get("one_line_summary") or "").strip() or candidate_name
    if len(one_line) > 120:
        one_line = one_line[:117] + "..."

    loc = raw.get("location_assessment") or {}
    commute = loc.get("commute_risk")
    if commute not in {"low", "medium", "high", "unknown"}:
        commute = "unknown"
    location_match = LocationMatch(
        candidate_location=loc.get("candidate_location") or None,
        distance_estimate_miles=(
            _coerce_int(loc.get("distance_estimate_miles"), 0, 10_000, default=0)
            if loc.get("distance_estimate_miles") is not None
            else None
        ),
        commute_risk=commute,  # type: ignore[arg-type]
    )

    exp = raw.get("experience_assessment") or {}
    experience_match = ExperienceMatch(
        years_relevant=_coerce_float(exp.get("years_relevant"), 0.0),
        matches_requirement=bool(exp.get("matches_requirement", False)),
        notes=str(exp.get("notes") or "No experience notes provided."),
    )

    return CandidateScore(
        candidate_id=str(uuid.uuid4()),
        name=candidate_name,
        score=score,
        score_band=band,  # type: ignore[arg-type]
        one_line_summary=one_line,
        strengths=_ensure_min(raw.get("strengths"), "No specific strengths identified."),
        gaps=_ensure_min(raw.get("gaps"), "No specific gaps identified."),
        interview_questions=_ensure_min(
            raw.get("interview_questions"),
            "Walk me through your most recent relevant role.",
        ),
        location_match=location_match,
        experience_match=experience_match,
        raw_resume_text=raw_resume_text[:_RAW_RESUME_PREVIEW_CHARS],
    )


def warn_if_distribution_suspicious(candidates: list[CandidateScore]) -> None:
    """Per spec: if every candidate in a batch scored 80+, something is off."""
    if len(candidates) < 5:
        return
    if all(c.score >= 80 for c in candidates):
        logger.warning(
            "score_distribution_suspicious | n={} all_scores>=80",
            len(candidates),
        )
