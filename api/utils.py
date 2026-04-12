import os

import duckdb


def duckdb_available() -> bool:
    """
    Check if DuckDB warehouse file exists.
    Only use this guard in endpoints that query DuckDB marts or views.
    Do NOT use in endpoints that query PostgreSQL directly.

    DuckDB endpoints: /posts, /trends, /tools/compare, /community/divergence
    PostgreSQL endpoints: /alerts, /health, /auth/*, /cache/*
    """
    path = os.getenv("DBT_DUCKDB_PATH", "transform/developer_radar.duckdb")
    return os.path.exists(path)


def connect_duckdb_with_postgres(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Open DuckDB and attach the live PostgreSQL catalog as `pg`.

    Some dbt models queried by the API are backed by DuckDB views that reference
    the attached Postgres source catalog. Those queries fail unless the API
    session recreates the `pg` attachment before reading.
    """
    duckdb_path = os.getenv("DBT_DUCKDB_PATH", "transform/developer_radar.duckdb")
    conn = duckdb.connect(duckdb_path, read_only=False)
    conn.execute("INSTALL postgres_scanner;")
    conn.execute("LOAD postgres_scanner;")
    pg_conn_str = (
        f"dbname={os.getenv('POSTGRES_DB', 'developer_radar')} "
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"user={os.getenv('POSTGRES_USER', 'postgres')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'postgres')}"
    )
    try:
        conn.execute("DETACH pg")
    except Exception:
        pass
    conn.execute(f"ATTACH '{pg_conn_str}' AS pg (TYPE postgres, READ_ONLY)")
    return conn
