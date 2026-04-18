"""Pytest configuration for the developer sentiment intelligence pipeline."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from api.auth.jwt import create_access_token

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Local test runs happen outside Docker, so the Compose service hostname
# is not resolvable from the host shell.
if os.environ.get("POSTGRES_HOST") == "postgres" and not Path("/.dockerenv").exists():
    os.environ["POSTGRES_HOST"] = "localhost"


@pytest.fixture
def auth_headers_non_admin():
    token = create_access_token({"sub": "user@test.com", "user_id": 1, "is_admin": False})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_admin():
    token = create_access_token({"sub": "admin@test.com", "user_id": 2, "is_admin": True})
    return {"Authorization": f"Bearer {token}"}
