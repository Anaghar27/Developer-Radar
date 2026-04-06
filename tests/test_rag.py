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

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = [dict(p) for p in SAMPLE_POSTS]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("rag.hybrid_retriever._get_embedding", return_value=[0.1] * 1536), \
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

    with patch("rag.corrective_rag.expand_query", return_value=["What do developers think about PyTorch?"]), \
         patch("rag.corrective_rag.retrieve", return_value=list(SAMPLE_POSTS)), \
         patch("rag.corrective_rag.grade_relevance", return_value=(0.8, list(SAMPLE_POSTS))), \
         patch("rag.corrective_rag.rerank", return_value=list(SAMPLE_POSTS)), \
         patch("rag.corrective_rag.generate_insight", return_value="Mock insight report"):

        result = run_corrective_rag("What do developers think about PyTorch?")

    assert "report" in result
    assert "sources_used" in result
    assert "generated_at" in result
    assert result["report"] == "Mock insight report"


# ── batch relevance grading ───────────────────────────────────────────────────

def test_batch_relevance_grading_single_llm_call():
    """grade_relevance() makes exactly 1 LLM call for 10 posts."""
    from rag.corrective_rag import grade_relevance

    posts = [
        {"post_id": f"post_{i}", "title": f"Title {i}", "body": f"Body {i}"}
        for i in range(10)
    ]

    with patch("rag.corrective_rag.call_llm",
               return_value="[0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]") as mock_llm:
        avg, graded = grade_relevance("test query", posts)

    assert mock_llm.call_count == 1, f"Expected 1 batch call, got {mock_llm.call_count}"
    assert len(graded) == 10
    assert abs(avg - 0.45) < 0.01
    assert all("relevance_score" in p for p in graded)


def test_batch_relevance_grading_fallback_on_error():
    """grade_relevance() falls back to 0.5 scores if LLM call fails."""
    from rag.corrective_rag import grade_relevance

    posts = [
        {"post_id": "a", "title": "Test", "body": "Body"},
        {"post_id": "b", "title": "Test 2", "body": "Body 2"},
    ]

    with patch("rag.corrective_rag.call_llm", side_effect=Exception("API down")):
        avg, graded = grade_relevance("test query", posts)

    assert len(graded) == 2
    assert all(p["relevance_score"] == 0.5 for p in graded)
    assert avg == 0.5


def test_batch_relevance_grading_malformed_response():
    """grade_relevance() handles malformed JSON response gracefully."""
    from rag.corrective_rag import grade_relevance

    posts = [{"post_id": "a", "title": "Test", "body": "Body"}]

    with patch("rag.corrective_rag.call_llm", return_value="not valid json at all"):
        _, graded = grade_relevance("test query", posts)

    assert graded[0]["relevance_score"] == 0.5


# ── query expansion ───────────────────────────────────────────────────────────

def test_expand_query_returns_4_variants():
    """expand_query() returns original + 3 variants = 4 total."""
    from rag.corrective_rag import expand_query

    with patch("rag.corrective_rag.call_llm",
               return_value='["pytorch optimization", "torch training speed", "deep learning perf"]'):
        variants = expand_query("pytorch performance")

    assert len(variants) == 4
    assert variants[0] == "pytorch performance"
    assert "pytorch optimization" in variants


def test_expand_query_fallback_on_error():
    """expand_query() returns [original_query] on failure."""
    from rag.corrective_rag import expand_query

    with patch("rag.corrective_rag.call_llm", side_effect=Exception("API down")):
        variants = expand_query("pytorch performance")

    assert variants == ["pytorch performance"]
    assert len(variants) == 1


def test_expand_query_original_always_first():
    """Original query is always the first element."""
    from rag.corrective_rag import expand_query

    original = "what is the best ML framework"
    with patch("rag.corrective_rag.call_llm",
               return_value='["top ML libraries", "best deep learning tools", "AI framework comparison"]'):
        variants = expand_query(original)

    assert variants[0] == original


# ── retrieve with expansion ───────────────────────────────────────────────────

def test_retrieve_with_expanded_queries():
    """retrieve() deduplicates posts appearing across multiple query variants."""
    from rag.hybrid_retriever import retrieve

    mock_post = {
        "post_id": "abc",
        "title": "PyTorch rocks",
        "body": "Great",
        "source": "reddit",
        "url": "http://example.com",
        "sentiment": "positive",
        "topic": "machine_learning",
        "tool_mentioned": "pytorch",
        "controversy_score": 0.1,
        "similarity_score": 0.9,
    }

    with patch("rag.hybrid_retriever.semantic_search", return_value=[mock_post]), \
         patch("rag.hybrid_retriever.keyword_search", return_value=[mock_post]):
        results = retrieve(
            "pytorch",
            limit=10,
            expanded_queries=["pytorch", "torch", "pytorch framework"],
        )

    post_ids = [r["post_id"] for r in results]
    assert len(set(post_ids)) == len(post_ids), "Duplicate post_ids found after dedup"


