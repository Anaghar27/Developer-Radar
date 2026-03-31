import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Load cross-encoder once at module level
_cross_encoder = None


def get_cross_encoder():
    """Lazy load cross-encoder model."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Cross-encoder model loaded")
        except Exception as e:
            logger.warning(f"Could not load cross-encoder: {e}. Reranking disabled.")
            _cross_encoder = None
    return _cross_encoder


def rerank(query: str, posts: list[dict], top_k: int = 10) -> list[dict]:
    """
    Rerank retrieved posts using cross-encoder scoring.

    Cross-encoder scores query-document pairs jointly,
    producing more accurate relevance scores than
    bi-encoder similarity alone.

    Falls back to original order if model unavailable.

    Args:
        query: The user's natural language query
        posts: List of post dicts from hybrid_retriever
        top_k: Number of top results to return after reranking

    Returns:
        Top k posts sorted by cross-encoder score descending.
        Each post dict gains a 'rerank_score' field.
    """
    if not posts:
        return []

    cross_encoder = get_cross_encoder()

    if cross_encoder is None:
        logger.warning("Cross-encoder unavailable — returning original order")
        return posts[:top_k]

    try:
        # Build query-document pairs
        pairs = [
            (query, f"{post.get('title', '')} {post.get('body', '')[:500]}")
            for post in posts
        ]

        # Score all pairs
        scores = cross_encoder.predict(pairs)

        # Attach scores and sort
        for post, score in zip(posts, scores):
            post["rerank_score"] = float(score)

        reranked = sorted(posts, key=lambda p: p.get("rerank_score", 0), reverse=True)
        top = reranked[:top_k]

        logger.info(f"Reranked {len(posts)} posts → top {len(top)}")
        return top

    except Exception as e:
        logger.warning(f"Reranking failed: {e}. Returning original order.")
        return posts[:top_k]
