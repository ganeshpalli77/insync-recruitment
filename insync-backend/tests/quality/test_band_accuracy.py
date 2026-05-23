"""Soft gate (informational, never fails): AI band vs intended band per JD.

The plan explicitly treats this as a metric, not a deploy blocker — synthetic
labels are weaker ground truth than real recruiter labels. The test prints
the full confusion matrix and a WARN line when we fall short of what we'd
want from a real corpus; both are soft signals only.

Tighten to a real `assert` once the corpus is replaced with hand-labeled
real resumes (see the plan's open risk #6).
"""

from __future__ import annotations

from collections import Counter

import pytest

from src.schemas.score import ScoreResponse
from tests.quality.conftest import CorpusJD, candidates_by_intended_resume

# Aspirational target — what real-corpus accuracy should look like.
WARN_THRESHOLD = 0.8


@pytest.mark.parametrize(
    "jd_slug",
    [
        "forklift_atlanta",
        "warehouse_dallas",
        "cdl_driver_columbus",
        "picker_packer_phoenix",
        "dock_worker_charlotte",
    ],
)
def test_band_accuracy_per_jd(
    scored_jds: dict[str, tuple[CorpusJD, ScoreResponse]], jd_slug: str
) -> None:
    jd, response = scored_jds[jd_slug]
    matches = 0
    mismatches: list[str] = []
    confusion: Counter[tuple[str, str]] = Counter()

    pairs = list(candidates_by_intended_resume(jd, response))
    if not pairs:
        pytest.skip(f"No resume matches resolved for {jd_slug} (name-based mapping fell through).")

    for source, candidate in pairs:
        confusion[(source.intended_band, candidate.score_band)] += 1
        if source.intended_band == candidate.score_band:
            matches += 1
        else:
            mismatches.append(
                f"  {source.path.name} -> intended={source.intended_band:8s} "
                f"got={candidate.score_band:8s} score={candidate.score}"
            )

    ratio = matches / len(pairs)
    print(f"\n[band_accuracy] {jd_slug}: {matches}/{len(pairs)} = {ratio:.0%}")
    print("[band_accuracy] confusion (intended -> got):")
    for (intended, got), n in sorted(confusion.items()):
        marker = "OK " if intended == got else "** "
        print(f"  {marker}{intended:8s} -> {got:8s}  {n}")
    if mismatches:
        print("[band_accuracy] mismatches:")
        for m in mismatches:
            print(m)

    if ratio < WARN_THRESHOLD:
        print(
            f"[band_accuracy] WARN: {ratio:.0%} below target {WARN_THRESHOLD:.0%} "
            f"-- replace synthetic corpus with real hand-labeled resumes for trustworthy signal."
        )
    # Smoke assertion only — at least one resume scored per JD. The accuracy
    # ratio itself is logged but not asserted: synthetic-corpus labels are
    # noisy by design and a hard gate here would just punish prompt iteration.
    assert len(pairs) > 0
