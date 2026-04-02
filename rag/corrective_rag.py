import hashlib
import json
import logging
from datetime import UTC, datetime

from dotenv import load_dotenv

from processing.llm_client import call_llm
from rag.hybrid_retriever import retrieve
from rag.llm_tracker import LLMTracker
from rag.reranker import rerank

load_dotenv()
logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.7   # retry if avg relevance score below this
MIN_POST_SCORE = 0.3        # drop posts below this score before insight generation
INITIAL_LIMIT = 20          # posts to retrieve on first attempt
WIDE_LIMIT = 40             # posts to retrieve on retry

# ── Relevance grader (1 OpenAI call per post) ────────────────────────────────

def grade_relevance(query: str, posts: list[dict]) -> tuple[float, list[dict]]:
    """
    Score each retrieved post for relevance to the query (0.0 to 1.0).
    Uses OpenAI gpt-4o-mini for fast, reliable relevance grading.
    """
    if not posts:
        return 0.0, []

    graded = []
    scores = []

    for post in posts:
        prompt = f"""Rate how relevant this post is to the query on a scale of 0.0 to 1.0.
Query: {query}
Post title: {post.get('title', '')}
Post body: {post.get('body', '')[:300]}

Respond with ONLY a JSON object: {{"score": 0.0}}
Score 1.0 = highly relevant, 0.0 = completely irrelevant."""

        try:
            content = call_llm(
                prompt,
                provider="openai",
                model="gpt-4o-mini",
                max_tokens=20,
            )
            clean = content.strip().replace("```json", "").replace("```", "")
            score = float(json.loads(clean)["score"])
            score = max(0.0, min(1.0, score))
        except Exception as e:
            logger.warning(f"Relevance grading failed for post {post.get('post_id')}: {e}")
            score = 0.5

        post["relevance_score"] = score
        scores.append(score)
        graded.append(post)

    avg_score = sum(scores) / len(scores) if scores else 0.0
    logger.info(f"Relevance grading: avg={avg_score:.3f} over {len(graded)} posts")
    return avg_score, graded


# ── Insight generator (1 OpenAI call) ────────────────────────────────────────

def generate_insight(query: str, posts: list[dict]) -> str:
    """
    Generate a grounded insight report using OpenAI gpt-4o-mini.
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

    prompt = f"""You are a developer sentiment analyst. Based on the posts below,
write a concise insight report answering the query.
Cite sources using [1], [2], etc. notation.
Be factual and grounded — only state what the posts actually say.

Query: {query}

Posts:
{context}

Write a 3-5 paragraph insight report:"""

    try:
        return call_llm(
            prompt,
            provider="openai",
            model="gpt-4o-mini",
            max_tokens=800,
        )
    except Exception as e:
        logger.error(f"Insight generation failed: {e}")
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

    # Step 2 — LLM relevance grading (1 call per post via OpenAI)
    avg_score, graded_posts = grade_relevance(query, posts)

    # Step 3 — Retry with wider search if below threshold
    if avg_score < RELEVANCE_THRESHOLD:
        logger.info(
            f"Avg relevance {avg_score:.3f} below threshold {RELEVANCE_THRESHOLD} "
            f"— retrying with wider search (limit={WIDE_LIMIT})"
        )
        posts = retrieve(query, limit=WIDE_LIMIT)
        avg_score, graded_posts = grade_relevance(query, posts)
        logger.info(f"Retry avg relevance: {avg_score:.3f}")

    # Step 4 — Filter low-relevance posts
    relevant_posts = [p for p in graded_posts if p.get("relevance_score", 0) >= MIN_POST_SCORE]
    if not relevant_posts:
        relevant_posts = graded_posts[:limit]

    # Step 5 — Rerank
    reranked = rerank(query, relevant_posts, top_k=limit)

    # Step 6 — Generate insight (1 OpenAI call)
    report = generate_insight(query, reranked)

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
        "generated_at": datetime.now(UTC),
        "avg_relevance": avg_score,
        "posts_retrieved": len(reranked),
    }


# ── Query hash for Redis caching ──────────────────────────────────────────────

def make_query_hash(query: str) -> str:
    """Generate a stable cache key hash from query string."""
    return hashlib.md5(query.strip().lower().encode()).hexdigest()
