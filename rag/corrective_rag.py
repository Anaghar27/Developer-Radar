import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from dotenv import load_dotenv

from llm_client import active_provider, call_llm
from rag.hybrid_retriever import retrieve
from rag.llm_tracker import LLMTracker
from rag.reranker import rerank

load_dotenv()
logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.7   # retry if avg relevance score below this
MIN_POST_SCORE = 0.3        # drop posts below this score before insight generation
INITIAL_LIMIT = 20          # posts to retrieve on first attempt
WIDE_LIMIT = 40             # posts to retrieve on retry
GRADING_BATCH_SIZE = 4      # posts per LLM grading call
GRADING_MAX_WORKERS = 2    # max concurrent grading calls (respects free-tier RPM)


# ── Batch relevance grader (LLM quality, 1 call per 4 posts) ─────────────────

def _grade_batch(query: str, batch: list[dict], tracker: LLMTracker) -> list[float]:
    """
    Score one batch of up to GRADING_BATCH_SIZE posts in a single LLM call.
    Returns a list of float scores (0.0–1.0) in the same order as batch.
    Falls back to 0.5 for any post that cannot be parsed.
    """
    numbered = "\n\n".join(
        f"[{i+1}] Title: {p.get('title', '')}\n"
        f"Body: {p.get('body', '')[:300]}"
        for i, p in enumerate(batch)
    )
    prompt = (
        f"Rate how relevant each post is to the query on a scale of 0.0 to 1.0.\n"
        f"Query: {query}\n\n"
        f"{numbered}\n\n"
        f"Respond with ONLY a JSON array of {len(batch)} scores in order, e.g. [0.9, 0.2, 0.8, 0.4].\n"
        f"1.0 = highly relevant, 0.0 = completely irrelevant."
    )

    try:
        t0 = time.perf_counter()
        content = call_llm(prompt, max_tokens=80, temperature=0.0)
        latency_ms = (time.perf_counter() - t0) * 1000

        tracker.record(
            operation="grade_relevance_batch",
            model=active_provider(),
            usage={},
            latency_ms=latency_ms,
        )

        clean = content.strip().replace("```json", "").replace("```", "")
        scores = json.loads(clean)

        if not isinstance(scores, list):
            raise ValueError(f"Expected list, got {type(scores)}")

        # Pad or trim to match batch size, clamp to [0, 1]
        scores = [max(0.0, min(1.0, float(s))) for s in scores]
        if len(scores) < len(batch):
            scores += [0.5] * (len(batch) - len(scores))
        return scores[:len(batch)]

    except Exception as e:
        logger.warning("Batch grading failed: %s — using neutral scores", e)
        tracker.record(
            operation="grade_relevance_batch",
            model=active_provider(),
            usage={},
            latency_ms=(time.perf_counter() - t0) * 1000,
            post_id=f"batch_failed (posts {len(batch)})",
        )
        return [0.5] * len(batch)


def grade_relevance(
    query: str,
    posts: list[dict],
    tracker: LLMTracker,
) -> tuple[float, list[dict]]:
    """
    Score all retrieved posts for relevance using batched LLM calls run in parallel.
    GRADING_BATCH_SIZE posts per call, all batches fired concurrently →
    wall-clock time = single batch latency instead of N × batch latency.
    Returns (avg_score, graded_posts).
    """
    if not posts:
        return 0.0, []

    batches = [
        (i, posts[i : i + GRADING_BATCH_SIZE])
        for i in range(0, len(posts), GRADING_BATCH_SIZE)
    ]
    total_batches = len(batches)
    # scores_by_batch preserves original post ordering
    scores_by_batch: dict[int, list[float]] = {}

    with ThreadPoolExecutor(max_workers=GRADING_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_grade_batch, query, batch, tracker): idx
            for idx, batch in batches
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            batch_scores = future.result()
            scores_by_batch[idx] = batch_scores
            batch_num = idx // GRADING_BATCH_SIZE + 1
            logger.info(
                "Grading batch %d/%d done: posts %d–%d, scores=%s",
                batch_num, total_batches,
                idx + 1, idx + len(batches[batch_num - 1][1]),
                [f"{s:.2f}" for s in batch_scores],
            )

    # Apply scores back to posts in original order
    all_scores = []
    for idx, batch in batches:
        for post, score in zip(batch, scores_by_batch[idx]):
            post["relevance_score"] = score
            all_scores.append(score)

    avg_score = sum(all_scores) / len(all_scores)
    logger.info("Relevance grading complete: avg=%.3f over %d posts", avg_score, len(posts))
    return avg_score, posts


