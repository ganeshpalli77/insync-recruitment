"""LangGraph wiring for the scoring workflow.

START → parse_jd → (Send-fan-out per resume) → parse_and_score_resume
                                                       │
                                                       ▼
                                          aggregate_and_normalize
                                                       │
                                                       ▼
                                                quality_check → END
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import Send

from src.core.graphs.nodes import (
    aggregate_and_normalize_node,
    parse_and_score_resume_node,
    parse_jd_node,
    quality_check_node,
)
from src.core.graphs.state import ScoringState


def _dispatch_to_workers(state: ScoringState) -> list[Send]:
    parsed_jd = state.get("parsed_jd") or {}
    return [
        Send(
            "parse_and_score_resume",
            {
                "resume": r,
                "parsed_jd": parsed_jd,
                "session_id": state.get("session_id", ""),
            },
        )
        for r in state.get("raw_resumes", [])
    ]


@lru_cache(maxsize=1)
def get_scoring_graph():
    g = StateGraph(ScoringState)
    g.add_node("parse_jd", parse_jd_node)
    g.add_node("parse_and_score_resume", parse_and_score_resume_node)
    g.add_node("aggregate_and_normalize", aggregate_and_normalize_node)
    g.add_node("quality_check", quality_check_node)

    g.add_edge(START, "parse_jd")
    g.add_conditional_edges(
        "parse_jd", _dispatch_to_workers, ["parse_and_score_resume"]
    )
    g.add_edge("parse_and_score_resume", "aggregate_and_normalize")
    g.add_edge("aggregate_and_normalize", "quality_check")
    g.add_edge("quality_check", END)

    return g.compile()
