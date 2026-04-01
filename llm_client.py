"""
Unified LLM client — routes to OpenAI or OpenRouter based on provider config.

Usage:
    from llm_client import call_llm

    # Uses LLM_PROVIDER env var (default: openai)
    response = call_llm(prompt, max_tokens=512)

    # Force a specific provider regardless of LLM_PROVIDER
    response = call_llm(prompt, max_tokens=512, provider="openrouter")

Environment variables:
    LLM_PROVIDER              "openai" (default) | "openrouter"
    CLASSIFICATION_PROVIDER   "openrouter" (default) | "openai"
    OPENAI_RPM                requests-per-minute cap (default: 60)
    OPENROUTER_RPM            requests-per-minute cap (default: 10)

    OpenAI:
        OPENAI_API_KEY    your OpenAI API key
        OPENAI_MODEL      model ID, e.g. gpt-4o-mini (default)

    OpenRouter:
        OPENROUTER_API_KEY   your OpenRouter API key
        OPENROUTER_MODEL     model ID, e.g. arcee-ai/trinity-large-preview:free
"""

import logging
import os
import random
import threading
import time
from collections import deque

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Provider config ───────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── Retry config ──────────────────────────────────────────────────────────────

_RETRY_DELAYS = [5, 10, 20]
_RATE_LIMIT_DELAYS = [30, 60, 90]
_MAX_ATTEMPTS = 4


def _backoff(attempt: int, is_rate_limit: bool) -> float:
    delays = _RATE_LIMIT_DELAYS if is_rate_limit else _RETRY_DELAYS
    base = delays[min(attempt, len(delays) - 1)]
    return base * random.uniform(0.8, 1.2)


# ── Content error detection ───────────────────────────────────────────────────

_CONTENT_ERROR_PHRASES = [
    "rate limit exceeded",
    "rate_limit_exceeded",
    "quota exceeded",
    "too many requests",
    "model is currently overloaded",
    "context length exceeded",
    "invalid api key",
]


def _assert_valid_content(content: str) -> None:
    """Raise ValueError if content looks like a provider error message."""
    lower = content.lower().strip()
    for phrase in _CONTENT_ERROR_PHRASES:
        if phrase in lower:
            raise ValueError(f"Provider returned error in content: {content[:200]}")


# ── Per-provider rate limiters ────────────────────────────────────────────────

class _RateLimiter:
    """
    Sliding-window rate limiter. Tracks timestamps of recent calls and blocks
    before sending if the per-minute cap would be exceeded.
    Thread-safe for concurrent grading calls.
    """

    def __init__(self, max_calls_per_minute: int):
        self.max_calls = max_calls_per_minute
        self.window = 60.0
        self._calls: deque = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.window:
                    self._calls.popleft()
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                wait = self.window - (now - self._calls[0])
            jitter = random.uniform(0, 0.5)
            logger.info(
                "Rate limiter: %d/%d calls used in last 60s — waiting %.1fs",
                len(self._calls), self.max_calls, wait + jitter,
            )
            time.sleep(wait + jitter)


_openai_limiter = _RateLimiter(max_calls_per_minute=int(os.getenv("OPENAI_RPM", "60")))
_openrouter_limiter = _RateLimiter(max_calls_per_minute=int(os.getenv("OPENROUTER_RPM", "10")))


# ── Provider implementations ──────────────────────────────────────────────────

def _call_openai(prompt: str, max_tokens: int, temperature: float) -> str:
    _openai_limiter.acquire()
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
            if response.status_code == 429:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise requests.exceptions.HTTPError(
                        f"429 Rate limited after {_MAX_ATTEMPTS} attempts", response=response
                    )
                wait = _backoff(attempt, is_rate_limit=True)
                logger.warning("OpenAI 429 (attempt %d/%d) — waiting %.0fs", attempt + 1, _MAX_ATTEMPTS, wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("Empty response content")
            _assert_valid_content(content)
            logger.debug("OpenAI OK: model=%s tokens=%s", OPENAI_MODEL, data.get("usage", {}).get("total_tokens"))
            return content
        except (KeyError, ValueError) as e:
            if attempt == _MAX_ATTEMPTS - 1:
                raise requests.exceptions.RequestException(f"Malformed response after {_MAX_ATTEMPTS} attempts: {e}")
            wait = _backoff(attempt, is_rate_limit=False)
            logger.warning("Malformed OpenAI response (attempt %d/%d) — retrying in %.0fs: %s", attempt + 1, _MAX_ATTEMPTS, wait, e)
            time.sleep(wait)
        except requests.RequestException as e:
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            wait = _backoff(attempt, is_rate_limit=False)
            logger.warning("OpenAI request failed (attempt %d/%d) — retrying in %.0fs: %s", attempt + 1, _MAX_ATTEMPTS, wait, e)
            time.sleep(wait)
    raise RuntimeError("OpenAI request failed after retries")


def _call_openrouter(prompt: str, max_tokens: int, temperature: float) -> str:
    _openrouter_limiter.acquire()
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
            if response.status_code == 429:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise requests.exceptions.HTTPError(
                        f"429 Rate limited after {_MAX_ATTEMPTS} attempts", response=response
                    )
                wait = _backoff(attempt, is_rate_limit=True)
                logger.warning("OpenRouter 429 (attempt %d/%d) — waiting %.0fs", attempt + 1, _MAX_ATTEMPTS, wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("Empty response content")
            _assert_valid_content(content)
            logger.debug("OpenRouter OK: model=%s tokens=%s", OPENROUTER_MODEL, data.get("usage", {}).get("total_tokens"))
            return content
        except (KeyError, ValueError) as e:
            if attempt == _MAX_ATTEMPTS - 1:
                raise requests.exceptions.RequestException(f"Malformed response after {_MAX_ATTEMPTS} attempts: {e}")
            wait = _backoff(attempt, is_rate_limit=False)
            logger.warning("Malformed OpenRouter response (attempt %d/%d) — retrying in %.0fs: %s", attempt + 1, _MAX_ATTEMPTS, wait, e)
            time.sleep(wait)
        except requests.RequestException as e:
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            wait = _backoff(attempt, is_rate_limit=False)
            logger.warning("OpenRouter request failed (attempt %d/%d) — retrying in %.0fs: %s", attempt + 1, _MAX_ATTEMPTS, wait, e)
            time.sleep(wait)
    raise RuntimeError("OpenRouter request failed after retries")


# ── Public interface ──────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
    provider: str | None = None,
) -> str:
    """
    Call an LLM provider and return the response text.

    provider: override which provider to use for this call.
              If None, reads LLM_PROVIDER env var (default: "openai").
              Pass "openrouter" explicitly to force OpenRouter.
    """
    resolved = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()

    if resolved == "openai":
        logger.info("LLM call → OpenAI (%s)", OPENAI_MODEL)
        return _call_openai(prompt, max_tokens, temperature)

    logger.info("LLM call → OpenRouter (%s)", OPENROUTER_MODEL)
    return _call_openrouter(prompt, max_tokens, temperature)


def active_provider(provider: str | None = None) -> str:
    """Return the provider+model string for the given or configured provider."""
    resolved = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    if resolved == "openai":
        return f"openai/{OPENAI_MODEL}"
    return f"openrouter/{OPENROUTER_MODEL}"
