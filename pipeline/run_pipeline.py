"""Run the developer sentiment pipeline end-to-end from one entrypoint."""

import argparse
import logging
import subprocess
import sys
from datetime import UTC, datetime

from ingestion import hackernews_ingestor, reddit_ingestor
from pipeline.aggregator import run_aggregation
from processing.embedder import run_embeddings
from processing.llm_processor import process_batch
from storage.db_client import get_connection


logger = logging.getLogger(__name__)


def _fetch_scalar(query: str):
    """Run a scalar SQL query and return the first column of the first row."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
            return row[0] if row else None


def _log_summary(target_date: str) -> None:
    """Log a compact pipeline summary from the database."""
    raw_count = _fetch_scalar("SELECT COUNT(*) FROM raw_posts")
    processed_count = _fetch_scalar("SELECT COUNT(*) FROM processed_posts")
    embedding_count = _fetch_scalar("SELECT COUNT(*) FROM post_embeddings")
    aggregate_count = _fetch_scalar(
        f"SELECT COUNT(*) FROM daily_aggregates WHERE date = '{target_date}'"
    )

    logger.info(
        "Pipeline summary: raw_posts=%s processed_posts=%s post_embeddings=%s daily_aggregates_for_%s=%s",
        raw_count,
        processed_count,
        embedding_count,
        target_date,
        aggregate_count,
    )


def _run_tests() -> None:
    """Run the local ingestion and processing test suites."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_ingestion.py",
        "tests/test_processing.py",
        "-q",
    ]
    logger.info("Running tests: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    """Run ingestion, embeddings, classification, aggregation, and optional tests."""
    parser = argparse.ArgumentParser(description="Run the developer sentiment pipeline.")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Batch size for embeddings and LLM processing.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Aggregation date in YYYY-MM-DD format. Defaults to today in UTC.",
    )
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Skip Reddit and Hacker News ingestion.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run ingestion and processing pytest suites after the pipeline.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    target_date = args.date or datetime.now(UTC).date().isoformat()

    if not args.skip_ingestion:
        logger.info("Starting Reddit ingestion")
        reddit_ingestor.run()
        logger.info("Starting Hacker News ingestion")
        hackernews_ingestor.run()

    logger.info("Starting embedding generation with limit=%s", args.limit)
    run_embeddings(args.limit)

    logger.info("Starting LLM classification with limit=%s", args.limit)
    process_batch(args.limit)

    logger.info("Starting aggregation for date=%s", target_date)
    run_aggregation(target_date)

    _log_summary(target_date)

    if args.run_tests:
        _run_tests()


if __name__ == "__main__":
    main()
