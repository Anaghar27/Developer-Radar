"""Tests for password reset: email utility and db helper functions."""

import hashlib
from unittest.mock import MagicMock, patch


# ── Email utility ─────────────────────────────────────────────────────────────

def test_send_reset_email_no_smtp_returns_false():
    """Returns False and logs token when SMTP_HOST is not configured."""
    from api.auth.email import send_reset_email

    with patch.dict("os.environ", {}, clear=True):
        result = send_reset_email("user@example.com", "test-token-123")

    assert result is False


def test_send_reset_email_smtp_configured_returns_true():
    """Returns True and calls smtplib when SMTP is configured."""
    from api.auth.email import send_reset_email

    mock_smtp = MagicMock()
    mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp.__exit__ = MagicMock(return_value=False)

    smtp_env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "sender@example.com",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM": "sender@example.com",
    }
    with patch.dict("os.environ", smtp_env), \
         patch("smtplib.SMTP", return_value=mock_smtp):
        result = send_reset_email("user@example.com", "test-token-123")

    assert result is True


def test_send_reset_email_smtp_connection_failure_returns_false():
    """Returns False when SMTP connection raises an exception."""
    from api.auth.email import send_reset_email

    smtp_env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587"}
    with patch.dict("os.environ", smtp_env), \
         patch("smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
        result = send_reset_email("user@example.com", "test-token-123")

    assert result is False


def test_send_reset_email_empty_host_returns_false():
    """SMTP_HOST set to empty string is treated as not configured."""
    from api.auth.email import send_reset_email

    with patch.dict("os.environ", {"SMTP_HOST": ""}):
        result = send_reset_email("user@example.com", "token")

    assert result is False


# ── Token hashing ─────────────────────────────────────────────────────────────

def test_forgot_password_hashes_otp_before_storing():
    """The raw OTP is SHA-256 hashed before being passed to create_reset_token."""
    captured = {}

    def capture_create(user_id, token_hash, expires_at):
        captured["token_hash"] = token_hash
        captured["user_id"] = user_id

    # Fix randbelow to always return 4, so OTP = "444444"
    with patch("api.auth.router.fetch_user_by_email", return_value={
        "id": 7, "email": "u@x.com", "is_active": True,
    }), patch("api.auth.router.secrets.randbelow", return_value=4), \
       patch("api.auth.router.create_reset_token", side_effect=capture_create), \
       patch("api.auth.router.send_reset_email", return_value=False):

        from unittest.mock import AsyncMock
        from fastapi.testclient import TestClient
        from api.main import app

        mock_pool = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.keys = AsyncMock(return_value=[])
        mock_redis.delete = AsyncMock(return_value=0)

        async def fake_init(app): app.state.redis = mock_redis
        async def fake_close(app): pass

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)), \
             patch("api.cache.redis_client.init_redis", side_effect=fake_init), \
             patch("api.cache.redis_client.close_redis", side_effect=fake_close):
            with TestClient(app) as c:
                c.post("/auth/forgot-password", json={"email": "u@x.com"})

    expected_hash = hashlib.sha256("444444".encode()).hexdigest()
    assert captured.get("token_hash") == expected_hash
    assert captured.get("user_id") == 7


# ── DB helper logic (mocked psycopg2) ─────────────────────────────────────────

def test_create_reset_token_deletes_existing_then_inserts():
    """create_reset_token deletes any existing unused token before inserting a new one."""
    from storage.db_client import create_reset_token

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    with patch("storage.db_client.get_connection", return_value=mock_conn):
        create_reset_token(user_id=1, token_hash="abc123", expires_at="2099-01-01")

    assert mock_cursor.execute.call_count == 2
    first_sql = mock_cursor.execute.call_args_list[0][0][0]
    assert "DELETE" in first_sql.upper()
    second_sql = mock_cursor.execute.call_args_list[1][0][0]
    assert "INSERT" in second_sql.upper()


def test_fetch_reset_token_returns_none_when_not_found():
    """fetch_reset_token returns None when no valid token matches."""
    from storage.db_client import fetch_reset_token

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = None
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    with patch("storage.db_client.get_connection", return_value=mock_conn):
        result = fetch_reset_token("nonexistent-hash")

    assert result is None


def test_fetch_reset_token_returns_dict_when_found():
    """fetch_reset_token returns a dict when a valid token record exists."""
    from storage.db_client import fetch_reset_token

    mock_row = {"id": 5, "user_id": 3, "token_hash": "hash123", "expires_at": None, "used_at": None}
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = mock_row
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    with patch("storage.db_client.get_connection", return_value=mock_conn):
        result = fetch_reset_token("hash123")

    assert result == mock_row
    assert result["user_id"] == 3


def test_consume_reset_token_sets_used_at():
    """consume_reset_token runs an UPDATE that sets used_at."""
    from storage.db_client import consume_reset_token

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    with patch("storage.db_client.get_connection", return_value=mock_conn):
        consume_reset_token(token_id=42)

    sql = mock_cursor.execute.call_args[0][0]
    assert "used_at" in sql.lower()
    assert mock_cursor.execute.call_args[0][1] == (42,)


def test_update_user_password_updates_correct_user():
    """update_user_password passes user_id and new hash in the right order."""
    from storage.db_client import update_user_password

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    with patch("storage.db_client.get_connection", return_value=mock_conn):
        update_user_password(user_id=3, hashed_password="$2b$newhash")

    sql, params = mock_cursor.execute.call_args[0]
    assert "UPDATE" in sql.upper() and "users" in sql
    assert "$2b$newhash" in params
    assert 3 in params
