"""Hard gate: scoring the same (JD, resume) 3 times yields ≤ 5-point variance.

Independent of corpus quality — purely tests the scorer's determinism. Costs
~5 (JD, resume) × 3 runs × ~$0.01 = ~$0.15.
"""

from __future__ import annotations

import time
from statistics import mean

import pytest

from src.core.graphs.nodes import build_score_response
from src.core.graphs.scoring_graph import get_scoring_graph
from tests.quality.conftest import CorpusJD, CorpusResume


# 5 representative pairs spanning bands across multiple JDs.
TARGETS = [
    ("forklift_atlanta", "strong"),
    ("forklift_atlanta", "weak"),
    ("warehouse_dallas", "moderate"),
    ("cdl_driver_columbus", "strong"),
    ("dock_worker_charlotte", "weak"),
]


def _pick_one(jd: CorpusJD, band: str) -> CorpusResume:
    for r in jd.resumes:
        if r.intended_band == band:
            return r
    raise AssertionError(f"No resume with band={band} for jd={jd.slug}")


async def _score_single(jd: CorpusJD, resume: CorpusResume) -> int:
    graph = get_scoring_graph()
    initial_state = {
        "jd_text": jd.text,
        "raw_resumes": [
            {
                "filename": resume.path.name,
                "content": resume.text.encode("utf-8"),
                "mimetype": "text/plain",
            }
        ],
        "session_id": f"consistency-{jd.slug}-{resume.path.stem}",
        "started_at": time.perf_counter(),
        "candidate_scores": [],
        "failed_resumes": [],
        "cost_records": [],
    }
    final = await graph.ainvoke(initial_state)
    response = build_score_response(final)
    assert response.candidates, f"No candidates scored for {jd.slug} / {resume.path.name}"
    return response.candidates[0].score


@pytest.mark.parametrize("jd_slug,band", TARGETS)
async def test_consistency_within_5_points(
    corpus: list[CorpusJD], jd_slug: str, band: str
) -> None:
    jd = next(j for j in corpus if j.slug == jd_slug)
    resume = _pick_one(jd, band)

    scores = []
    for _ in range(3):
        scores.append(await _score_single(jd, resume))

    spread = max(scores) - min(scores)
    print(
        f"[consistency] {jd_slug:25s} band={band:8s} scores={scores} "
        f"spread={spread} mean={mean(scores):.1f}"
    )
    assert spread <= 5, (
        f"Score variance too high for {jd_slug}/{band}: "
        f"got {scores} (spread={spread}, allowed=5). "
        f"Lower temperature in the scorer or sharpen the rubric."
    )
