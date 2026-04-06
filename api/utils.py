import os


def duckdb_available() -> bool:
    """Return True if the DuckDB mart file exists and is readable."""
    path = os.getenv("DBT_DUCKDB_PATH", "transform/devpulse.duckdb")
    return os.path.isfile(path)
