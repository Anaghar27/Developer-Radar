"""Daily aggregate computation for processed post classifications."""
# NOTE: run_aggregation() writes to the legacy daily_aggregates PostgreSQL table.
# For current aggregations, use detect_volume_spikes() which reads from
# mart_trending_topics DuckDB mart (built by dbt on every DAG 2 run).
# run_aggregation() is kept for backward compatibility only.

import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime, timezone

from psycopg2 import extras

from storage import db_client

logger = logging.getLogger(__name__)


def _sentiment_to_score(sentiment: str) -> float:
    """Map a sentiment label to its numeric aggregate score."""
    mapping = {
        "positive": 1.0,
        "neutral": 0.0,
        "negative": -1.0,
    }
    return mapping[sentiment]


def _compute_aggregates(date: str) -> list[dict]:
    """Compute per-topic and per-tool aggregates for all posts on the given date."""
    query = """
        SELECT
            p.sentiment,
            p.emotion,
            p.topic,
            p.tool_mentioned
        FROM processed_posts AS p
        JOIN raw_posts AS r
            ON p.post_id = r.id
        WHERE DATE(r.created_at) = %s
    """

    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"sentiment_scores": [], "emotions": []}
    )

    with db_client.get_connection() as conn:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(query, (date,))
            rows = cur.fetchall()

    for row in rows:
        tool = row["tool_mentioned"] or "none"
        key = (row["topic"], tool)
        grouped[key]["sentiment_scores"].append(_sentiment_to_score(row["sentiment"]))
        grouped[key]["emotions"].append(row["emotion"])

    aggregates = []
    for (topic, tool), values in grouped.items():
        emotion_counts = Counter(values["emotions"])
        dominant_emotion = emotion_counts.most_common(1)[0][0]
        avg_sentiment = sum(values["sentiment_scores"]) / len(values["sentiment_scores"])

        aggregates.append(
            {
                "date": date,
                "topic": topic,
                "tool": tool,
                "avg_sentiment": avg_sentiment,
                "dominant_emotion": dominant_emotion,
                "post_count": len(values["sentiment_scores"]),
            }
        )

    return aggregates


def run_aggregation(date: str = None):
    """Compute and upsert daily aggregates for the given date or for today by default."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    target_date = date or datetime.now(UTC).date().isoformat()
    aggregate_rows = _compute_aggregates(target_date)

    for record in aggregate_rows:
        db_client.upsert_daily_aggregate(record)

    logger.info(
        "Aggregation complete for date=%s rows_upserted=%s",
        target_date,
        len(aggregate_rows),
    )


def detect_volume_spikes(date=None):
    """
    Detect volume spikes by reading from mart_trending_topics DuckDB mart.
    Returns list of spike dicts for topics where spike_flag is True.
    """
    import os

    import duckdb

    duckdb_path = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")
    target_date = date or datetime.now(UTC).date()

    try:
        conn = duckdb.connect(duckdb_path, read_only=True)
        results = conn.execute("""
            SELECT
                topic,
                today_count,
                rolling_avg_7d,
                pct_change,
                spike_flag
            FROM mart_trending_topics
            WHERE post_date = ?
            AND spike_flag = true
            ORDER BY pct_change DESC
        """, [target_date]).fetchall()
        conn.close()

        spikes = []
        for row in results:
            if row[0] is None:
                logging.warning("Skipping spike row with null topic: %s", row)
                continue
            spikes.append({
                "topic": row[0],
                "today_count": row[1],
                "rolling_avg": row[2],
                "pct_increase": row[3],
                "spike_flag": row[4],
            })

        logging.info(f"Detected {len(spikes)} volume spikes for {target_date}")
        return spikes

    except Exception as e:
        logging.error(f"Failed to read mart_trending_topics: {e}")
        return []


if __name__ == "__main__":
    run_aggregation()