# ── Insight generator (1 LLM call) ───────────────────────────────────────────

def generate_insight(query: str, posts: list[dict], tracker: LLMTracker) -> str:
    """
    Generate a grounded insight report from retrieved posts.
    Each claim must be traceable to a source post.
    """
    if not posts:
        return "No relevant posts found to generate an insight report."

    context_parts = []
    for i, post in enumerate(posts, 1):
        context_parts.append(
            f"[{i}] Source: {post.get('source', 'unknown')} | "
            f"Sentiment: {post.get('sentiment', 'unknown')} | "
            f"Topic: {post.get('topic', 'unknown')}\n"
            f"Title: {post.get('title', '')}\n"
            f"Body: {post.get('body', '')[:400]}"
        )

    context = "\n\n".join(context_parts)

    prompt = f"""You are a developer sentiment analyst. Based on the posts below, \
write a concise insight report answering the query. \
Cite sources using [1], [2], etc. notation.
Be factual and grounded — only state what the posts actually say.

Query: {query}

Posts:
{context}

Write a 3-5 paragraph insight report:"""

    try:
        t0 = time.perf_counter()
        content = call_llm(prompt, max_tokens=2500, temperature=0.0)
        latency_ms = (time.perf_counter() - t0) * 1000
        tracker.record(
            operation="generate_insight",
            model=active_provider(),
            usage={},
            latency_ms=latency_ms,
        )
        return content
    except Exception as e:
        logger.error(f"Insight generation failed: {e}")
        tracker.record(
            operation="generate_insight",
            model=active_provider(),
            usage={},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
        return f"Insight generation failed: {str(e)}"


# ── Main RAG pipeline ─────────────────────────────────────────────────────────

def run_corrective_rag(query: str, limit: int = 10) -> dict:
    """
    Corrective RAG pipeline — 6–16 LLM calls per query (vs 21–61 original):
    1. Hybrid retrieval (pgvector + FTS)
    2. Batched LLM relevance grading — 4 posts per call (5 calls for 20 posts)
    3. Retry with wider search if avg score < threshold (up to 10 more calls)
    4. Filter low-scoring posts
    5. Cross-encoder reranking (local, no API calls)
    6. Insight generation via OpenRouter (1 API call)

    Returns dict with report, sources_used, generated_at.
    """
    query_hash = make_query_hash(query)
    tracker = LLMTracker(query=query, query_hash=query_hash)

    logger.info(f"Corrective RAG pipeline started for: '{query[:80]}'")

    # Step 1 — Initial retrieval
    posts = retrieve(query, limit=INITIAL_LIMIT)

    # Step 2 — Batched LLM relevance grading (4 posts per call)
    avg_score, graded_posts = grade_relevance(query, posts, tracker)

    # Step 3 — Retry with wider search if below threshold
    if avg_score < RELEVANCE_THRESHOLD:
        logger.info(
            f"Avg relevance {avg_score:.3f} below threshold {RELEVANCE_THRESHOLD} "
            f"— retrying with wider search (limit={WIDE_LIMIT})"
        )
        posts = retrieve(query, limit=WIDE_LIMIT)
        avg_score, graded_posts = grade_relevance(query, posts, tracker)
        logger.info(f"Retry avg relevance: {avg_score:.3f}")

    # Step 4 — Filter low-relevance posts
    relevant_posts = [p for p in graded_posts if p.get("relevance_score", 0) >= MIN_POST_SCORE]
    if not relevant_posts:
        relevant_posts = graded_posts[:limit]

    # Step 5 — Rerank
    reranked = rerank(query, relevant_posts, top_k=limit)

    # Step 6 — Generate insight (only LLM call)
    report = generate_insight(query, reranked, tracker)

    # Step 7 — Log and save LLM usage
    tracker.log_summary()
    tracker.save()

    # Step 8 — Collect source URLs
    sources_used = [
        p.get("url", "") or f"post:{p.get('post_id', '')}"
        for p in reranked
        if p.get("url") or p.get("post_id")
    ]

    return {
        "query": query,
        "report": report,
        "sources_used": sources_used,
        "generated_at": datetime.now(timezone.utc),
        "avg_relevance": avg_score,
        "posts_retrieved": len(reranked),
    }


# ── Query hash for Redis caching ──────────────────────────────────────────────

def make_query_hash(query: str) -> str:
    """Generate a stable cache key hash from query string."""
    return hashlib.md5(query.strip().lower().encode()).hexdigest()
