import logging
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from processing.llm_client import get_embedding as _get_embedding

load_dotenv()
logger = logging.getLogger(__name__)


def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "developer_intelligence"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def semantic_search(query: str, limit: int = 20) -> list[dict]:
    """
    pgvector cosine similarity search.
    Returns list of dicts with post_id, title, body, source,
    sentiment, topic, tool_mentioned, score, rank.
    """
    query_embedding = _get_embedding(query)

    conn = get_pg_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    r.id         AS post_id,
                    r.title,
                    r.body,
                    r.source,
                    r.url,
                    p.sentiment,
                    p.topic,
                    p.tool_mentioned,
                    p.controversy_score,
                    1 - (e.embedding <=> %s::vector) AS similarity_score
                FROM post_embeddings e
                JOIN raw_posts r ON e.post_id = r.id
                LEFT JOIN processed_posts p ON r.id = p.post_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, limit))
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def keyword_search(query: str, limit: int = 20) -> list[dict]:
    """
    PostgreSQL full-text search using tsvector.
    Catches exact tool names and version numbers that
    semantic search often misses.
    Returns list of dicts with same schema as semantic_search.
    """
    conn = get_pg_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    r.id         AS post_id,
                    r.title,
                    r.body,
                    r.source,
                    r.url,
                    p.sentiment,
                    p.topic,
                    p.tool_mentioned,
                    p.controversy_score,
                    ts_rank(
                        to_tsvector('english', r.title || ' ' || coalesce(r.body, '')),
                        plainto_tsquery('english', %s)
                    ) AS similarity_score
                FROM raw_posts r
                LEFT JOIN processed_posts p ON r.id = p.post_id
                WHERE to_tsvector('english', r.title || ' ' || coalesce(r.body, ''))
                    @@ plainto_tsquery('english', %s)
                ORDER BY similarity_score DESC
                LIMIT %s
            """, (query, query, limit))
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def reciprocal_rank_fusion(
    semantic_results: list[dict],
    keyword_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Combine semantic and keyword results using Reciprocal Rank Fusion.
    RRF score = 1/(k + rank) summed across both result lists.
    Returns merged list sorted by RRF score descending.
    """
    scores: dict[str, float] = {}
    posts: dict[str, dict] = {}

    for rank, post in enumerate(semantic_results, start=1):
        pid = post["post_id"]
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
        posts[pid] = post

    for rank, post in enumerate(keyword_results, start=1):
        pid = post["post_id"]
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
        if pid not in posts:
            posts[pid] = post

    sorted_ids = sorted(scores, key=lambda pid: scores[pid], reverse=True)
    return [
        {**posts[pid], "rrf_score": scores[pid]}
        for pid in sorted_ids
    ]


def retrieve(query: str, limit: int = 20, expanded_queries: list[str] | None = None) -> list[dict]:
    """
    Hybrid retrieval with optional query expansion.

    If expanded_queries provided, retrieves for each query variant
    and merges results via RRF for better recall.

    Args:
        query: Original query string
        limit: Max results to return
        expanded_queries: Optional list of query variants from expand_query()

    Returns:
        Top `limit` results ranked by RRF score.
    """
    queries = expanded_queries if expanded_queries else [query]
    logger.info(f"Hybrid retrieval for {len(queries)} query variants, limit={limit}")

    all_semantic = []
    all_keyword = []

    for q in queries:
        semantic = semantic_search(q, limit=limit)
        keyword = keyword_search(q, limit=limit)
        all_semantic.extend(semantic)
        all_keyword.extend(keyword)

    # Deduplicate by post_id before fusion — keep highest similarity_score
    seen_semantic: dict[str, dict] = {}
    for post in all_semantic:
        pid = post["post_id"]
        if pid not in seen_semantic or \
           post.get("similarity_score", 0) > seen_semantic[pid].get("similarity_score", 0):
            seen_semantic[pid] = post

    seen_keyword: dict[str, dict] = {}
    for post in all_keyword:
        pid = post["post_id"]
        if pid not in seen_keyword or \
           post.get("similarity_score", 0) > seen_keyword[pid].get("similarity_score", 0):
            seen_keyword[pid] = post

    fused = reciprocal_rank_fusion(
        list(seen_semantic.values()),
        list(seen_keyword.values()),
    )
    top = fused[:limit]

    logger.info(f"After multi-query RRF fusion: {len(top)} results")
    return top
