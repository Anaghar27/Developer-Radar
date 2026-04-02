"""
Seed demo posts for the live Render deployment.
Safe to run multiple times — uses ON CONFLICT DO NOTHING.

Usage:
    python scripts/seed_demo_data.py
"""
import os
import random
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv

load_dotenv()

BATCH_ID = "demo_seed_batch"

SAMPLE_POSTS = [
    (
        "reddit",
        "PyTorch 2.0 compile mode is a game changer for training speed",
        "We benchmarked PyTorch 2.0 compile vs eager mode and saw 40% speedup on transformer models.",
        "https://reddit.com/r/MachineLearning/demo1",
        342,
    ),
    (
        "hackernews",
        "Ask HN: Is Rust worth learning for ML infrastructure?",
        "Considering rewriting our data pipeline in Rust. Looking for experiences from people who made the switch.",
        "https://news.ycombinator.com/item?id=demo2",
        187,
    ),
    (
        "reddit",
        "Llama 3 beats GPT-3.5 on our internal benchmarks",
        "After extensive testing Llama 3 8B is now our default for classification tasks. Cost savings are significant.",
        "https://reddit.com/r/LocalLLaMA/demo3",
        521,
    ),
    (
        "reddit",
        "dbt + DuckDB is the best local analytics stack I have used",
        "Replaced our Spark setup with dbt + DuckDB for local development. 10x faster iteration, zero infrastructure.",
        "https://reddit.com/r/datascience/demo4",
        298,
    ),
    (
        "hackernews",
        "Kafka is overkill for most startups",
        "We spent 6 months building Kafka infrastructure and then replaced it with Postgres LISTEN/NOTIFY.",
        "https://news.ycombinator.com/item?id=demo5",
        412,
    ),
    (
        "reddit",
        "Airflow vs Prefect in 2024 — our team's experience after 2 years",
        "After 2 years on Airflow and 6 months on Prefect here is an honest comparison of both platforms.",
        "https://reddit.com/r/mlops/demo6",
        267,
    ),
    (
        "reddit",
        "FastAPI async performance is genuinely impressive",
        "Migrated from Flask to FastAPI and our p95 latency dropped from 120ms to 18ms on cached endpoints.",
        "https://reddit.com/r/Python/demo7",
        445,
    ),
    (
        "hackernews",
        "The problem with vector databases",
        "We tried 4 different vector DBs and ended up back on pgvector. Simpler, cheaper, good enough.",
        "https://news.ycombinator.com/item?id=demo8",
        334,
    ),
    (
        "reddit",
        "Transformer attention is all you need — 6 years later",
        "Revisiting the original attention paper and how it shaped modern LLMs. The architecture is still dominant.",
        "https://reddit.com/r/MachineLearning/demo9",
        612,
    ),
    (
        "reddit",
        "Docker Compose vs Kubernetes for small teams",
        "If you have fewer than 5 services just use Docker Compose. Kubernetes is not worth the complexity.",
        "https://reddit.com/r/devops/demo10",
        389,
    ),
]

SENTIMENTS = ["positive", "negative", "neutral"]
EMOTIONS = ["excitement", "frustration", "curiosity", "satisfaction", "neutral"]
TOPICS = ["machine_learning", "devtools", "career", "open_source", "hardware", "general"]
TOOLS = ["pytorch", "tensorflow", "kafka", "dbt", "airflow", "fastapi", "rust", None]


def seed():
    print(f"Connecting to PostgreSQL at {os.getenv('POSTGRES_HOST')}...")
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    now = datetime.now(timezone.utc)
    inserted_raw = 0
    inserted_processed = 0

    with conn.cursor() as cur:
        # Ensure ingest_batch_id column exists (added dynamically by db_client)
        cur.execute("ALTER TABLE raw_posts ADD COLUMN IF NOT EXISTS ingest_batch_id TEXT;")
        conn.commit()

        for i, (source, title, body, url, score) in enumerate(SAMPLE_POSTS):
            post_id = f"demo_{i + 1:03d}"
            created_at = now - timedelta(days=random.randint(0, 14))

            cur.execute(
                """
                INSERT INTO raw_posts (id, source, title, body, url, score, created_at, ingest_batch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (post_id, source, title, body, url, score, created_at, BATCH_ID),
            )
            if cur.rowcount > 0:
                inserted_raw += 1

            sentiment = random.choice(SENTIMENTS)
            cur.execute(
                """
                INSERT INTO processed_posts
                    (post_id, sentiment, emotion, topic,
                     tool_mentioned, controversy_score, reasoning, processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (post_id) DO NOTHING
                """,
                (
                    post_id,
                    sentiment,
                    random.choice(EMOTIONS),
                    random.choice(TOPICS),
                    random.choice(TOOLS),
                    random.randint(0, 5),
                    f"Demo seed — sentiment: {sentiment}",
                ),
            )
            if cur.rowcount > 0:
                inserted_processed += 1

        conn.commit()

    conn.close()
    print(f"Seeded {inserted_raw} raw posts, {inserted_processed} processed posts")
    print("Run 'python scripts/seed_embeddings.py' next to embed the demo posts")


if __name__ == "__main__":
    seed()
