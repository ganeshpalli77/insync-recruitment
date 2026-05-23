"""POST /api/score — main scoring endpoint.

SSE streaming by default; JSON via ?stream=false. Caches full results by
(jd + file hashes + model versions) for 1h.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from src.api.deps import client_ip
from src.config import get_settings
from src.core.graphs.nodes import build_score_response
from src.core.graphs.scoring_graph import get_scoring_graph
from src.db.repositories import events as events_repo
from src.db.repositories import prospects as prospects_repo
from src.db.repositories import sessions as sessions_repo
from src.schemas.score import ScoreResponse
from src.services.crm_webhook import post_event as crm_post_event
from src.services.slack import alert_scoring_completed
from src.services.cache import (
    get_cached_score_response,
    hash_bytes,
    hash_score_key,
    set_cached_score_response,
)
from src.services.file_validator import matches_extension
from src.services.limiter import (
    enforce_daily_resume_cap,
    record_cost_and_maybe_alert,
)
from src.services.sanitizer import clean_text

router = APIRouter(prefix="/api", tags=["score"])

_ACCEPTED_EXT = {".pdf", ".docx", ".txt"}

# Headers that tell intermediary proxies (Cloudflare, NGINX) NOT to buffer
# the SSE response. Without these, long LlamaParse pauses can trigger an
# idle-connection kill before the result event ever leaves the origin.
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-store, no-transform, must-revalidate",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
_MAX_FILES = 100
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_BATCH_BYTES = 100 * 1024 * 1024
_MIN_JD_CHARS = 50
_MAX_JD_CHARS = 10_000
_BATCH_TIMEOUT_SECONDS = 90


def _ext(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""


def _validate_jd(jd: str) -> None:
    n = len(jd or "")
    if n < _MIN_JD_CHARS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Job description too short (min {_MIN_JD_CHARS} chars).",
        )
    if n > _MAX_JD_CHARS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Job description too long (max {_MAX_JD_CHARS} chars).",
        )


async def _read_uploads(resumes: list[UploadFile]) -> list[dict[str, Any]]:
    if not resumes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one resume is required.")
    if len(resumes) > _MAX_FILES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Too many resumes (max {_MAX_FILES} per batch)."
        )

    out: list[dict[str, Any]] = []
    total_bytes = 0
    for f in resumes:
        ext = _ext(f.filename or "")
        if ext not in _ACCEPTED_EXT:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Unsupported file type: {f.filename}. Accepted: PDF, DOCX, TXT.",
            )
        content = await f.read()
        if len(content) > _MAX_FILE_BYTES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"File too large: {f.filename} (max 10 MB per file).",
            )
        total_bytes += len(content)
        if total_bytes > _MAX_BATCH_BYTES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Total batch size exceeds 100 MB.",
            )
        if not matches_extension(f.filename or "", content):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"File contents don't match extension: {f.filename}.",
            )
        out.append(
            {
                "filename": f.filename or f"unknown-{uuid.uuid4().hex[:8]}",
                "content": content,
                "mimetype": f.content_type,
            }
        )
    return out


async def _run_graph(jd_text: str, resumes: list[dict[str, Any]], session_id: str) -> ScoreResponse:
    graph = get_scoring_graph()
    initial_state = {
        "jd_text": jd_text,
        "raw_resumes": resumes,
        "session_id": session_id,
        "started_at": time.perf_counter(),
        "candidate_scores": [],
        "failed_resumes": [],
        "cost_records": [],
    }
    final_state = await asyncio.wait_for(
        graph.ainvoke(initial_state), timeout=_BATCH_TIMEOUT_SECONDS
    )
    return build_score_response(final_state)


async def _stream_graph(
    jd_text: str,
    resumes: list[dict[str, Any]],
    session_id: str,
    cache_key: str,
    *,
    prospect_id: str | None = None,
    ip: str = "unknown",
    user_agent: str | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE events: per-worker progress, then a final result (or error)."""
    graph = get_scoring_graph()
    initial_state = {
        "jd_text": jd_text,
        "raw_resumes": resumes,
        "session_id": session_id,
        "started_at": time.perf_counter(),
        "candidate_scores": [],
        "failed_resumes": [],
        "cost_records": [],
    }

    total = len(resumes)
    completed = 0
    final_state: dict[str, Any] | None = None

    try:
        # Single graph run yielding both per-node deltas (for progress events)
        # and the cumulative state (final element is the END state).
        stream = graph.astream(initial_state, stream_mode=["updates", "values"])
        async for mode, payload in _with_timeout(stream, _BATCH_TIMEOUT_SECONDS):
            if mode == "updates" and "parse_and_score_resume" in payload:
                completed += 1
                delta = payload["parse_and_score_resume"] or {}
                name = None
                if delta.get("candidate_scores"):
                    name = delta["candidate_scores"][0].get("name")
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        {"completed": completed, "total": total, "candidate_name": name}
                    ),
                }
            elif mode == "values":
                final_state = payload  # keep latest; last one is the END state
    except asyncio.TimeoutError:
        yield {
            "event": "error",
            "data": json.dumps({"message": "Scoring timed out (90s)."}),
        }
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("scoring_graph_failed | session_id={}", session_id)
        yield {
            "event": "error",
            "data": json.dumps({"message": f"Scoring failed: {e!s}"[:300]}),
        }
        return

    logger.info(
        "graph_complete | session_id={} candidates={} failed={}",
        session_id,
        len(final_state.get("candidate_scores") or []) if final_state else 0,
        len(final_state.get("failed_resumes") or []) if final_state else 0,
    )

    if final_state is None or not final_state.get("metadata"):
        logger.warning("scoring_no_final_state | session_id={}", session_id)
        yield {
            "event": "error",
            "data": json.dumps({"message": "Scoring produced no final state."}),
        }
        return

    try:
        response = build_score_response(final_state)
    except Exception as e:  # noqa: BLE001
        logger.exception("build_response_failed | session_id={}", session_id)
        yield {
            "event": "error",
            "data": json.dumps({"message": f"Building response failed: {e!s}"[:300]}),
        }
        return

    # Persist + cache + cost record — none of these should ever swallow the
    # result event. Belt-and-suspenders try/except in case any wrapped repo
    # function lets an exception escape.
    try:
        await set_cached_score_response(cache_key, response.model_dump())
        await record_cost_and_maybe_alert(response.metadata.total_cost_usd)
        await _persist_after_scoring(
            session_id=session_id,
            prospect_id=prospect_id,
            response=response,
            ip=ip,
            user_agent=user_agent,
        )
    except Exception:  # noqa: BLE001
        logger.exception("post_score_side_effects_failed | session_id={}", session_id)
        # Fall through — the user gets their result even if persistence broke.

    # Resolve *after* persist so an already-registered prospect's flag is
    # accurate even if the cache was written before this lookup.
    try:
        response.lead_registered = await _is_lead_registered(prospect_id)
    except Exception:  # noqa: BLE001
        logger.exception("lead_registered_lookup_failed | session_id={}", session_id)

    logger.info(
        "yielding_result_event | session_id={} candidate_count={} cost=${:.4f}",
        session_id,
        len(response.candidates),
        response.metadata.total_cost_usd,
    )
    yield {"event": "result", "data": response.model_dump_json()}


