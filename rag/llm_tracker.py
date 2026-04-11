"""
LLM usage tracker for DevPulse.

Tracks every LLM call across classification, RAG grading,
insight generation, and query expansion.

Persists in memory for cost and quality observability.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "logs" / "llm"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class LLMCall:
    """Represents a single LLM API call."""

    operation: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    success: bool = True
    error_reason: str | None = None
    cost_usd: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    post_id: str | None = None


COST_PER_1M_INPUT = {
    "gpt-4o-mini": 0.15,
    "text-embedding-3-small": 0.02,
    "nvidia/llama-3.1-nemotron-ultra-253b-v1:free": 0.0,
    "stepfun-ai/step-3-5-flash": 0.0,
    "nvidia/llama-3.1-nemotron-nano-8b-instruct:free": 0.0,
}

COST_PER_1M_OUTPUT = {
    "gpt-4o-mini": 0.60,
    "text-embedding-3-small": 0.0,
    "nvidia/llama-3.1-nemotron-ultra-253b-v1:free": 0.0,
    "stepfun-ai/step-3-5-flash": 0.0,
    "nvidia/llama-3.1-nemotron-nano-8b-instruct:free": 0.0,
}

_call_log: list[LLMCall] = []
_total_cost_usd = 0.0
_lock = threading.Lock()


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate call cost in USD from token counts."""
    input_cost = COST_PER_1M_INPUT.get(model, 0.0) * input_tokens / 1_000_000
    output_cost = COST_PER_1M_OUTPUT.get(model, 0.0) * output_tokens / 1_000_000
    return round(input_cost + output_cost, 8)


def estimate_tokens(text: str) -> int:
    """Estimate token count using a simple 4-chars-per-token heuristic."""
    return max(1, len(text) // 4) if text else 0


def record_call(call: LLMCall) -> None:
    """Record one LLM call in memory and log a concise summary."""
    global _total_cost_usd
    with _lock:
        _call_log.append(call)
        _total_cost_usd += call.cost_usd

    status = "OK" if call.success else f"FAILED ({call.error_reason})"
    logger.info(
        "[LLM] %s | %s/%s | %.0fms | in=%s out=%s | $%.6f | %s",
        call.operation,
        call.provider,
        call.model,
        call.latency_ms,
        call.input_tokens,
        call.output_tokens,
        call.cost_usd,
        status,
    )


def get_stats() -> dict:
    """Return aggregated in-memory LLM usage stats."""
    with _lock:
        calls = list(_call_log)
        total_cost_usd = _total_cost_usd

    if not calls:
        return {
            "total_calls": 0,
            "total_cost_usd": 0.0,
            "by_operation": {},
            "by_provider": {},
            "success_rate": 1.0,
            "avg_latency_ms": 0.0,
        }

    by_operation: dict[str, dict] = {}
    by_provider: dict[str, dict] = {}

    for call in calls:
        op = by_operation.setdefault(
            call.operation,
            {"calls": 0, "cost_usd": 0.0, "total_latency_ms": 0.0, "failures": 0},
        )
        op["calls"] += 1
        op["cost_usd"] += call.cost_usd
        op["total_latency_ms"] += call.latency_ms
        if not call.success:
            op["failures"] += 1

        provider = by_provider.setdefault(
            call.provider,
            {"calls": 0, "cost_usd": 0.0, "failures": 0},
        )
        provider["calls"] += 1
        provider["cost_usd"] += call.cost_usd
        if not call.success:
            provider["failures"] += 1

    successful = sum(1 for call in calls if call.success)
    avg_latency = sum(call.latency_ms for call in calls) / len(calls)

    return {
        "total_calls": len(calls),
        "total_cost_usd": round(total_cost_usd, 6),
        "success_rate": round(successful / len(calls), 4),
        "avg_latency_ms": round(avg_latency, 1),
        "by_operation": by_operation,
        "by_provider": by_provider,
    }


def reset_stats() -> None:
    """Clear the in-memory tracker state."""
    global _call_log, _total_cost_usd
    with _lock:
        _call_log = []
        _total_cost_usd = 0.0


class LLMTracker:
    """
    Backward-compatible tracker facade used by Corrective RAG.

    Calls are recorded into the same global in-memory store so per-run
    logging continues to work alongside shared client tracking.
    """

    def __init__(self, query: str, query_hash: str):
        self.query = query
        self.query_hash = query_hash
        self.started_at = datetime.now(UTC).isoformat()

    def record(
        self,
        operation: str,
        model: str,
        usage: dict,
        latency_ms: float,
        post_id: str | None = None,
        provider: str = "openai",
    ) -> None:
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        record_call(
            LLMCall(
                operation=operation,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=round(latency_ms, 1),
                success=True,
                cost_usd=estimate_cost(model, input_tokens, output_tokens),
                post_id=post_id,
            )
        )

    def summary(self) -> dict:
        with _lock:
            calls = [call for call in _call_log if call.timestamp.isoformat() >= self.started_at]

        by_model: dict[str, dict] = {}
        by_operation: dict[str, dict] = {}
        for call in calls:
            model_stats = by_model.setdefault(
                call.model,
                {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "total_latency_ms": 0.0,
                },
            )
            model_stats["calls"] += 1
            model_stats["input_tokens"] += call.input_tokens
            model_stats["output_tokens"] += call.output_tokens
            model_stats["total_tokens"] += call.input_tokens + call.output_tokens
            model_stats["total_latency_ms"] += call.latency_ms

            op_stats = by_operation.setdefault(
                call.operation,
                {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "total_latency_ms": 0.0,
                },
            )
            op_stats["calls"] += 1
            op_stats["input_tokens"] += call.input_tokens
            op_stats["output_tokens"] += call.output_tokens
            op_stats["total_tokens"] += call.input_tokens + call.output_tokens
            op_stats["total_latency_ms"] += call.latency_ms

        return {
            "query": self.query,
            "query_hash": self.query_hash,
            "started_at": self.started_at,
            "totals": {
                "calls": len(calls),
                "input_tokens": sum(call.input_tokens for call in calls),
                "output_tokens": sum(call.output_tokens for call in calls),
                "total_tokens": sum(call.input_tokens + call.output_tokens for call in calls),
                "total_latency_ms": round(sum(call.latency_ms for call in calls), 1),
            },
            "by_model": by_model,
            "by_operation": by_operation,
            "calls": [asdict(call) for call in calls],
        }

    def log_summary(self) -> None:
        summary = self.summary()
        totals = summary["totals"]
        logger.info(
            "[LLM SUMMARY] query='%s' calls=%s in=%s out=%s total=%s latency=%.0fms",
            self.query[:80],
            totals["calls"],
            totals["input_tokens"],
            totals["output_tokens"],
            totals["total_tokens"],
            totals["total_latency_ms"],
        )

    def save(self) -> Path:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        filename = LOGS_DIR / f"{ts}_{self.query_hash[:8]}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.summary(), f, indent=2, default=str)
        logger.info("[LLM TRACKER] Log saved -> %s", filename)
        return filename
