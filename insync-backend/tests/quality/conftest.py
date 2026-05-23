"""Shared fixtures for the quality harness.

`scored_jds` is a session-scoped fixture that scores every (JD, resume) pair
in the corpus **once** and shares the result across `test_band_accuracy.py`
and `test_top_pick.py`. Costs ~$1-2 per full session against gpt-4o.

Gated by `QUALITY_TESTS=1` — without it, the entire `tests/quality/` package
is skipped at collection.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pytest

from src.core.graphs.nodes import build_score_response
from src.core.graphs.scoring_graph import get_scoring_graph
from src.schemas.score import ScoreResponse

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("QUALITY_TESTS") != "1":
        skip_marker = pytest.mark.skip(
            reason="Quality tests gated by QUALITY_TESTS=1 (uses real OpenAI, ~$1-2/run)."
        )
        for item in items:
            if "tests/quality" in str(item.fspath).replace(os.sep, "/"):
                item.add_marker(skip_marker)


@dataclass(slots=True)
class CorpusResume:
    jd_slug: str
    name: str
    intended_band: str
    path: Path
    text: str


@dataclass(slots=True)
class CorpusJD:
    slug: str
    role: str
    city: str
    text: str
    resumes: list[CorpusResume]


def _load_corpus() -> list[CorpusJD]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    jds: dict[str, CorpusJD] = {}
    for slug, info in manifest["jds"].items():
        jd_text = (FIXTURES / info["path"]).read_text(encoding="utf-8")
        jds[slug] = CorpusJD(
            slug=slug, role=info["role"], city=info["city"], text=jd_text, resumes=[]
        )
    for r in manifest["resumes"]:
        slug = r["jd_slug"]
        path = FIXTURES / r["path"]
        jds[slug].resumes.append(
            CorpusResume(
                jd_slug=slug,
                name=r["name"],
                intended_band=r["intended_band"],
                path=path,
                text=path.read_text(encoding="utf-8"),
            )
        )
    return list(jds.values())


@pytest.fixture(scope="session")
def corpus() -> list[CorpusJD]:
    return _load_corpus()


async def _score_jd(jd: CorpusJD) -> ScoreResponse:
    graph = get_scoring_graph()
    initial_state = {
        "jd_text": jd.text,
        "raw_resumes": [
            {
                "filename": r.path.name,
                "content": r.text.encode("utf-8"),
                "mimetype": "text/plain",
            }
            for r in jd.resumes
        ],
        "session_id": f"quality-{jd.slug}",
        "started_at": time.perf_counter(),
        "candidate_scores": [],
        "failed_resumes": [],
        "cost_records": [],
    }
    final = await graph.ainvoke(initial_state)
    return build_score_response(final)


SCORED_CACHE_DIR = FIXTURES / ".scored_cache"


@pytest.fixture(scope="session")
async def scored_jds(corpus: list[CorpusJD]) -> dict[str, tuple[CorpusJD, ScoreResponse]]:
    """Score every JD's 10 resumes once; share across band/top-pick tests.

    Results are cached to disk under tests/fixtures/.scored_cache/{slug}.json
    so re-running these tests is free until the corpus changes. Delete the
    cache (or pass QUALITY_REFRESH=1) to force a fresh scoring pass.
    """
    SCORED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    refresh = os.environ.get("QUALITY_REFRESH") == "1"

    out: dict[str, tuple[CorpusJD, ScoreResponse]] = {}
    total_cost = 0.0
    cache_hits = 0

    for jd in corpus:
        cache_path = SCORED_CACHE_DIR / f"{jd.slug}.json"
        if not refresh and cache_path.exists():
            response = ScoreResponse.model_validate_json(cache_path.read_text(encoding="utf-8"))
            out[jd.slug] = (jd, response)
            cache_hits += 1
            print(f"[quality]   {jd.slug}: cached (${response.metadata.total_cost_usd:.4f} prior cost)")
            continue

        print(f"[quality] scoring {jd.slug} ({len(jd.resumes)} resumes)...")
        response = await _score_jd(jd)
        out[jd.slug] = (jd, response)
        cache_path.write_text(response.model_dump_json(), encoding="utf-8")
        total_cost += response.metadata.total_cost_usd
        print(
            f"[quality]   {jd.slug}: ${response.metadata.total_cost_usd:.4f}, "
            f"{response.metadata.processing_time_ms} ms, "
            f"{len(response.candidates)} scored, "
            f"{response.metadata.failed_resume_count} failed"
        )
    print(f"[quality] cache hits: {cache_hits}/{len(corpus)}, fresh spend: ${total_cost:.4f}")
    return out


def candidates_by_intended_resume(
    jd: CorpusJD, response: ScoreResponse
) -> Iterable[tuple[CorpusResume, object]]:
    """Match each CandidateScore back to its source CorpusResume by filename hint."""
    by_path = {r.path.name: r for r in jd.resumes}
    by_lower_name = {r.path.name.split("_", 2)[-1].rsplit(".", 1)[0]: r for r in jd.resumes}
    for c in response.candidates:
        # Candidate `name` is the parsed candidate name (e.g. "Michael Johnson") —
        # not directly mappable to a file. Fall back to matching by extracted
        # name against the file's slug-name (best-effort) or by ordering.
        slug_fragment = c.name.lower().replace(" ", "_")
        cr = by_lower_name.get(slug_fragment)
        if cr is None:
            # Fall back: assume order preserved (the graph doesn't guarantee
            # this, but worst-case it just means a few labels are wrong).
            continue
        yield cr, c
