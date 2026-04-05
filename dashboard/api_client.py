import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def get_token() -> str | None:
    """Get JWT token from Streamlit session state."""
    return st.session_state.get("token")


def api_get(endpoint: str, params: dict = None) -> dict | None:
    """
    Authenticated GET request to FastAPI.
    Returns response JSON or None on failure.
    """
    token = get_token()
    if not token:
        st.error("Not authenticated. Please log in.")
        return None
    try:
        response = requests.get(
            f"{API_BASE_URL}{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        if response.status_code == 401:
            st.session_state.pop("token", None)
            st.query_params.clear()
            st.error("Session expired. Please log in again.")
            st.rerun()
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API. Is the server running?")
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(endpoint: str, payload: dict) -> dict | None:
    """
    Authenticated POST request to FastAPI.
    Returns response JSON or None on failure.
    """
    token = get_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.post(
            f"{API_BASE_URL}{endpoint}",
            headers=headers,
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def login(email: str, password: str) -> bool:
    """Login and store JWT token in session state."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/token",
            json={"email": email, "password": password},
            timeout=10,
        )
        if response.status_code == 200:
            st.session_state["token"] = response.json()["access_token"]
            st.session_state["email"] = email
            return True
        st.error("Invalid email or password.")
        return False
    except Exception as e:
        st.error(f"Login failed: {e}")
        return False


def forgot_password(email: str) -> dict | None:
    """Request a password reset token. Returns response dict or None on error."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/forgot-password",
            json={"email": email},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None


def verify_reset_otp(token: str) -> dict:
    """Check whether a reset OTP is valid without consuming it."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/verify-otp",
            json={"token": token},
            timeout=10,
        )
        if response.status_code == 200:
            body = response.json()
            return {
                "valid": bool(body.get("valid", False)),
                "message": body.get("message", "OTP verification failed."),
            }
        if response.status_code == 404:
            return {
                "valid": False,
                "message": "OTP verification is unavailable on the API. Restart or redeploy the backend.",
            }
        try:
            body = response.json()
            message = body.get("detail") or body.get("message") or "OTP verification failed."
        except Exception:
            message = "OTP verification failed."
        return {"valid": False, "message": message}
    except Exception as e:
        return {"valid": False, "message": f"OTP verification failed: {e}"}


def reset_password(token: str, new_password: str) -> bool:
    """Submit a reset token and new password. Returns True on success."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/reset-password",
            json={"token": token, "new_password": new_password},
            timeout=10,
        )
        if response.status_code == 200:
            return True
        st.error(response.json().get("detail", "Reset failed."))
        return False
    except Exception as e:
        st.error(f"Reset failed: {e}")
        return False


def register(email: str, password: str) -> dict | None:
    """Register a new user. Returns response dict (may include verify_token in dev mode) or None on error."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/register",
            json={"email": email, "password": password},
            timeout=10,
        )
        if response.status_code == 201:
            return response.json()
        try:
            detail = response.json().get("detail", "Registration failed.")
        except Exception:
            detail = f"Registration failed (HTTP {response.status_code})."
        if isinstance(detail, list):
            detail = "; ".join(e.get("msg", str(e)) for e in detail)
        st.error(detail)
        return None
    except Exception as e:
        st.error(f"Registration failed: {e}")
        return None


def verify_email(token: str) -> bool:
    """Submit an email verification OTP. Returns True on success."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/verify-email",
            json={"token": token},
            timeout=10,
        )
        if response.status_code == 200:
            return True
        st.error(response.json().get("detail", "Verification failed."))
        return False
    except Exception as e:
        st.error(f"Verification failed: {e}")
        return False
