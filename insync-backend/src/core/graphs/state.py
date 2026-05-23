"""ScoringState for the LangGraph workflow.

Reducer-typed lists let parallel `Send`-fan-out workers each return a list-of-one
and have the graph merge them automatically — the canonical LangGraph parallel
fan-out pattern.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class RawResume(TypedDict):
    filename: str
    content: bytes
    mimetype: str | None


class CostRecord(TypedDict):
    node: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class FailedResume(TypedDict):
    filename: str
    error: str
    stage: str  # "parse" | "score"


class ScoringState(TypedDict, total=False):
    # Inputs (set at graph entry; never mutated)
    jd_text: str
    raw_resumes: list[RawResume]
    session_id: str
    started_at: float  # time.perf_counter() at entry

    # Parsed JD (set by parse_jd node)
    parsed_jd: dict[str, Any] | None

    # Per-worker reducers (each worker returns list-of-one; reducer concats)
    candidate_scores: Annotated[list[dict[str, Any]], operator.add]
    failed_resumes: Annotated[list[FailedResume], operator.add]
    cost_records: Annotated[list[CostRecord], operator.add]

    # Final aggregation output
    job_summary: dict[str, Any] | None
    final_candidates: list[dict[str, Any]] | None
    metadata: dict[str, Any] | None


class WorkerInput(TypedDict):
    """Payload Send() passes to each parallel parse_and_score_resume worker."""

    resume: RawResume
    parsed_jd: dict[str, Any]
    session_id: str
