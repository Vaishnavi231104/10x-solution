"""Single entry point for every LLM call (concept: LLM integration).

Why one module: each call goes through the same place, so every call is
(1) wrapped in error handling, (2) validated by its caller, and (3) written to
the `llm_usage` table as a cost log. Prompts and API keys are never logged.
"""
import json
import logging
import os
import time
from typing import Optional

from groq import Groq

import models
from database import SessionLocal

log = logging.getLogger("auraflow.llm")

_client: Optional[Groq] = None

# Groq retires models over time, so the name is configuration, not code.
DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


class LLMError(Exception):
    """Raised when the model call fails. Callers decide on a fallback."""


def _get_client() -> Groq:
    # Created lazily so importing the app (and running tests) never needs a key.
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY", "")
        if not key:
            raise LLMError("GROQ_API_KEY is not set")
        _client = Groq(api_key=key)
    return _client


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Free tier costs $0. Set these env vars to estimate spend on a paid plan."""
    price_in = float(os.getenv("LLM_PRICE_IN_PER_1M", "0"))
    price_out = float(os.getenv("LLM_PRICE_OUT_PER_1M", "0"))
    return round((prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000, 6)


def _log_usage(*, user_id, purpose, model, prompt_tokens, completion_tokens, latency_ms, success, error=None):
    # Logging must never break the request it is measuring.
    try:
        db = SessionLocal()
        try:
            db.add(
                models.LlmUsage(
                    user_id=user_id,
                    purpose=purpose,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=_estimate_cost(prompt_tokens, completion_tokens),
                    latency_ms=latency_ms,
                    success=success,
                    error=(error or None) and error[:200],
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("could not write llm_usage row: %s", exc)


def chat(*, purpose: str, model: str, prompt: str, user_id: Optional[int] = None, temperature: float = 0.2) -> str:
    """Send one prompt, return the reply text, and record tokens/latency/cost."""
    started = time.perf_counter()
    try:
        resp = _get_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        _log_usage(
            user_id=user_id,
            purpose=purpose,
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=int((time.perf_counter() - started) * 1000),
            success=True,
        )
        return text
    except Exception as exc:
        _log_usage(
            user_id=user_id,
            purpose=purpose,
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=int((time.perf_counter() - started) * 1000),
            success=False,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise LLMError(str(exc)) from exc


def parse_json_reply(text: str):
    """Models sometimes wrap JSON in ``` fences. Strip them, then parse."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0].strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return json.loads(cleaned)
