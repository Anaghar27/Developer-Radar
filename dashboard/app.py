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

from dashboard.api_client import forgot_password, login, register, reset_password  # noqa: E402

# ── Auth gate ─────────────────────────────────────────────────────────────────

def show_login():
    st.title("📡 DevPulse")
    st.caption("Real-Time Developer Sentiment Intelligence")
    st.divider()

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        # Toggle between login form and reset password flow
        if "show_reset" not in st.session_state:
            st.session_state.show_reset = False

        if not st.session_state.show_reset:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", use_container_width=True)
                if submitted:
                    if login(email, password):
                        st.rerun()
            if st.button("Forgot password?", type="tertiary"):
                st.session_state.show_reset = True
                st.rerun()

        else:
            # Step 1 — request token
            if not st.session_state.get("reset_token_sent"):
                st.markdown("**Reset your password**")
                with st.form("forgot_form"):
                    email = st.text_input("Enter your email address")
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Send OTP", use_container_width=True)
                    with col2:
                        cancel = st.form_submit_button("Back to Login", use_container_width=True)
                    if cancel:
                        st.session_state.show_reset = False
                        st.rerun()
                    if submitted and email:
                        data = forgot_password(email)
                        if data is not None:
                            st.session_state.reset_token_sent = True
                            st.session_state.reset_dev_token = data.get("reset_token")
                            st.session_state.reset_email = email
                            st.rerun()

            # Step 2 — set new password
            else:
                st.markdown("**Set a new password**")
                sent_to = st.session_state.get("reset_email", "your registered email")
                st.success(f"OTP sent to **{sent_to}**. It expires in 5 minutes.")

                with st.form("reset_form"):
                    # Auto-fill token when returned directly (no SMTP); hidden but editable
                    default_token = st.session_state.get("reset_dev_token", "")
                    token = st.text_input("Enter OTP", value=default_token)
                    new_password = st.text_input("New password (min 8 characters)", type="password")
                    confirm = st.text_input("Confirm new password", type="password")
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Reset Password", use_container_width=True)
                    with col2:
                        cancel = st.form_submit_button("Back to Login", use_container_width=True)
                    if cancel:
                        st.session_state.show_reset = False
                        st.session_state.reset_token_sent = False
                        st.session_state.reset_dev_token = None
                        st.session_state.reset_email = None
                        st.rerun()
                    if submitted:
                        if not token or not new_password:
                            st.error("OTP and new password are required.")
                        elif new_password != confirm:
                            st.error("Passwords do not match.")
                        elif len(new_password) < 8:
                            st.error("Password must be at least 8 characters.")
                        elif reset_password(token, new_password):
                            st.success("Password updated! Please log in.")
                            st.session_state.show_reset = False
                            st.session_state.reset_token_sent = False
                            st.session_state.reset_dev_token = None

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
