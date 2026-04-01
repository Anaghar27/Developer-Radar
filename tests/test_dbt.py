import os

import duckdb
import pytest

DUCKDB_PATH = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")


@pytest.fixture(scope="module")
def duckdb_conn():
    """Connect to DuckDB — skip all tests if file doesn't exist."""
    if not os.path.exists(DUCKDB_PATH):
        pytest.skip(f"DuckDB file not found at {DUCKDB_PATH} — run dbt first")
    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    yield conn
    conn.close()


def _exec_or_skip(conn, query: str, skip_msg: str):
    """
    Execute a query against DuckDB. Skip the test if the pg catalog is not
    configured — staging models are views that query PostgreSQL live and
    require the dbt postgres_scanner extension to be active.
    """
    try:
        return conn.execute(query)
    except duckdb.BinderException as e:
        if "pg" in str(e):
            pytest.skip(f"{skip_msg} (requires live pg catalog — run via dbt)")
        raise


def test_stg_raw_posts_exists(duckdb_conn):
    """stg_raw_posts view exists and has rows."""
    result = _exec_or_skip(
        duckdb_conn,
        "SELECT COUNT(*) FROM stg_raw_posts",
        "stg_raw_posts is a view over PostgreSQL",
    )
    count = result.fetchone()[0]
    assert count > 0, "stg_raw_posts is empty"


def test_stg_raw_posts_no_null_post_ids(duckdb_conn):
    """No null post_ids in stg_raw_posts."""
    result = _exec_or_skip(
        duckdb_conn,
        "SELECT COUNT(*) FROM stg_raw_posts WHERE post_id IS NULL",
        "stg_raw_posts is a view over PostgreSQL",
    )
    assert result.fetchone()[0] == 0


def test_stg_raw_posts_valid_sources(duckdb_conn):
    """All sources are reddit or hackernews."""
    result = _exec_or_skip(
        duckdb_conn,
        "SELECT COUNT(*) FROM stg_raw_posts WHERE source NOT IN ('reddit', 'hackernews')",
        "stg_raw_posts is a view over PostgreSQL",
    )
    assert result.fetchone()[0] == 0


def test_stg_processed_posts_valid_sentiments(duckdb_conn):
    """All sentiment values are valid enums."""
    count_result = _exec_or_skip(
        duckdb_conn,
        "SELECT COUNT(*) FROM stg_processed_posts",
        "stg_processed_posts is a view over PostgreSQL",
    )
    if count_result.fetchone()[0] == 0:
        pytest.skip("No processed posts yet")
    invalid = duckdb_conn.execute("""
        SELECT COUNT(*) FROM stg_processed_posts
        WHERE sentiment NOT IN ('positive', 'negative', 'neutral')
    """).fetchone()[0]
    assert invalid == 0


def test_mart_daily_sentiment_exists(duckdb_conn):
    """mart_daily_sentiment table exists."""
    count = duckdb_conn.execute("SELECT COUNT(*) FROM mart_daily_sentiment").fetchone()[0]
    assert count >= 0   # empty is ok — table must exist


def test_mart_trending_topics_spike_flag_is_boolean(duckdb_conn):
    """spike_flag only contains True or False."""
    invalid = duckdb_conn.execute("""
        SELECT COUNT(*) FROM mart_trending_topics
        WHERE spike_flag IS NULL
    """).fetchone()[0]
    assert invalid == 0


def test_mart_trending_topics_rolling_avg_non_negative(duckdb_conn):
    """rolling_avg_7d is always >= 0."""
    invalid = duckdb_conn.execute("""
        SELECT COUNT(*) FROM mart_trending_topics
        WHERE rolling_avg_7d < 0
    """).fetchone()[0]
    assert invalid == 0


def test_int_posts_enriched_sentiment_score_range(duckdb_conn):
    """sentiment_score is always -1, 0, or 1."""
    result = _exec_or_skip(
        duckdb_conn,
        """
        SELECT COUNT(*) FROM int_posts_enriched
        WHERE sentiment_score NOT IN (-1, 0, 1)
        AND is_classified = true
        """,
        "int_posts_enriched is a view over PostgreSQL",
    )
    assert result.fetchone()[0] == 0