def test_corrective_rag_uses_query_expansion():
    """run_corrective_rag() calls expand_query and passes variants to retrieve."""
    from rag.corrective_rag import run_corrective_rag

    with patch("rag.corrective_rag.expand_query",
               return_value=["original", "variant1", "variant2", "variant3"]) as mock_expand, \
         patch("rag.corrective_rag.retrieve", return_value=list(SAMPLE_POSTS)) as mock_retrieve, \
         patch("rag.corrective_rag.grade_relevance", return_value=(0.8, list(SAMPLE_POSTS))), \
         patch("rag.corrective_rag.rerank", return_value=list(SAMPLE_POSTS)), \
         patch("rag.corrective_rag.generate_insight", return_value="Mock report"):

        result = run_corrective_rag("original query")

    mock_expand.assert_called_once_with("original query")
    call_kwargs = mock_retrieve.call_args.kwargs
    assert "expanded_queries" in call_kwargs
    assert len(call_kwargs["expanded_queries"]) == 4
    assert "query_variants" in result
    assert result["query_variants"] == 4


# ── corrective_rag retry logic ────────────────────────────────────────────────

def test_corrective_rag_retries_when_relevance_low():
    """
    run_corrective_rag() retries with wider search when avg relevance < threshold.
    On retry, retrieve is called with WIDE_LIMIT instead of INITIAL_LIMIT.
    """
    from rag.corrective_rag import run_corrective_rag, RELEVANCE_THRESHOLD, WIDE_LIMIT

    retrieve_call_count = {"n": 0}

    def mock_retrieve(query, limit, expanded_queries=None):
        retrieve_call_count["n"] += 1
        return list(SAMPLE_POSTS)

    # First grading returns low score → triggers retry; second is high → proceeds
    grade_results = [
        (RELEVANCE_THRESHOLD - 0.1, list(SAMPLE_POSTS)),
        (RELEVANCE_THRESHOLD + 0.1, list(SAMPLE_POSTS)),
    ]

    with patch("rag.corrective_rag.expand_query", return_value=["query"]), \
         patch("rag.corrective_rag.retrieve", side_effect=mock_retrieve), \
         patch("rag.corrective_rag.grade_relevance", side_effect=grade_results), \
         patch("rag.corrective_rag.rerank", return_value=list(SAMPLE_POSTS)), \
         patch("rag.corrective_rag.generate_insight", return_value="Report"):

        run_corrective_rag("test query")

    assert retrieve_call_count["n"] == 2, \
        f"Expected 2 retrieve calls (initial + retry), got {retrieve_call_count['n']}"


def test_corrective_rag_no_retry_when_relevance_high():
    """
    run_corrective_rag() does NOT retry when avg relevance >= threshold.
    retrieve should be called exactly once.
    """
    from rag.corrective_rag import run_corrective_rag, RELEVANCE_THRESHOLD

    retrieve_call_count = {"n": 0}

    def mock_retrieve(query, limit, expanded_queries=None):
        retrieve_call_count["n"] += 1
        return list(SAMPLE_POSTS)

    with patch("rag.corrective_rag.expand_query", return_value=["query"]), \
         patch("rag.corrective_rag.retrieve", side_effect=mock_retrieve), \
         patch("rag.corrective_rag.grade_relevance",
               return_value=(RELEVANCE_THRESHOLD + 0.1, list(SAMPLE_POSTS))), \
         patch("rag.corrective_rag.rerank", return_value=list(SAMPLE_POSTS)), \
         patch("rag.corrective_rag.generate_insight", return_value="Report"):

        run_corrective_rag("test query")

    assert retrieve_call_count["n"] == 1, \
        f"Expected 1 retrieve call, got {retrieve_call_count['n']}"


def test_corrective_rag_empty_posts_returns_gracefully():
    """
    run_corrective_rag() handles empty retrieval without crashing.
    Returns a report even when no posts are found.
    """
    from rag.corrective_rag import run_corrective_rag

    with patch("rag.corrective_rag.expand_query", return_value=["query"]), \
         patch("rag.corrective_rag.retrieve", return_value=[]), \
         patch("rag.corrective_rag.grade_relevance", return_value=(0.0, [])), \
         patch("rag.corrective_rag.rerank", return_value=[]), \
         patch("rag.corrective_rag.generate_insight",
               return_value="No relevant posts found."):

        result = run_corrective_rag("obscure query with no results")

    assert "report" in result
    assert "sources_used" in result
    assert result["report"] == "No relevant posts found."


# ── hybrid_retriever deduplication ───────────────────────────────────────────

def test_hybrid_retriever_deduplicates_across_query_variants():
    """
    retrieve() with expanded_queries deduplicates posts appearing
    in multiple query variant results.
    """
    from rag.hybrid_retriever import retrieve

    post = {
        "post_id": "duplicate_post",
        "title": "Same post appears in all queries",
        "body": "body text",
        "source": "reddit",
        "url": "http://example.com",
        "sentiment": "positive",
        "topic": "machine_learning",
        "tool_mentioned": "pytorch",
        "controversy_score": 0.1,
        "similarity_score": 0.9,
    }

    # Same post returned by both searches for all 3 query variants
    with patch("rag.hybrid_retriever.semantic_search", return_value=[post]), \
         patch("rag.hybrid_retriever.keyword_search", return_value=[post]):
        results = retrieve(
            "pytorch",
            limit=10,
            expanded_queries=["pytorch", "torch", "pytorch framework"],
        )

    post_ids = [r["post_id"] for r in results]
    assert post_ids.count("duplicate_post") == 1, \
        "Duplicate post should appear only once after deduplication"
