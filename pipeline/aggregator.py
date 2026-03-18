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


if __name__ == "__main__":
    run_aggregation()