async def _with_timeout(stream: AsyncIterator[Any], timeout: float) -> AsyncIterator[Any]:
    """Per-yield deadline — caps wall-clock at ``timeout`` seconds total."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        try:
            item = await asyncio.wait_for(stream.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            return
        yield item


from src.services.limiter import get_limiter as _get_limiter  # noqa: E402

_limiter = _get_limiter()


async def _is_lead_registered(prospect_id: str | None) -> bool:
    """True if the prospect has already given us name+email+company.

    Live-checks the prospects table on every call (cheap — one indexed
    lookup) so stale cached responses don't make us re-prompt a user who
    already submitted the gate.
    """
    if not prospect_id:
        return False
    row = await prospects_repo.get_by_id(prospect_id)
    return bool(row and row.get("email"))


async def _persist_after_scoring(
    *,
    session_id: str,
    prospect_id: str | None,
    response: ScoreResponse,
    ip: str,
    user_agent: str | None,
) -> None:
    """Persist session + candidates + Track B event + CRM, and fire the
    per-scoring Slack alert if the prospect is already a known lead.

    For brand-new prospects (no email yet), Slack is deferred — it fires
    once from /api/lead/register when the user submits the email gate.
    """
    if prospect_id:
        await prospects_repo.ensure_exists(prospect_id, {"ip": ip})
    await sessions_repo.record_session(
        session_id=session_id,
        prospect_id=prospect_id,
        response=response,
        ip_address=ip,
        user_agent=user_agent,
    )
    if prospect_id:
        await prospects_repo.increment_tool_use(prospect_id, len(response.candidates))
        event_data = {
            "session_id": session_id,
            "candidate_count": len(response.candidates),
            "cost_usd": response.metadata.total_cost_usd,
        }
        await events_repo.record_event(
            prospect_id=prospect_id,
            event_type="tool_used",
            event_data=event_data,
            triggered_crm_webhook=True,
        )
        await crm_post_event(
            prospect_id=prospect_id, event_type="tool_used", event_data=event_data
        )

        # Slack-on-every-scoring, but only for already-registered leads.
        # We re-fetch *after* increment_tool_use so total_resumes_scored
        # reflects this run.
        try:
            row = await prospects_repo.get_by_id(prospect_id)
            if row and row.get("email"):
                await alert_scoring_completed(
                    name=str(row.get("name") or "(unknown)"),
                    company=str(row.get("company_name") or "(unknown)"),
                    email=row.get("email"),
                    prospect_id=prospect_id,
                    this_run_count=len(response.candidates),
                    total_count=int(row.get("total_resumes_scored") or 0),
                    first_time=False,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "slack_scoring_alert_failed | prospect_id={}", prospect_id
            )


@router.post("/score")
@_limiter.limit("30/hour")
async def score_resumes(
    request: Request,  # required by slowapi.limit
    job_description: Annotated[str, Form(min_length=_MIN_JD_CHARS, max_length=_MAX_JD_CHARS)],
    session_id: Annotated[str, Form(min_length=1)],
    resumes: Annotated[list[UploadFile], File()],
    prospect_id: Annotated[str | None, Form()] = None,
    stream: Annotated[bool, Query(description="false = JSON, true (default) = SSE")] = True,
):
    job_description = clean_text(job_description, max_length=_MAX_JD_CHARS)
    _validate_jd(job_description)
    files = await _read_uploads(resumes)

    ip = client_ip(request)
    user_agent = request.headers.get("user-agent")
    await enforce_daily_resume_cap(ip, len(files))

    settings = get_settings()
    file_hashes = [hash_bytes(f["content"]) for f in files]
    cache_key = hash_score_key(
        jd_text=job_description,
        file_hashes=file_hashes,
        model_parser=settings.openai_model_parser,
        model_scorer=settings.openai_model_scorer,
    )

    # Full-result cache check first
    cached = await get_cached_score_response(cache_key)
    if cached is not None:
        logger.info("score_cache_hit | session_id={}", session_id)
        cached["session_id"] = session_id  # echo client's session_id
        cached.setdefault("metadata", {})["cache_hit"] = True
        # Re-resolve lead_registered live — the cached payload may have been
        # written before the prospect registered.
        cached["lead_registered"] = await _is_lead_registered(prospect_id)
        if stream:
            async def _cached_stream() -> AsyncIterator[dict[str, str]]:
                yield {"event": "result", "data": json.dumps(cached)}

            return EventSourceResponse(
                _cached_stream(), headers=_SSE_HEADERS, ping=5
            )
        return JSONResponse(content=cached)

    if not stream:
        try:
            response = await _run_graph(job_description, files, session_id)
        except asyncio.TimeoutError:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Scoring timed out (90s).")
        except Exception as e:  # noqa: BLE001
            logger.exception("scoring_failed_json | session_id={}", session_id)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Scoring failed: {e!s}")
        await set_cached_score_response(cache_key, response.model_dump())
        await record_cost_and_maybe_alert(response.metadata.total_cost_usd)
        await _persist_after_scoring(
            session_id=session_id,
            prospect_id=prospect_id,
            response=response,
            ip=ip,
            user_agent=user_agent,
        )
        # Resolve *after* persist so increment_tool_use bumps land first.
        response.lead_registered = await _is_lead_registered(prospect_id)
        return JSONResponse(content=response.model_dump())

    return EventSourceResponse(
        _stream_graph(
            job_description,
            files,
            session_id,
            cache_key,
            prospect_id=prospect_id,
            ip=ip,
            user_agent=user_agent,
        ),
        headers=_SSE_HEADERS,
        ping=5,  # keepalive every 5s — covers long LlamaParse pauses
    )
