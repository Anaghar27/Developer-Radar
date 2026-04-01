from unittest.mock import MagicMock, patch

import pytest

SAMPLE_POSTS = [
    {
        "post_id": "abc123",
        "title": "PyTorch 2.0 is amazing for production",
        "body": "We migrated our ML pipeline to PyTorch 2.0 and saw 40% speedup",
        "source": "reddit",
        "url": "https://reddit.com/r/MachineLearning/abc123",
        "sentiment": "positive",
        "topic": "machine_learning",
        "tool_mentioned": "pytorch",
        "controversy_score": 0.1,
        "similarity_score": 0.95,
    },
    {
        "post_id": "def456",
        "title": "TensorFlow vs PyTorch in 2024",
        "body": "Comparing the two frameworks for deep learning",
        "source": "hackernews",
        "url": "https://news.ycombinator.com/item?id=def456",
        "sentiment": "neutral",
        "topic": "machine_learning",
        "tool_mentioned": "tensorflow",
        "controversy_score": 0.3,
        "similarity_score": 0.80,
    },
]


# ── hybrid_retriever ──────────────────────────────────────────────────────────

def test_semantic_search_returns_posts():
    """semantic_search returns a list of post dicts."""
    from rag.hybrid_retriever import semantic_search

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value.data = [MagicMock(embedding=[0.1] * 1536)]

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = [dict(p) for p in SAMPLE_POSTS]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("rag.hybrid_retriever.get_openai_client", return_value=mock_client), \
         patch("rag.hybrid_retriever.get_pg_connection", return_value=mock_conn):
        results = semantic_search("pytorch production", limit=10)

    assert isinstance(results, list)
    assert len(results) == 2


def test_keyword_search_returns_posts():
    """keyword_search returns a list of post dicts."""
    from rag.hybrid_retriever import keyword_search

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = [dict(p) for p in SAMPLE_POSTS[:1]]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("rag.hybrid_retriever.get_pg_connection", return_value=mock_conn):
        results = keyword_search("pytorch", limit=10)

    assert isinstance(results, list)
    assert len(results) == 1


def test_reciprocal_rank_fusion():
    """RRF combines two result lists and assigns rrf_score."""
    from rag.hybrid_retriever import reciprocal_rank_fusion

    semantic = [SAMPLE_POSTS[0], SAMPLE_POSTS[1]]
    keyword = [SAMPLE_POSTS[1], SAMPLE_POSTS[0]]

    fused = reciprocal_rank_fusion(semantic, keyword)

    assert len(fused) == 2
    assert all("rrf_score" in p for p in fused)
    assert fused[0]["rrf_score"] > 0


# ── reranker ──────────────────────────────────────────────────────────────────

def test_rerank_returns_top_k():
    """rerank returns at most top_k posts."""
    from rag.reranker import rerank

    mock_ce = MagicMock()
    mock_ce.predict.return_value = [0.9, 0.5]

    with patch("rag.reranker.get_cross_encoder", return_value=mock_ce):
        result = rerank("pytorch", list(SAMPLE_POSTS), top_k=1)

    assert len(result) == 1
    assert "rerank_score" in result[0]


def test_rerank_fallback_when_model_unavailable():
    """rerank falls back to original order when cross-encoder unavailable."""
    from rag.reranker import rerank

    with patch("rag.reranker.get_cross_encoder", return_value=None):
        result = rerank("pytorch", list(SAMPLE_POSTS), top_k=2)

    assert len(result) == 2


# ── corrective_rag ────────────────────────────────────────────────────────────

def test_make_query_hash_stable():
    """Same query always produces the same hash."""
    from rag.corrective_rag import make_query_hash

    h1 = make_query_hash("What do developers think about PyTorch?")
    h2 = make_query_hash("What do developers think about PyTorch?")
    h3 = make_query_hash("  What do developers think about PyTorch?  ")

    assert h1 == h2
    assert h1 == h3


def test_make_query_hash_different_queries():
    """Different queries produce different hashes."""
    from rag.corrective_rag import make_query_hash

    h1 = make_query_hash("pytorch sentiment")
    h2 = make_query_hash("tensorflow sentiment")
    assert h1 != h2


def test_run_corrective_rag_returns_report():
    """run_corrective_rag returns a dict with report and sources_used."""
    from rag.corrective_rag import run_corrective_rag

    with patch("rag.corrective_rag.retrieve", return_value=list(SAMPLE_POSTS)), \
         patch("rag.corrective_rag.grade_relevance", return_value=(0.8, list(SAMPLE_POSTS))), \
         patch("rag.corrective_rag.rerank", return_value=list(SAMPLE_POSTS)), \
         patch("rag.corrective_rag.generate_insight", return_value="Mock insight report"):

        result = run_corrective_rag("What do developers think about PyTorch?")

    assert "report" in result
    assert "sources_used" in result
    assert "generated_at" in result
    assert result["report"] == "Mock insight report"
