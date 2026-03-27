"""Daily aggregate computation for processed post classifications."""

import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime

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


def detect_volume_spikes(
    date: str | None = None,
    lookback_days: int = 7,
    min_baseline_count: int = 1,
    min_pct_increase: float = 100.0,
) -> list[dict]:
    """Detect topic-level daily volume spikes versus a rolling historical average."""
    target_date = date or datetime.now(UTC).date().isoformat()
    query = """
        WITH today AS (
            SELECT
                topic,
                SUM(post_count) AS today_count
            FROM daily_aggregates
            WHERE date = %s
            GROUP BY topic
        ),
        history AS (
            SELECT
                topic,
                AVG(daily_count) AS rolling_avg
            FROM (
                SELECT
                    date,
                    topic,
                    SUM(post_count) AS daily_count
                FROM daily_aggregates
                WHERE date < %s
                  AND date >= %s::date - (%s || ' days')::interval
                GROUP BY date, topic
            ) grouped_history
            GROUP BY topic
        )
        SELECT
            t.topic,
            t.today_count,
            COALESCE(h.rolling_avg, 0) AS rolling_avg
        FROM today AS t
        LEFT JOIN history AS h
            ON t.topic = h.topic
    """

    spikes: list[dict] = []
    with db_client.get_connection() as conn:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(query, (target_date, target_date, target_date, lookback_days))
            rows = cur.fetchall()

    for row in rows:
        today_count = int(row["today_count"] or 0)
        rolling_avg = float(row["rolling_avg"] or 0)

        if rolling_avg < min_baseline_count:
            continue

        pct_increase = ((today_count - rolling_avg) / rolling_avg) * 100
        if pct_increase < min_pct_increase:
            continue

        spike = {
            "topic": row["topic"],
            "today_count": today_count,
            "rolling_avg": rolling_avg,
            "pct_increase": pct_increase,
        }
        db_client.insert_alert(
            topic=spike["topic"],
            today_count=spike["today_count"],
            rolling_avg=spike["rolling_avg"],
            pct_increase=spike["pct_increase"],
        )
        spikes.append(spike)

    return spikes


if __name__ == "__main__":
    run_aggregation()
