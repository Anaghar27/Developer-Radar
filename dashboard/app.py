import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="DevPulse",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.api_client import login, register  # noqa: E402

# ── Auth gate ─────────────────────────────────────────────────────────────────

def show_login():
    st.title("📡 DevPulse")
    st.caption("Real-Time Developer Sentiment Intelligence")
    st.divider()

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
            if submitted:
                if login(email, password):
                    st.rerun()

    with tab_register:
        with st.form("register_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Register", use_container_width=True)
            if submitted:
                if register(email, password):
                    st.success("Registered! Please log in.")


# ── Main app ──────────────────────────────────────────────────────────────────

def show_dashboard():
    from dashboard.tabs import (
        community_comparison,
        intelligence_reports,
        live_feed,
        tool_tracker,
        trends,
    )

    with st.sidebar:
        st.title("📡 DevPulse")
        st.caption(f"Logged in as {st.session_state.get('email', '')}")
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔴 Live Feed",
        "📈 Trends",
        "⚔️ Community Comparison",
        "🛠️ Tool Tracker",
        "🧠 Intelligence Reports",
    ])

    with tab1:
        live_feed.render()
    with tab2:
        trends.render()
    with tab3:
        community_comparison.render()
    with tab4:
        tool_tracker.render()
    with tab5:
        intelligence_reports.render()


# ── Entry point ───────────────────────────────────────────────────────────────

if "token" not in st.session_state:
    show_login()
else:
    show_dashboard()
