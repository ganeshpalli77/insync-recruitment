"""Async OpenAI wrapper: JSON-mode chat completions, retries, cost + concurrency control."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from loguru import logger
from openai import AsyncOpenAI, APIConnectionError, APIError, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from src.config import get_settings
from src.core.llm.prompts import cost_usd


@dataclass(slots=True)
class LLMCall:
    """Single OpenAI invocation result."""

    parsed: dict[str, Any]
    raw_text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    cost: float


_semaphore: asyncio.Semaphore | None = None
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_request_timeout,
            max_retries=0,  # we own retries via tenacity
        )
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().openai_max_concurrency)
    return _semaphore


async def chat_json(
    *,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.2,
    top_p: float = 0.95,
    max_tokens: int = 1500,
) -> LLMCall:
    """One JSON-mode chat completion with retries, cost tracking, and concurrency control.

    Raises on terminal failure after retry budget exhausted.
    """
    client = _get_client()
    sem = _get_semaphore()

    retrier = AsyncRetrying(
        stop=stop_after_attempt(4),
        wait=wait_random_exponential(min=1, max=20),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, APIError)),
        reraise=True,
    )

    async for attempt in retrier:
        with attempt:
            async with sem:
                response = await client.chat.completions.create(
                    model=model,
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )

    choice = response.choices[0]
    raw_text = choice.message.content or "{}"
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(
            "openai_json_parse_failed | model={} raw={!r}",
            model,
            raw_text[:500],
        )
        raise ValueError(f"OpenAI returned non-JSON despite json_object mode: {e}") from e

    return LLMCall(
        parsed=parsed,
        raw_text=raw_text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model,
        cost=cost_usd(model, prompt_tokens, completion_tokens),
    )
