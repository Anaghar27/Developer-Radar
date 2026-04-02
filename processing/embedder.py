"""Embedding generation for developer sentiment posts."""

import logging

from processing.llm_client import get_embedding as _get_embedding
from storage import db_client
from storage.db_client import insert_embedding

logger = logging.getLogger(__name__)


def get_embedding(text: str) -> list[float]:
    """
    Get 1536-dim embedding via unified LLM client (OpenAI text-embedding-3-small).
    """
    return _get_embedding(text)


def embed_post(post_id: str, title: str, body: str) -> list[float]:
    """
    Embed a single post using OpenAI text-embedding-3-small.
    Combines title + body for richer semantic representation.
    Returns 1536-dim vector.
    """
    text = f"{title} {body or ''}".strip()
    embedding = get_embedding(text)
    insert_embedding(post_id=post_id, embedding=embedding)
    return embedding


def embed_batch(posts: list[dict]) -> int:
    """
    Embed a batch of posts using OpenAI text-embedding-3-small.
    Returns number of posts successfully embedded.
    """
    count = 0
    for post in posts:
        post_id = post.get("id") or post.get("post_id")
        title = post.get("title", "")
        body = post.get("body", "") or ""
        try:
            embed_post(post_id=post_id, title=title, body=body)
            count += 1
            logging.info(f"Embedded post {post_id}")
        except Exception as e:
            logging.error(f"Failed to embed post {post_id}: {e}")
    return count


def run_embeddings(limit: int = 100, ingest_batch_id: str | None = None):
    """Generate embeddings for posts that do not yet have stored vectors."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    posts = db_client.fetch_batch_posts_without_embeddings(
        ingest_batch_id=ingest_batch_id,
        limit=limit,
    )
    total_fetched = len(posts)
    posts_to_embed = []
    already_embedded = 0

    for post in posts:
        if db_client.embedding_exists(post["id"]):
            already_embedded += 1
            continue
        posts_to_embed.append(post)

    embedded_count = embed_batch(posts_to_embed)

    logger.info(
        "Embedding run complete: fetched=%s already_embedded=%s newly_embedded=%s",
        total_fetched,
        already_embedded,
        embedded_count,
    )


if __name__ == "__main__":
    run_embeddings()
