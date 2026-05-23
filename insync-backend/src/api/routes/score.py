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

    if final_state is None or not final_state.get("metadata"):
        yield {
            "event": "error",
            "data": json.dumps({"message": "Scoring produced no final state."}),
        }
        return

    response = build_score_response(final_state)
    await set_cached_score_response(cache_key, response.model_dump())
    await record_cost_and_maybe_alert(response.metadata.total_cost_usd)
    await _persist_after_scoring(
        session_id=session_id,
        prospect_id=prospect_id,
        response=response,
        ip=ip,
        user_agent=user_agent,
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


async def _persist_after_scoring(
    *,
    session_id: str,
    prospect_id: str | None,
    response: ScoreResponse,
    ip: str,
    user_agent: str | None,
) -> None:
    """Fire-and-forget: write the session + candidates + Track B event + CRM."""
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


@router.post("/score")
@_limiter.limit("5/hour")
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
