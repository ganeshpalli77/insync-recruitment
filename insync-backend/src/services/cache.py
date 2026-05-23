"""Redis JSON cache with content-hash keys.

Key strategy (per the approved plan):
- Per-file LlamaParse output:  cache:parse-file:{sha256(file_bytes)}        TTL 24h
- Per-JD parsed JSON:           cache:parse-jd:{sha256(normalized_text)}     TTL 24h
- Full /api/score result:       cache:score:{sha256(jd + sorted_file_hashes + models)} TTL 1h
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import redis.asyncio as redis
from loguru import logger

from src.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            get_settings().redis_url, encoding="utf-8", decode_responses=True
        )
    return _client


# Hashing helpers ----------------------------------------------------------


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_WHITESPACE = re.compile(r"\s+")


def _normalize_jd(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


def hash_jd(text: str) -> str:
    return hashlib.sha256(_normalize_jd(text).encode("utf-8")).hexdigest()


def hash_score_key(*, jd_text: str, file_hashes: list[str], model_parser: str, model_scorer: str) -> str:
    # Late import keeps the cache module free of LangGraph/LLM deps.
    from src.core.llm.prompts import PROMPT_VERSION

    payload = json.dumps(
        {
            "jd": _normalize_jd(jd_text),
            "files": sorted(file_hashes),
            "parser": model_parser,
            "scorer": model_scorer,
            "prompt_version": PROMPT_VERSION,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Generic JSON get/set ----------------------------------------------------


async def get_json(key: str) -> Any | None:
    try:
        raw = await get_redis().get(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("redis_get_failed | key={} err={}", key, e)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("redis_json_decode_failed | key={}", key)
        return None


async def set_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception as e:  # noqa: BLE001
        logger.warning("redis_set_failed | key={} err={}", key, e)


# Typed accessors ---------------------------------------------------------


async def get_cached_parsed_jd(text: str) -> dict | None:
    return await get_json(f"cache:parse-jd:{hash_jd(text)}")


async def set_cached_parsed_jd(text: str, value: dict) -> None:
    await set_json(
        f"cache:parse-jd:{hash_jd(text)}",
        value,
        ttl_seconds=get_settings().cache_ttl_jd_parse,
    )


async def get_cached_parsed_file(file_hash: str) -> str | None:
    return await get_json(f"cache:parse-file:{file_hash}")


async def set_cached_parsed_file(file_hash: str, text: str) -> None:
    await set_json(
        f"cache:parse-file:{file_hash}",
        text,
        ttl_seconds=get_settings().cache_ttl_file_parse,
    )


async def get_cached_score_response(key: str) -> dict | None:
    return await get_json(f"cache:score:{key}")


async def set_cached_score_response(key: str, value: dict) -> None:
    await set_json(
        f"cache:score:{key}",
        value,
        ttl_seconds=get_settings().cache_ttl_result,
    )
