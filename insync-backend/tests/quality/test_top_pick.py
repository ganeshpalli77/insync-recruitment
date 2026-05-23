"""Soft gate (informational, never fails): does the AI's #1-ranked candidate
sit in the intended-strong set for each JD?

Per the plan, "AI #1 ranked candidate is in human's top-3 for >= 4/5 JDs" is
aspirational, not enforced — synthetic-corpus generation drifts on resume
quality so the ground-truth bands are noisy. Hard-gate this only when the
corpus is real.
"""

from __future__ import annotations

import pytest

from src.schemas.score import ScoreResponse
from tests.quality.conftest import CorpusJD, candidates_by_intended_resume

WARN_THRESHOLD_JDS = 4  # what we'd want once corpus is real (4 of 5)


def test_top_pick_lands_in_strong_set(
    scored_jds: dict[str, tuple[CorpusJD, ScoreResponse]]
) -> None:
    wins = 0
    total = 0
    per_jd: list[str] = []

    for jd_slug, (jd, response) in scored_jds.items():
        if not response.candidates:
            continue
        total += 1

        # Map candidate_id -> intended_band for this JD.
        pairs = list(candidates_by_intended_resume(jd, response))
        if not pairs:
            per_jd.append(f"  {jd_slug}: unable to map candidates back to fixtures (skipped)")
            continue
        by_candidate_id: dict[str, str] = {c.candidate_id: r.intended_band for r, c in pairs}

        top_candidate = response.candidates[0]  # already sorted desc by score
        intended = by_candidate_id.get(top_candidate.candidate_id, "unknown")
        is_strong = intended == "strong"
        wins += 1 if is_strong else 0
        per_jd.append(
            f"  {jd_slug}: #1 = {top_candidate.name!r} score={top_candidate.score} "
            f"intended={intended} {'OK' if is_strong else 'MISS'}"
        )

    print(f"\n[top_pick] {wins}/{total} JDs had a strong candidate at #1")
    for line in per_jd:
        print(line)

    if wins < WARN_THRESHOLD_JDS:
        print(
            f"[top_pick] WARN: only {wins}/{total} (target {WARN_THRESHOLD_JDS}/{total}) "
            f"-- synthetic strong vs moderate resumes likely too similar; "
            f"replace corpus with hand-labeled resumes for trustworthy signal."
        )
    # Smoke assertion only: we got at least one JD's worth of scored candidates.
    assert total > 0
