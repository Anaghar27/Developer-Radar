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
GRADING_BATCH_SIZE = 10     # posts per relevance grading LLM call
                            # sweet spot: quality stays high, 4x fewer calls than grading all 40

# ── Query expansion ───────────────────────────────────────────────────────────

def expand_query(query: str) -> list[str]:
    """
    Expand the original query into multiple semantically related variants.

    Why: A user asking "pytorch performance issues" might miss posts titled
    "slow training in torch" or "model optimization techniques". Query expansion
    generates alternative phrasings to improve retrieval recall.

    Uses a single OpenAI call to generate 3 variants.
    Always includes the original query as the first entry.

    Returns:
        List of 4 queries: [original, variant1, variant2, variant3]
    """
    prompt = f"""Generate 3 alternative search queries for the following question.
The alternatives should capture different phrasings, synonyms, and related concepts
that might appear in developer forum posts and discussions.

Original query: {query}

Respond with ONLY a JSON array of 3 strings.
Example: ["alternative 1", "alternative 2", "alternative 3"]
Do not include the original query in your response.
Return ONLY the JSON array, no other text."""

    try:
        response = call_llm(
            prompt,
            provider="openai",
            model="gpt-4o-mini",
            max_tokens=150,
        )
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        variants = json.loads(clean)

        if not isinstance(variants, list):
            raise ValueError(f"Expected list, got {type(variants)}")

        variants = [v for v in variants if isinstance(v, str)][:3]

        while len(variants) < 3:
            variants.append(query)

        expanded = [query] + variants
        logger.info(f"Query expanded: {len(expanded)} variants for '{query[:60]}'")
        return expanded

    except Exception as e:
        logger.warning(f"Query expansion failed: {e}. Using original query only.")
        return [query]


# ── Relevance grader ──────────────────────────────────────────────────────────

def _grade_batch(query: str, posts: list[dict]) -> list[float]:
    """
    Grade a single mini-batch of posts (up to GRADING_BATCH_SIZE).
    Makes exactly 1 LLM call per batch.
    Returns list of float scores in same order as posts.
    Falls back to 0.5 for all posts if call fails.
    """
    if not posts:
        return []

    post_summaries = []
    for i, post in enumerate(posts):
        post_summaries.append(
            f"[{i}] Title: {post.get('title', '')[:150]}\n"
            f"    Body: {post.get('body', '')[:200]}"
        )

    posts_text = "\n\n".join(post_summaries)

    prompt = f"""Rate how relevant each post is to the query on a scale of 0.0 to 1.0.

Query: {query}

Posts to rate:
{posts_text}

Respond with ONLY a JSON array of {len(posts)} scores in the same order as the posts.
Example for {len(posts)} posts: {[0.5] * len(posts)}
Score 1.0 = highly relevant, 0.0 = completely irrelevant.
Return ONLY the JSON array, no other text."""

    try:
        response = call_llm(
            prompt,
            provider="openai",
            model="gpt-4o-mini",
            max_tokens=100,
        )

        clean = response.strip().replace("```json", "").replace("```", "").strip()
        scores = json.loads(clean)

        if not isinstance(scores, list):
            raise ValueError(f"Expected list, got {type(scores)}")

        while len(scores) < len(posts):
            scores.append(0.5)
        scores = scores[:len(posts)]

        return [max(0.0, min(1.0, float(s))) for s in scores]

    except Exception as e:
        logger.warning(f"Batch grading failed for {len(posts)} posts: {e}. Using 0.5 defaults.")
        return [0.5] * len(posts)


def grade_relevance(query: str, posts: list[dict]) -> tuple[float, list[dict]]:
    """
    Score all retrieved posts for relevance to the query.

    Uses mini-batches of GRADING_BATCH_SIZE (10) posts per LLM call.
    For 40 posts: 4 API calls instead of 40 (10x improvement).
    For 20 posts: 2 API calls instead of 20.

    Mini-batches of 10 chosen over full batching because:
    - Model attention stays focused per batch (better quality)
    - JSON parse errors rare with only 10 items
    - Score calibration consistent within each batch

    Returns:
        (avg_score, graded_posts) where each post has a 'relevance_score' field.
    """
    if not posts:
        return 0.0, []

    all_scores = []
    graded = []
    total_batches = (len(posts) + GRADING_BATCH_SIZE - 1) // GRADING_BATCH_SIZE

    for batch_idx in range(0, len(posts), GRADING_BATCH_SIZE):
        batch = posts[batch_idx: batch_idx + GRADING_BATCH_SIZE]
        batch_num = (batch_idx // GRADING_BATCH_SIZE) + 1

        logger.info(f"Grading batch {batch_num}/{total_batches} ({len(batch)} posts)")

        scores = _grade_batch(query, batch)

        for post, score in zip(batch, scores):
            post["relevance_score"] = score
            graded.append(post)
            all_scores.append(score)

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
    logger.info(
        f"Relevance grading complete: {len(posts)} posts graded in "
        f"{total_batches} batches (avg={avg_score:.3f})"
    )
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
    Full Corrective RAG pipeline with query expansion:
    1. Expand query into 4 variants (1 LLM call)
    2. Hybrid retrieval across all variants (pgvector + FTS)
    3. Batch relevance grading — 10 posts per LLM call
    4. Retry with wider search if avg < threshold
    5. Cross-encoder reranking (local, no API calls)
    6. Insight generation via OpenAI (1 LLM call)

    Returns dict with report, sources_used, generated_at, query_variants.
    """
    query_hash = make_query_hash(query)
    tracker = LLMTracker(query=query, query_hash=query_hash)

    logger.info(f"Corrective RAG pipeline started for: '{query[:80]}'")

    # Step 1 — Query expansion
    expanded_queries = expand_query(query)
    logger.info(f"Expanded to {len(expanded_queries)} query variants")

    # Step 2 — Initial retrieval with expanded queries
    posts = retrieve(query, limit=INITIAL_LIMIT, expanded_queries=expanded_queries)

    # Step 3 — Batch relevance grading (10 posts per LLM call)
    avg_score, graded_posts = grade_relevance(query, posts)

    # Step 4 — Retry with wider search if below threshold
    if avg_score < RELEVANCE_THRESHOLD:
        logger.info(
            f"Avg relevance {avg_score:.3f} below threshold {RELEVANCE_THRESHOLD} "
            f"— retrying with wider search (limit={WIDE_LIMIT})"
        )
        posts = retrieve(query, limit=WIDE_LIMIT, expanded_queries=expanded_queries)
        avg_score, graded_posts = grade_relevance(query, posts)
        logger.info(f"Retry avg relevance: {avg_score:.3f}")

    # Step 5 — Filter low-relevance posts
    relevant_posts = [p for p in graded_posts if p.get("relevance_score", 0) >= MIN_POST_SCORE]
    if not relevant_posts:
        relevant_posts = graded_posts[:limit]

    # Step 6 — Rerank
    reranked = rerank(query, relevant_posts, top_k=limit)

    # Step 7 — Generate insight (1 OpenAI call)
    report = generate_insight(query, reranked)

    # Step 8 — Log and save LLM usage
    tracker.log_summary()
    tracker.save()

    # Step 9 — Collect source URLs
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
        "query_variants": len(expanded_queries),
    }


# ── Query hash for Redis caching ──────────────────────────────────────────────

def make_query_hash(query: str) -> str:
    """Generate a stable cache key hash from query string."""
    return hashlib.md5(query.strip().lower().encode()).hexdigest()
