"""LangGraph nodes for the scoring workflow.

Layout:
    parse_jd                    (one LLM call)
       │
       └─► (Send fan-out per resume) ──► parse_and_score_resume  (LlamaParse + 2 LLM calls)
                                              │
                                              ▼
                                   aggregate_and_normalize
                                              │
                                              ▼
                                       quality_check ──► END
"""

from __future__ import annotations

import json
import time
from typing import Any

from loguru import logger

from src.config import get_settings
from src.core.graphs.state import ScoringState, WorkerInput
from src.core.llm.client import chat_json
from src.core.llm.prompts import (
    PARSE_JD_SYSTEM,
    PARSE_RESUME_SYSTEM,
    SCORE_CANDIDATE_SYSTEM,
)
from src.core.parsers import parse_resume_bytes
from src.core.scoring.validator import (
    normalize_candidate,
    warn_if_distribution_suspicious,
)
from src.schemas.common import JobSummary
from src.schemas.score import ScoreResponse, ScoringMetadata
from src.services.cache import get_cached_parsed_jd, set_cached_parsed_jd


# ---------------------------------------------------------------------------
# Node 1: parse_jd
# ---------------------------------------------------------------------------


async def parse_jd_node(state: ScoringState) -> dict[str, Any]:
    jd_text = state["jd_text"]

    cached = await get_cached_parsed_jd(jd_text)
    if cached is not None:
        logger.info("parse_jd_cache_hit")
        return {"parsed_jd": cached}

    settings = get_settings()
    call = await chat_json(
        model=settings.openai_model_parser,
        system=PARSE_JD_SYSTEM,
        user=jd_text,
        temperature=0.1,
        max_tokens=800,
    )
    await set_cached_parsed_jd(jd_text, call.parsed)

    return {
        "parsed_jd": call.parsed,
        "cost_records": [
            {
                "node": "parse_jd",
                "model": call.model,
                "prompt_tokens": call.prompt_tokens,
                "completion_tokens": call.completion_tokens,
                "cost_usd": call.cost,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Node 2: parse_and_score_resume  (called once per resume via Send)
# ---------------------------------------------------------------------------


async def parse_and_score_resume_node(state: WorkerInput) -> dict[str, Any]:
    resume = state["resume"]
    parsed_jd = state["parsed_jd"]
    filename = resume["filename"]
    settings = get_settings()

    # Step 1: bytes → plain text
    try:
        parsed_file = await parse_resume_bytes(filename, resume["content"])
    except Exception as e:  # noqa: BLE001
        logger.exception("resume_parse_failed | filename={}", filename)
        return {
            "failed_resumes": [
                {"filename": filename, "error": str(e)[:300], "stage": "parse"}
            ]
        }

    if not parsed_file.text.strip():
        return {
            "failed_resumes": [
                {
                    "filename": filename,
                    "error": "Parsed resume text was empty.",
                    "stage": "parse",
                }
            ]
        }

    cost_records: list[dict[str, Any]] = []

    # Step 2: structure the resume
    try:
        parse_call = await chat_json(
            model=settings.openai_model_parser,
            system=PARSE_RESUME_SYSTEM,
            user=parsed_file.text,
            temperature=0.1,
            max_tokens=1500,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("resume_structure_failed | filename={}", filename)
        return {
            "failed_resumes": [
                {"filename": filename, "error": str(e)[:300], "stage": "parse"}
            ]
        }
    cost_records.append(
        {
            "node": "parse_resume",
            "model": parse_call.model,
            "prompt_tokens": parse_call.prompt_tokens,
            "completion_tokens": parse_call.completion_tokens,
            "cost_usd": parse_call.cost,
        }
    )

    parsed_resume = parse_call.parsed
    candidate_name = (parsed_resume.get("name") or filename).strip() or filename

    # Step 3: score against parsed_jd  (gpt-4o — the high-stakes call)
    score_user_prompt = (
        "PARSED_JD:\n"
        + json.dumps(parsed_jd, indent=2)
        + "\n\nPARSED_RESUME:\n"
        + json.dumps(parsed_resume, indent=2)
    )
    try:
        score_call = await chat_json(
            model=settings.openai_model_scorer,
            system=SCORE_CANDIDATE_SYSTEM,
            user=score_user_prompt,
            temperature=0.2,
            top_p=0.95,
            max_tokens=1500,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("candidate_score_failed | filename={}", filename)
        return {
            "failed_resumes": [
                {"filename": filename, "error": str(e)[:300], "stage": "score"}
            ],
            "cost_records": cost_records,
        }
    cost_records.append(
        {
            "node": "score_candidate",
            "model": score_call.model,
            "prompt_tokens": score_call.prompt_tokens,
            "completion_tokens": score_call.completion_tokens,
            "cost_usd": score_call.cost,
        }
    )

    candidate = normalize_candidate(
        raw=score_call.parsed,
        candidate_name=candidate_name,
        raw_resume_text=parsed_file.text,
    )

    return {
        "candidate_scores": [candidate.model_dump()],
        "cost_records": cost_records,
    }


# ---------------------------------------------------------------------------
# Node 3: aggregate_and_normalize
# ---------------------------------------------------------------------------


def _job_summary_from_parsed(parsed_jd: dict[str, Any]) -> JobSummary:
    return JobSummary(
        title=str(parsed_jd.get("title") or "Untitled role"),
        location=str(parsed_jd.get("location") or "Unknown"),
        company=parsed_jd.get("company") or None,
        required_experience_years=(
            int(parsed_jd["required_experience_years"])
            if isinstance(parsed_jd.get("required_experience_years"), (int, float))
            else None
        ),
        required_certifications=list(parsed_jd.get("required_certifications") or []),
        key_skills=list(parsed_jd.get("key_skills") or []),
    )


async def aggregate_and_normalize_node(state: ScoringState) -> dict[str, Any]:
    parsed_jd = state.get("parsed_jd") or {}
    raw_candidates = state.get("candidate_scores") or []
    cost_records = state.get("cost_records") or []
    failed = state.get("failed_resumes") or []
    started_at = state.get("started_at") or time.perf_counter()

    # Already-validated CandidateScore dicts → re-instantiate, sort, re-dump.
    from src.schemas.score import CandidateScore  # local import to avoid cycle

    candidates = [CandidateScore.model_validate(c) for c in raw_candidates]
    candidates.sort(key=lambda c: c.score, reverse=True)
    warn_if_distribution_suspicious(candidates)

    settings = get_settings()
    total_tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in cost_records)
    total_cost = sum(r["cost_usd"] for r in cost_records)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)

    metadata = ScoringMetadata(
        processing_time_ms=elapsed_ms,
        model_parser=settings.openai_model_parser,
        model_scorer=settings.openai_model_scorer,
        total_tokens_used=total_tokens,
        total_cost_usd=round(total_cost, 6),
        cache_hit=False,
        failed_resume_count=len(failed),
    )

    return {
        "job_summary": _job_summary_from_parsed(parsed_jd).model_dump(),
        "final_candidates": [c.model_dump() for c in candidates],
        "metadata": metadata.model_dump(),
    }


# ---------------------------------------------------------------------------
# Node 4: quality_check  (final guardrail)
# ---------------------------------------------------------------------------


async def quality_check_node(state: ScoringState) -> dict[str, Any]:
    candidates = state.get("final_candidates") or []
    if not candidates and not (state.get("failed_resumes") or []):
        logger.error("quality_check_empty | session_id={}", state.get("session_id"))
    return {}


# ---------------------------------------------------------------------------
# Helper: build the final ScoreResponse object
# ---------------------------------------------------------------------------


def build_score_response(state: ScoringState) -> ScoreResponse:
    return ScoreResponse(
        job_summary=JobSummary.model_validate(state["job_summary"]),
        candidates=[c for c in state.get("final_candidates") or []],  # type: ignore[misc]
        metadata=ScoringMetadata.model_validate(state["metadata"]),
        session_id=state["session_id"],
    )
