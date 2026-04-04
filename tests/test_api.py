from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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
         patch("api.auth.router.insert_user", return_value=1), \
         patch("api.auth.router.create_verification_token"), \
         patch("api.auth.router.send_verification_email", return_value=False):
        response = client.post("/auth/register", json={
            "email": "newuser@devpulse.com",
            "password": "Securepass123!",
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


# ── Password reset ─────────────────────────────────────────────────────────────

def test_forgot_password_dev_mode_returns_token(client):
    """When SMTP is not configured, reset token is returned directly in the response."""
    with patch("api.auth.router.fetch_user_by_email", return_value={
        "id": 1, "email": "user@devpulse.com", "is_active": True,
    }), patch("api.auth.router.create_reset_token"), \
       patch("api.auth.router.send_reset_email", return_value=False):
        response = client.post("/auth/forgot-password", json={"email": "user@devpulse.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["reset_token"] is not None
    assert len(body["reset_token"]) > 0


def test_forgot_password_smtp_configured_no_token_in_response(client):
    """When SMTP is configured and email is sent, reset token is NOT returned in the response."""
    with patch("api.auth.router.fetch_user_by_email", return_value={
        "id": 1, "email": "user@devpulse.com", "is_active": True,
    }), patch("api.auth.router.create_reset_token"), \
       patch("api.auth.router.send_reset_email", return_value=True):
        response = client.post("/auth/forgot-password", json={"email": "user@devpulse.com"})

    assert response.status_code == 200
    assert response.json().get("reset_token") is None
    assert "message" in response.json()


def test_forgot_password_unknown_email_returns_200(client):
    """Unknown email still returns 200 — never reveal whether an email is registered."""
    with patch("api.auth.router.fetch_user_by_email", return_value=None):
        response = client.post("/auth/forgot-password", json={"email": "ghost@nowhere.com"})

    assert response.status_code == 200
    assert response.json().get("reset_token") is None


def test_forgot_password_inactive_account_returns_200(client):
    """Inactive account behaves the same as unknown email — no token, no error."""
    with patch("api.auth.router.fetch_user_by_email", return_value={
        "id": 2, "email": "inactive@devpulse.com", "is_active": False,
    }):
        response = client.post("/auth/forgot-password", json={"email": "inactive@devpulse.com"})

    assert response.status_code == 200
    assert response.json().get("reset_token") is None


def test_reset_password_success(client):
    """Valid token and matching passwords → 200 and password is updated."""
    with patch("api.auth.router.fetch_reset_token", return_value={"id": 10, "user_id": 1}), \
         patch("api.auth.router.update_user_password") as mock_update, \
         patch("api.auth.router.consume_reset_token") as mock_consume:
        response = client.post("/auth/reset-password", json={
            "token": "valid-token-abc",
            "new_password": "newpass123",
        })

    assert response.status_code == 200
    assert "successfully" in response.json()["message"].lower()
    mock_update.assert_called_once_with(1, mock_update.call_args[0][1])
    mock_consume.assert_called_once_with(10)


def test_reset_password_invalid_token(client):
    """Invalid or expired token → 400."""
    with patch("api.auth.router.fetch_reset_token", return_value=None):
        response = client.post("/auth/reset-password", json={
            "token": "bad-token",
            "new_password": "newpass123",
        })

    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_reset_password_too_short(client):
    """Password shorter than 8 characters → 422 validation error."""
    response = client.post("/auth/reset-password", json={
        "token": "some-token",
        "new_password": "short",
    })
    assert response.status_code == 422


def test_reset_password_consumes_token_only_once(client):
    """consume_reset_token is called exactly once per successful reset."""
    with patch("api.auth.router.fetch_reset_token", return_value={"id": 99, "user_id": 5}), \
         patch("api.auth.router.update_user_password"), \
         patch("api.auth.router.consume_reset_token") as mock_consume:
        client.post("/auth/reset-password", json={
            "token": "one-time-token",
            "new_password": "securepass99",
        })

    mock_consume.assert_called_once_with(99)
