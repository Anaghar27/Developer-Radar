"""Reddit ingestion for the developer sentiment intelligence pipeline."""

import logging
import os
from datetime import UTC, datetime

import praw
from prawcore import exceptions as prawcore_exceptions

from storage.db_client import insert_raw_post, post_exists


logger = logging.getLogger(__name__)

SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "datascience",
    "python",
    "ollama",
]


def get_reddit_client() -> praw.Reddit:
    """Create and return a read-only Reddit client from environment variables."""
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )
    reddit.read_only = True
    return reddit


def map_submission(submission) -> dict:
    """Map a PRAW submission into the raw_posts schema."""
    return {
        "id": f"reddit_{submission.id}",
        "source": "reddit",
        "title": submission.title,
        "body": submission.selftext or "",
        "url": submission.url,
        "score": submission.score,
        "created_at": datetime.fromtimestamp(submission.created_utc, UTC),
    }


def ingest_subreddit(reddit: praw.Reddit, subreddit_name: str) -> None:
    """Fetch hot posts for one subreddit and insert them into raw_posts."""
    fetched_count = 0
    new_count = 0

    try:
        subreddit = reddit.subreddit(subreddit_name)
        for submission in subreddit.hot(limit=500):
            try:
                post = map_submission(submission)
                fetched_count += 1
                if not post_exists(post["id"]):
                    new_count += 1
                insert_raw_post(post)
            except prawcore_exceptions.PrawcoreException:
                logger.exception(
                    "Failed to process Reddit submission %s from r/%s",
                    getattr(submission, "id", "unknown"),
                    subreddit_name,
                )
            except Exception:
                logger.exception(
                    "Unexpected error while processing Reddit submission %s from r/%s",
                    getattr(submission, "id", "unknown"),
                    subreddit_name,
                )
    except prawcore_exceptions.PrawcoreException:
        logger.exception("Failed to fetch posts from r/%s", subreddit_name)
        return

    logger.info(
        "Reddit ingestion complete for r/%s: fetched=%s new=%s duplicates=%s",
        subreddit_name,
        fetched_count,
        new_count,
        fetched_count - new_count,
    )


def run() -> None:
    """Run Reddit ingestion across all configured subreddits."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    reddit = get_reddit_client()
    for subreddit_name in SUBREDDITS:
        ingest_subreddit(reddit, subreddit_name)


if __name__ == "__main__":
    run()
