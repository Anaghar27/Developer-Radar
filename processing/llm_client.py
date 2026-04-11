"""
Unified LLM client for DevPulse.

Routes LLM calls through either OpenRouter or OpenAI depending on
the provider argument. This gives a single call interface across
classification (OpenRouter), RAG grading, and insight generation (OpenAI).

Usage:
    from processing.llm_client import call_llm

    # Use OpenRouter (default — free tier)
    response = call_llm(prompt, provider="openrouter")

    # Use OpenAI (RAG, higher quality)
    response = call_llm(prompt, provider="openai", model="gpt-4o-mini")
"""

import logging
import os
import threading
import time

import requests
from dotenv import load_dotenv

from rag.llm_tracker import LLMCall, estimate_cost, estimate_tokens, record_call

load_dotenv()
logger = logging.getLogger(__name__)

# ── OpenRouter config ─────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [
    os.getenv("OPENROUTER_MODEL", "nvidia/llama-3.1-nemotron-ultra-253b-v1:free"),
    "stepfun-ai/step-3-5-flash",
    "nvidia/llama-3.1-nemotron-nano-8b-instruct:free",
]

# ── OpenAI config ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"

# ── Rate limiting ─────────────────────────────────────────────────────────────
_last_openrouter_call = 0.0
OPENROUTER_MIN_DELAY = 1.0  # seconds between OpenRouter calls
_tracking_state = threading.local()


def _reset_tracking_state() -> None:
    _tracking_state.recorded = False


def _mark_tracked() -> None:
    _tracking_state.recorded = True


def _was_tracked() -> bool:
    return getattr(_tracking_state, "recorded", False)


def _safe_record(call: LLMCall) -> None:
    """Best-effort tracker hook that never affects primary LLM behavior."""
    try:
        record_call(call)
        _mark_tracked()
    except Exception:
        logger.exception("LLM tracker failed while recording call")


# ── Core call functions ───────────────────────────────────────────────────────

def _call_openrouter(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 500,
    retries: int = 3,
) -> str:
    """
    Call OpenRouter API with automatic model fallback.
    Tries each model in OPENROUTER_MODELS on failure.
    """
    global _last_openrouter_call

    models_to_try = [model] if model else OPENROUTER_MODELS

    last_error = None
    for attempt, m in enumerate(models_to_try):
        # Rate limiting
        elapsed = time.time() - _last_openrouter_call
        if elapsed < OPENROUTER_MIN_DELAY:
            time.sleep(OPENROUTER_MIN_DELAY - elapsed)

        start = time.time()
        try:
            response = requests.post(
                OPENROUTER_BASE_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/devpulse",
                    "X-Title": "DevPulse",
                },
                json={
                    "model": m,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            _last_openrouter_call = time.time()
            latency = (time.time() - start) * 1000

            # Handle rate limits
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                logger.warning(f"OpenRouter rate limited — waiting {retry_after}s")
                time.sleep(retry_after)
                continue

            # Handle fatal errors
            if response.status_code in (401, 402, 403):
                raise Exception(f"OpenRouter auth/billing error: {response.status_code}")

            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            input_tok = estimate_tokens(prompt)
            output_tok = estimate_tokens(content)
            _safe_record(
                LLMCall(
                    operation="llm_call",
                    provider="openrouter",
                    model=m,
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    latency_ms=latency,
                    success=True,
                    cost_usd=estimate_cost(m, input_tok, output_tok),
                )
            )
            return content

        except Exception as e:
            latency = (time.time() - start) * 1000
            _safe_record(
                LLMCall(
                    operation="llm_call",
                    provider="openrouter",
                    model=m,
                    latency_ms=latency,
                    success=False,
                    error_reason=str(e)[:200],
                )
            )
            last_error = e
            logger.warning(f"OpenRouter attempt {attempt + 1} failed with {m}: {e}")
            continue

    raise Exception(f"All OpenRouter models failed. Last error: {last_error}")


def _call_openai(
    prompt: str,
    model: str = OPENAI_DEFAULT_MODEL,
    max_tokens: int = 500,
) -> str:
    """
    Call OpenAI API directly.
    Used for RAG relevance grading and insight generation.
    """
    start = time.time()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=60,
        )
        content = response.choices[0].message.content
        latency = (time.time() - start) * 1000
        input_tok = estimate_tokens(prompt)
        output_tok = estimate_tokens(content or "")
        _safe_record(
            LLMCall(
                operation="llm_call",
                provider="openai",
                model=model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency,
                success=True,
                cost_usd=estimate_cost(model, input_tok, output_tok),
            )
        )
        return content
    except Exception as e:
        latency = (time.time() - start) * 1000
        _safe_record(
            LLMCall(
                operation="llm_call",
                provider="openai",
                model=model,
                latency_ms=latency,
                success=False,
                error_reason=str(e)[:200],
            )
        )
        logger.error(f"OpenAI call failed: {e}")
        raise


