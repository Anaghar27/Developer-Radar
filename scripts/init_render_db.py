"""
Initialize the Render PostgreSQL database with the full schema.
Run once after creating a Render PostgreSQL instance.

Usage:
    python scripts/init_render_db.py
"""
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def init_db():
    print(f"Connecting to PostgreSQL at {os.getenv('POSTGRES_HOST')}...")
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    with conn.cursor() as cur:
        # Enable pgvector
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()
        print("pgvector extension enabled")

        # Run schema
        schema_path = os.path.join(os.path.dirname(__file__), "..", "storage", "schema.sql")
        with open(schema_path) as f:
            schema_sql = f.read()
        cur.execute(schema_sql)
        conn.commit()
        print("Schema applied successfully")

        # Verify tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cur.fetchall()]
        print(f"Tables present: {tables}")
        assert len(tables) >= 9, f"Expected at least 9 tables, got {len(tables)}: {tables}"

        # Verify 1536-dim vector column
        cur.execute("""
            SELECT udt_name FROM information_schema.columns
            WHERE table_name = 'post_embeddings'
            AND column_name = 'embedding';
        """)
        row = cur.fetchone()
        assert row is not None, "post_embeddings.embedding column not found"
        print("post_embeddings.embedding column verified")

    conn.close()
    print("Database initialization complete")


if __name__ == "__main__":
    init_db()
