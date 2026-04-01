import os
from typing import Optional

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


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


def register(email: str, password: str) -> bool:
    """Register a new user."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/register",
            json={"email": email, "password": password},
            timeout=10,
        )
        if response.status_code == 201:
            return True
        st.error(response.json().get("detail", "Registration failed."))
        return False
    except Exception as e:
        st.error(f"Registration failed: {e}")
        return False
