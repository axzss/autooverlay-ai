"""LLM provider helper with primary + fallback support.

Reads configuration from environment:
- Primary:  AI_ROUTER_BASE_URL, AI_ROUTER_API_KEY, AI_ROUTER_MODEL
- Fallback: LLM_FALLBACK_BASE_URL, LLM_FALLBACK_API_KEY, LLM_FALLBACK_MODEL

Behavior:
- Try primary provider first.
- If the request fails or returns model_not_found, try fallback.
- Return the first successful chat completion text.
- Raise on total failure so callers can handle it explicitly.
"""

from __future__ import annotations

import os
from typing import List, Sequence

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam


def _env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip()


def _client(base_url: str | None, api_key: str | None) -> OpenAI | None:
    if not base_url or not api_key:
        return None
    return OpenAI(base_url=base_url, api_key=api_key)


def _try_complete(
    client: OpenAI,
    *,
    model: str,
    messages: Sequence[ChatCompletionMessageParam],
) -> str | None:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=list(messages),
        )
        if resp.choices and resp.choices[0].message.content:
            return resp.choices[0].message.content
    except Exception as exc:
        msg = str(exc).lower()
        if "404" in msg or "model_not_found" in msg or "not supported" in msg:
            return None
        if "timeout" in msg or "5xx" in msg or "internal" in msg or "502" in msg or "503" in msg:
            return None
        return None
    return None


def chat_completion(
    messages: Sequence[ChatCompletionMessageParam],
) -> str:
    """Return assistant text from the first successful provider."""

    primary = {
        "base_url": _env("AI_ROUTER_BASE_URL"),
        "api_key": _env("AI_ROUTER_API_KEY"),
        "model": _env("AI_ROUTER_MODEL"),
    }
    fallback = {
        "base_url": _env("LLM_FALLBACK_BASE_URL"),
        "api_key": _env("LLM_FALLBACK_API_KEY"),
        "model": _env("LLM_FALLBACK_MODEL"),
    }

    candidates: List[dict[str, str | None]] = []
    if primary["base_url"] and primary["api_key"] and primary["model"]:
        candidates.append(primary)
    if fallback["base_url"] and fallback["api_key"] and fallback["model"]:
        candidates.append(fallback)

    last_error: str | None = None
    for candidate in candidates:
        client = _client(candidate["base_url"], candidate["api_key"])
        if client is None:
            continue
        text = _try_complete(
            client,
            model=candidate["model"],
            messages=messages,
        )
        if text is not None:
            return text

    raise RuntimeError(last_error or "LLM providers exhausted without success")
