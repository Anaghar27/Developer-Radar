import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from api.main import app


@pytest.fixture
def client():
    """TestClient with mocked Redis and db pool — no live services needed."""
    mock_pool = AsyncMock()
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_pool.fetchrow = AsyncMock(return_value=None)
    mock_pool.close = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.delete = AsyncMock(return_value=0)
    mock_redis.aclose = AsyncMock()

    async def fake_init_redis(app):
        app.state.redis = mock_redis

    async def fake_close_redis(app):
        pass

    with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)), \
         patch("api.cache.redis_client.init_redis", side_effect=fake_init_redis), \
         patch("api.cache.redis_client.close_redis", side_effect=fake_close_redis):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture
def auth_token(client):
    """Register a test user and return a valid JWT token."""
    with patch("api.auth.router.fetch_user_by_email", return_value=None), \
         patch("api.auth.router.insert_user", return_value=1):
        client.post("/auth/register", json={
            "email": "testuser@devpulse.com",
            "password": "testpass123",
        })

    with patch("api.auth.router.fetch_user_by_email", return_value={
        "id": 1,
        "email": "testuser@devpulse.com",
        "hashed_password": "$2b$12$placeholder_hash",
        "is_active": True,
    }), patch("api.auth.router.verify_password", return_value=True):
        response = client.post("/auth/token", json={
            "email": "testuser@devpulse.com",
            "password": "testpass123",
        })
    return response.json()["access_token"]


# ── Liveness ──────────────────────────────────────────────────────────────────

def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    with patch("api.routes.health.fetch_latest_pipeline_run", return_value=None):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_register_user(client):
    with patch("api.auth.router.fetch_user_by_email", return_value=None), \
         patch("api.auth.router.insert_user", return_value=1):
        response = client.post("/auth/register", json={
            "email": "newuser@devpulse.com",
            "password": "securepass123",
        })
    assert response.status_code == 201
    assert "api_key" in response.json()


def test_login(client):
    with patch("api.auth.router.fetch_user_by_email", return_value={
        "id": 1,
        "email": "test@devpulse.com",
        "hashed_password": "hashed",
        "is_active": True,
    }), patch("api.auth.router.verify_password", return_value=True):
        response = client.post("/auth/token", json={
            "email": "test@devpulse.com",
            "password": "testpass123",
        })
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password(client):
    with patch("api.auth.router.fetch_user_by_email", return_value={
        "id": 1,
        "email": "test@devpulse.com",
        "hashed_password": "hashed",
        "is_active": True,
    }), patch("api.auth.router.verify_password", return_value=False):
        response = client.post("/auth/token", json={
            "email": "test@devpulse.com",
            "password": "wrongpass",
        })
    assert response.status_code == 401


# ── Posts ─────────────────────────────────────────────────────────────────────

def test_posts_requires_auth(client):
    # No Bearer token → get_current_user raises 401
    response = client.get("/posts")
    assert response.status_code == 401


def test_posts_with_auth(client, auth_token):
    # posts.py queries PostgreSQL via app.state.db_pool (asyncpg), not DuckDB.
    # The mock_pool.fetch already returns [] from the client fixture.
    response = client.get("/posts", headers={"Authorization": f"Bearer {auth_token}"})
    assert response.status_code == 200
    body = response.json()
    assert "posts" in body
    assert "total" in body
    assert body["total"] == 0


# ── Trends ────────────────────────────────────────────────────────────────────

def test_trends_with_auth(client, auth_token):
    with patch("api.routes.trends.duckdb.connect") as mock_conn:
        mock_conn.return_value.execute.return_value.fetchall.return_value = []
        mock_conn.return_value.close = MagicMock()
        response = client.get("/trends", headers={"Authorization": f"Bearer {auth_token}"})
    assert response.status_code == 200
    assert "data" in response.json()


# ── Cache ─────────────────────────────────────────────────────────────────────

def test_cache_invalidate_requires_api_key(client):
    # No X-API-Key header → require_api_key raises 403
    response = client.post("/cache/invalidate")
    assert response.status_code == 403
