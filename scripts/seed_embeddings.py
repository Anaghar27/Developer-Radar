"""
Embed the seeded demo posts using OpenAI text-embedding-3-small.
Run after seed_demo_data.py.

Usage:
    python -m scripts.seed_embeddings
"""
import logging
import sys
import os

# Ensure project root is on sys.path when run as a plain script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")

from processing.embedder import run_embeddings  # noqa: E402

if __name__ == "__main__":
    print("Embedding demo posts with OpenAI text-embedding-3-small...")
    run_embeddings(limit=500, ingest_batch_id="demo_seed_batch")
    print("Embedding run complete")
