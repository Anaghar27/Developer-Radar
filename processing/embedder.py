"""Embedding generation for developer sentiment posts."""

import logging

from sentence_transformers import SentenceTransformer

from storage import db_client


logger = logging.getLogger(__name__)
MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)


def _build_text(post: dict) -> str:
    """Build the text payload used for embedding a post."""
    title = post.get("title", "") or ""
    body = post.get("body", "") or ""
    return f"{title} {body}".strip()


def embed_post(post: dict) -> list[float]:
    """Encode a single post into an embedding vector and return it as a list."""
    text = _build_text(post)
    vector = model.encode(text)
    return vector.tolist()


def embed_batch(posts: list[dict]) -> list[tuple[str, list[float]]]:
    """Encode a batch of posts in one model call and return (post_id, vector) pairs."""
    valid_posts = []
    texts = []
    for post in posts:
        title = post.get("title", "") or ""
        body = post.get("body", "") or ""
        if not title and not body:
            logger.warning("Skipping embedding for post with empty title and body: %s", post["id"])
            continue
        valid_posts.append(post)
        texts.append(_build_text(post))

    if not valid_posts:
        return []

    vectors = model.encode(texts)
    return [(post["id"], vector.tolist()) for post, vector in zip(valid_posts, vectors)]


def run_embeddings(limit: int = 100, ingest_batch_id: str | None = None):
    """Generate embeddings for posts that do not yet have stored vectors."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if ingest_batch_id is None:
        raise ValueError("run_embeddings requires ingest_batch_id for batch-scoped embedding")

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

    embedded_count = 0
    for post_id, vector in embed_batch(posts_to_embed):
        db_client.insert_embedding(post_id, vector)
        embedded_count += 1

    logger.info(
        "Embedding run complete: fetched=%s already_embedded=%s newly_embedded=%s",
        total_fetched,
        already_embedded,
        embedded_count,
    )


if __name__ == "__main__":
    run_embeddings()