# ── Unified entry point ───────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    provider: str = "openrouter",
    model: str | None = None,
    max_tokens: int = 500,
) -> str:
    """
    Unified LLM call — routes to OpenRouter or OpenAI based on provider.

    Args:
        prompt: The prompt to send
        provider: "openrouter" (default, free) or "openai" (paid, higher quality)
        model: Optional model override. If None, uses provider defaults.
        max_tokens: Maximum tokens in response

    Returns:
        Response text string
    """
    _reset_tracking_state()
    resolved_model = model or OPENAI_DEFAULT_MODEL if provider == "openai" else model or OPENROUTER_MODELS[0]
    start = time.time()
    try:
        if provider == "openai":
            result = _call_openai(
                prompt,
                model=model or OPENAI_DEFAULT_MODEL,
                max_tokens=max_tokens,
            )
        elif provider == "openrouter":
            result = _call_openrouter(
                prompt,
                model=model,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'openrouter' or 'openai'.")
    except Exception as exc:
        if not _was_tracked():
            latency = (time.time() - start) * 1000
            _safe_record(
                LLMCall(
                    operation="llm_call",
                    provider=provider,
                    model=resolved_model,
                    latency_ms=latency,
                    success=False,
                    error_reason=str(exc)[:200],
                )
            )
        raise

    if not _was_tracked():
        latency = (time.time() - start) * 1000
        input_tok = estimate_tokens(prompt)
        output_tok = estimate_tokens(result or "")
        _safe_record(
            LLMCall(
                operation="llm_call",
                provider=provider,
                model=resolved_model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency,
                success=True,
                cost_usd=estimate_cost(resolved_model, input_tok, output_tok),
            )
        )
    return result


# ── Embedding entry point ─────────────────────────────────────────────────────

def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """
    Get text embedding using OpenAI.
    Returns 1536-dim vector for text-embedding-3-small.
    Always uses OpenAI — no OpenRouter alternative for embeddings.
    """
    start = time.time()
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    text = text[:8000] if text else ""
    if not text.strip():
        return [0.0] * 1536
    try:
        response = client.embeddings.create(
            input=text,
            model=model,
        )
        embedding = response.data[0].embedding
        latency = (time.time() - start) * 1000
        input_tok = estimate_tokens(text)
        _safe_record(
            LLMCall(
                operation="embedding",
                provider="openai",
                model=model,
                input_tokens=input_tok,
                output_tokens=0,
                latency_ms=latency,
                success=True,
                cost_usd=estimate_cost(model, input_tok, 0),
            )
        )
        return embedding
    except Exception as e:
        latency = (time.time() - start) * 1000
        _safe_record(
            LLMCall(
                operation="embedding",
                provider="openai",
                model=model,
                latency_ms=latency,
                success=False,
                error_reason=str(e)[:200],
            )
        )
        logger.error(f"Embedding failed: {e}")
        return [0.0] * 1536
