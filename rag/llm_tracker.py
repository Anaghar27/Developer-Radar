"""
LLM call tracker for the Corrective RAG pipeline.

Tracks every OpenRouter call with:
  - operation name (grade_relevance, generate_insight)
  - model used
  - input / output / total tokens
  - latency

At the end of a pipeline run, call .summary() to get per-model and
per-operation breakdowns, and .save() to persist the full log to
logs/llm/<timestamp>_<query_hash>.json.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "logs" / "llm"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class LLMCall:
    operation: str          # grade_relevance | generate_insight
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    post_id: Optional[str] = None   # set for per-post grading calls


class LLMTracker:
    """
    Accumulates LLM call stats for one pipeline run.
    Thread-safe for sequential use within a single run.
    """

    def __init__(self, query: str, query_hash: str):
        self.query = query
        self.query_hash = query_hash
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.calls: list[LLMCall] = []

    # ── Recording ─────────────────────────────────────────────────────────────

    def record(
        self,
        operation: str,
        model: str,
        usage: dict,
        latency_ms: float,
        post_id: Optional[str] = None,
    ) -> None:
        """
        Record one LLM call.

        usage dict expected keys: prompt_tokens, completion_tokens, total_tokens
        (standard OpenRouter / OpenAI usage block).
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        call = LLMCall(
            operation=operation,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=round(latency_ms, 1),
            post_id=post_id,
        )
        self.calls.append(call)

        logger.info(
            "[LLM] op=%-20s model=%-45s  in=%5d  out=%5d  total=%6d  latency=%6.0fms%s",
            operation,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            latency_ms,
            f"  post_id={post_id}" if post_id else "",
        )

    # ── Aggregation ───────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return per-model and per-operation breakdowns plus grand totals."""
        by_model: dict[str, dict] = {}
        by_operation: dict[str, dict] = {}

        for c in self.calls:
            # per model
            m = by_model.setdefault(c.model, {
                "calls": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "total_tokens": 0, "total_latency_ms": 0.0,
            })
            m["calls"] += 1
            m["prompt_tokens"] += c.prompt_tokens
            m["completion_tokens"] += c.completion_tokens
            m["total_tokens"] += c.total_tokens
            m["total_latency_ms"] += c.latency_ms

            # per operation
            op = by_operation.setdefault(c.operation, {
                "calls": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "total_tokens": 0, "total_latency_ms": 0.0,
            })
            op["calls"] += 1
            op["prompt_tokens"] += c.prompt_tokens
            op["completion_tokens"] += c.completion_tokens
            op["total_tokens"] += c.total_tokens
            op["total_latency_ms"] += c.latency_ms

        total_calls = len(self.calls)
        total_prompt = sum(c.prompt_tokens for c in self.calls)
        total_completion = sum(c.completion_tokens for c in self.calls)
        total_tokens = sum(c.total_tokens for c in self.calls)
        total_latency = sum(c.latency_ms for c in self.calls)

        return {
            "query": self.query,
            "query_hash": self.query_hash,
            "started_at": self.started_at,
            "totals": {
                "calls": total_calls,
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "total_tokens": total_tokens,
                "total_latency_ms": round(total_latency, 1),
            },
            "by_model": by_model,
            "by_operation": by_operation,
            "calls": [asdict(c) for c in self.calls],
        }

    def log_summary(self) -> None:
        """Print a human-readable summary to the Python logger."""
        s = self.summary()
        t = s["totals"]
        sep = "─" * 70

        logger.info(sep)
        logger.info("[LLM SUMMARY] query='%s'", self.query[:80])
        logger.info(
            "[LLM SUMMARY] TOTALS  calls=%d  in=%d  out=%d  total=%d  latency=%.0fms",
            t["calls"], t["prompt_tokens"], t["completion_tokens"],
            t["total_tokens"], t["total_latency_ms"],
        )

        logger.info("[LLM SUMMARY] ── Per Model ──")
        for model, stats in s["by_model"].items():
            logger.info(
                "  %-45s  calls=%2d  in=%6d  out=%6d  total=%7d  latency=%7.0fms",
                model,
                stats["calls"], stats["prompt_tokens"],
                stats["completion_tokens"], stats["total_tokens"],
                stats["total_latency_ms"],
            )

        logger.info("[LLM SUMMARY] ── Per Operation ──")
        for op, stats in s["by_operation"].items():
            logger.info(
                "  %-20s  calls=%2d  in=%6d  out=%6d  total=%7d  latency=%7.0fms",
                op,
                stats["calls"], stats["prompt_tokens"],
                stats["completion_tokens"], stats["total_tokens"],
                stats["total_latency_ms"],
            )

        logger.info(sep)

    def save(self) -> Path:
        """Persist full log JSON to logs/llm/<timestamp>_<query_hash>.json."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = LOGS_DIR / f"{ts}_{self.query_hash[:8]}.json"
        with open(filename, "w") as f:
            json.dump(self.summary(), f, indent=2, default=str)
        logger.info("[LLM TRACKER] Log saved → %s", filename)
        return filename
