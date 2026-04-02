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
import time
from typing import Optional

import requests
from dotenv import load_dotenv

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
            return response.json()["choices"][0]["message"]["content"]

        except Exception as e:
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
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=60,
        )
        return response.choices[0].message.content
    except Exception as e:
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
    if provider == "openai":
        return _call_openai(
            prompt,
            model=model or OPENAI_DEFAULT_MODEL,
            max_tokens=max_tokens,
        )
    elif provider == "openrouter":
        return _call_openrouter(
            prompt,
            model=model,
            max_tokens=max_tokens,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'openrouter' or 'openai'.")


# ── Embedding entry point ─────────────────────────────────────────────────────

def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """
    Get text embedding using OpenAI.
    Returns 1536-dim vector for text-embedding-3-small.
    Always uses OpenAI — no OpenRouter alternative for embeddings.
    """
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
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return [0.0] * 1536
