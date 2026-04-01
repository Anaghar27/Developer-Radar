"""Pytest configuration for the developer sentiment intelligence pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Local test runs happen outside Docker, so the Compose service hostname
# is not resolvable from the host shell.
if os.environ.get("POSTGRES_HOST") == "postgres" and not Path("/.dockerenv").exists():
    os.environ["POSTGRES_HOST"] = "localhost"
