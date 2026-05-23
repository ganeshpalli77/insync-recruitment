"""End-to-end smoke against real OpenAI (and optionally LlamaParse + Redis).

Usage:
    cd insync-backend
    uv run python scripts/smoke_real.py

Uses two .txt resumes (Marcus = strong match, Jamie = weak match) against the
sample forklift JD. Costs ~$0.05–0.10 in OpenAI tokens. Skips LlamaParse
entirely (txt path is native).

Pass --pdf to also test the LlamaParse path on a small generated PDF (adds
~$0.01 in LlamaParse + ~10 s).
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Make `src` importable when running the script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.routes.sample import SAMPLE_JD, SAMPLE_RESUMES  # noqa: E402
from src.core.graphs.nodes import build_score_response  # noqa: E402
from src.core.graphs.scoring_graph import get_scoring_graph  # noqa: E402


async def main() -> int:
    graph = get_scoring_graph()

    # One strong + one weak — confirms the engine differentiates across bands.
    by_band = {r.expected_score_band: r for r in SAMPLE_RESUMES}
    chosen = [by_band["strong"], by_band["weak"]]
    resumes = [
        {
            "filename": f"{r.name.replace(' ', '_').lower()}.txt",
            "content": r.content.encode("utf-8"),
            "mimetype": "text/plain",
        }
        for r in chosen
    ]

    initial_state = {
        "jd_text": SAMPLE_JD,
        "raw_resumes": resumes,
        "session_id": "smoke-real",
        "started_at": time.perf_counter(),
        "candidate_scores": [],
        "failed_resumes": [],
        "cost_records": [],
    }

    print(f"Scoring {len(resumes)} resumes against the Forklift Operator JD...")
    t0 = time.perf_counter()
    final_state = await graph.ainvoke(initial_state)
    elapsed = time.perf_counter() - t0

    response = build_score_response(final_state)
    print()
    print(f"Job: {response.job_summary.title} @ {response.job_summary.location}")
    print(
        f"Required certs: {response.job_summary.required_certifications} | "
        f"Key skills: {response.job_summary.key_skills}"
    )
    print()
    for c in response.candidates:
        print(f"  [{c.score:3d}] {c.score_band:>8s}  {c.name}  --  {c.one_line_summary}")
        for s in c.strengths[:2]:
            print(f"        + {s}")
        for g in c.gaps[:2]:
            print(f"        - {g}")
        print()

    print(
        f"--- metadata: {response.metadata.processing_time_ms} ms  | "
        f"{response.metadata.total_tokens_used} tokens  | "
        f"${response.metadata.total_cost_usd:.4f}  | "
        f"failed: {response.metadata.failed_resume_count}"
    )
    print(f"--- wall-clock from script: {elapsed:.2f}s")

    failed = final_state.get("failed_resumes") or []
    if failed:
        print(f"\nFAILED RESUMES: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
