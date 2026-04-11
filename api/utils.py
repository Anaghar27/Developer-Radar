import os


def duckdb_available() -> bool:
    """
    Check if DuckDB warehouse file exists.
    Only use this guard in endpoints that query DuckDB marts or views.
    Do NOT use in endpoints that query PostgreSQL directly.

    DuckDB endpoints: /posts, /trends, /tools/compare, /community/divergence
    PostgreSQL endpoints: /alerts, /health, /auth/*, /cache/*
    """
    path = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")
    return os.path.exists(path)
