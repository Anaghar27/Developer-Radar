"""DevPulse – main Streamlit entry-point (Silver Ghost theme: mono dark + light)."""
import base64
import os
import sys
from urllib.parse import quote, unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import streamlit.components.v1 as stcomponents
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="DevPulse",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from dashboard.api_client import forgot_password, login, register, reset_password, verify_email, verify_reset_otp  # noqa: E402, I001

_COOKIE_TOKEN = "dp_session_token"
_COOKIE_EMAIL = "dp_session_email"
_COOKIE_TTL_DAYS = 7
_SPECIAL_PASSWORD_CHARS = set("!@#$%^&*()_+-=[]{}|;':\",./<>?")


def _write_session_cookies(token: str, email: str) -> None:
    """Set session cookies via a same-origin iframe script (no external library)."""
    max_age = _COOKIE_TTL_DAYS * 24 * 60 * 60
    safe_token = quote(token, safe="")
    safe_email = quote(email, safe="")
    stcomponents.html(
        f"""<script>
        var a = "max-age={max_age}; path=/; SameSite=Lax";
        document.cookie = "{_COOKIE_TOKEN}={safe_token}; " + a;
        document.cookie = "{_COOKIE_EMAIL}={safe_email}; " + a;
        </script>""",
        height=0,
    )


def _clear_session_cookies() -> None:
    """Expire auth cookies via a same-origin iframe script."""
    stcomponents.html(
        f"""<script>
        var exp = "expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax";
        document.cookie = "{_COOKIE_TOKEN}=; " + exp;
        document.cookie = "{_COOKIE_EMAIL}=; " + exp;
        </script>""",
        height=0,
    )


def _password_requirements(password: str) -> list[tuple[bool, str]]:
    return [
        (len(password) >= 8, "At least 8 characters"),
        (any(c.isupper() for c in password), "One uppercase letter"),
        (any(c.isdigit() for c in password), "One number"),
        (any(c in _SPECIAL_PASSWORD_CHARS for c in password), "One special character (!@# ...)"),
    ]


def _forgot_password_started(data: dict | None) -> bool:
    """Accept both the new API contract and the older generic success response."""
    if not data:
        return False
    if data.get("otp_sent") is True:
        return True
    if data.get("reset_token"):
        return True
    message = str(data.get("message", "")).lower()
    return "otp" in message and "sent" in message

# ══════════════════════════════════════════════════════════════════════════════
# THEME SYSTEM — "Silver Ghost" (Vercel mono: white on black / black on white)
# ══════════════════════════════════════════════════════════════════════════════

_DARK_VARS = """
:root {
  --bg:       #080808;
  --surf:     #111111;
  --surf2:    #1a1a1a;
  --card:     #1a1a1a;
  --border:   rgba(255,255,255,.09);
  --border-h: rgba(255,255,255,.30);

  --t1: #f0f0f0;
  --t2: #909090;
  --t3: #585858;
  --t4: #383838;

  --a:   #ffffff;
  --al:  #e0e0e0;
  --a2:  #c8c8c8;
  --a2l: #d8d8d8;

  --pos:  #5cd65c; --pos-b: rgba(92,214,92,.12);
  --neg:  #ff4444; --neg-b: rgba(255,68,68,.12);
  --neu:  #888888; --neu-b: rgba(136,136,136,.10);
  --wrn:  #e0a020; --wrn-b: rgba(224,160,32,.12);

  --grad:      linear-gradient(135deg, #ffffff 0%, #c8c8c8 100%);
  --grad-cta:  linear-gradient(135deg, #e8e8e8 0%, #b0b0b0 100%);
  --grad-soft: linear-gradient(135deg, rgba(255,255,255,.07), rgba(200,200,200,.04));

  --sh-sm: 0 2px 8px rgba(0,0,0,.6);
  --sh-md: 0 4px 24px rgba(0,0,0,.7);
  --sh-lg: 0 12px 48px rgba(0,0,0,.75);
  --glow:  0 0 24px rgba(255,255,255,.10);
  --glow2: 0 0 24px rgba(200,200,200,.08);

  --r-s: 8px;  --r-m: 14px;  --r-l: 22px;

  --glass-bg:   rgba(26,26,26,.82);
  --glass-blur: blur(16px);
  --glass-bord: 1px solid rgba(255,255,255,.07);

  /* Accent alpha helpers (used in shared CSS) */
  --a-focus:    rgba(255,255,255,.08);
  --a-tag-bg:   rgba(255,255,255,.07);
  --a-tag-bd:   rgba(255,255,255,.18);
  --a-btn-sh:   0 4px 18px rgba(255,255,255,.10);
  --a-btn-sh-h: 0 6px 28px rgba(255,255,255,.18);
  --a-hover:    rgba(255,255,255,.04);
  --a-tab-sh:   0 2px 12px rgba(255,255,255,.08);
  --a-scroll:   rgba(255,255,255,.22);
  --a-scroll-h: rgba(255,255,255,.42);
  --on-a:       #000000;
}
"""

_LIGHT_VARS = """
:root {
  --bg:       #f8f8f8;
  --surf:     #ffffff;
  --surf2:    #eeeeee;
  --card:     #ffffff;
  --border:   #d0d0d0;
  --border-h: #888888;

  --t1: #0a0a0a;
  --t2: #484848;
  --t3: #787878;
  --t4: #a8a8a8;

  --a:   #0a0a0a;
  --al:  #1a1a1a;
  --a2:  #303030;
  --a2l: #484848;

  --pos:  #1e8c1e; --pos-b: rgba(30,140,30,.09);
  --neg:  #cc0000; --neg-b: rgba(204,0,0,.09);
  --neu:  #787878; --neu-b: rgba(120,120,120,.08);
  --wrn:  #b06800; --wrn-b: rgba(176,104,0,.09);

  --grad:      linear-gradient(135deg, #0a0a0a 0%, #484848 100%);
  --grad-cta:  linear-gradient(135deg, #0a0a0a 0%, #303030 100%);
  --grad-soft: linear-gradient(135deg, rgba(0,0,0,.05), rgba(48,48,48,.03));

  --sh-sm: 0 1px 4px rgba(0,0,0,.10), 0 0 0 1px rgba(0,0,0,.05);
  --sh-md: 0 4px 16px rgba(0,0,0,.12), 0 2px 6px rgba(0,0,0,.07);
  --sh-lg: 0 10px 36px rgba(0,0,0,.14), 0 4px 14px rgba(0,0,0,.08);
  --glow:  0 0 20px rgba(0,0,0,.09);
  --glow2: 0 0 20px rgba(48,48,48,.07);

  --r-s: 8px;  --r-m: 14px;  --r-l: 22px;

  --glass-bg:   rgba(255,255,255,.96);
  --glass-blur: blur(0px);
  --glass-bord: 1.5px solid #d0d0d0;

  /* Accent alpha helpers */
  --a-focus:    rgba(0,0,0,.08);
  --a-tag-bg:   rgba(0,0,0,.05);
  --a-tag-bd:   rgba(0,0,0,.16);
  --a-btn-sh:   0 4px 18px rgba(0,0,0,.18);
  --a-btn-sh-h: 0 6px 28px rgba(0,0,0,.28);
  --a-hover:    rgba(0,0,0,.04);
  --a-tab-sh:   0 2px 12px rgba(0,0,0,.15);
  --a-scroll:   rgba(0,0,0,.22);
  --a-scroll-h: rgba(0,0,0,.42);
  --on-a:       #ffffff;
}
"""

_SHARED_CSS = """
/* ── Google Fonts ───────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Fira+Code:wght@400;500&display=swap');

/* ── Base reset ─────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded):not(.material-symbols-outlined):not(.material-icons) {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

#MainMenu, footer, [data-testid="stDeployButton"],
[data-testid="stDecoration"], [data-testid="stHeader"] {
  display: none !important; visibility: hidden !important;
}
[data-testid="InputInstructions"] { display: none !important; }

/* ── App backgrounds ────────────────────────────────────────────────────── */
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"], .main {
  background: var(--bg) !important;
  color: var(--t1) !important;
}
.block-container {
  padding-top: 1.5rem !important;
  padding-bottom: 4rem !important;
  max-width: 1400px !important;
}

/* Very subtle vignette — Ghost theme stays clean */
[data-testid="stApp"]::before {
  content: '';
  position: fixed; inset: 0;
  background:
    radial-gradient(ellipse at 20% 60%, rgba(255,255,255,.018) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 20%, rgba(255,255,255,.012) 0%, transparent 55%);
  pointer-events: none; z-index: 0;
}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--surf); }
::-webkit-scrollbar-thumb { background: var(--a-scroll); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--a-scroll-h); }

/* ── Inputs ─────────────────────────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea, .stNumberInput input {
  background: var(--surf2) !important;
  border: 1.5px solid var(--border) !important;
  border-radius: var(--r-s) !important;
  color: var(--t1) !important;
  font-size: 0.9rem !important;
  transition: border-color .2s, box-shadow .2s !important;
  min-height: 38px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
  border-color: var(--a) !important;
  box-shadow: 0 0 0 3px var(--a-focus) !important;
  outline: none !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {
  color: var(--t3) !important;
}

/* ── Form labels ────────────────────────────────────────────────────────── */
.stTextInput label, .stTextArea label, .stSelectbox label,
.stSlider label, .stNumberInput label, .stMultiSelect label {
  color: var(--t3) !important;
  font-size: 0.71rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.09em !important;
  min-height: 16px !important;
  margin-bottom: 0.38rem !important;
}

/* ── Selectbox ──────────────────────────────────────────────────────────── */
.stSelectbox > div > div {
  background: var(--surf2) !important;
  border: 1.5px solid var(--border) !important;
  border-radius: var(--r-s) !important;
  color: var(--t1) !important;
  transition: border-color .2s !important;
  min-height: 38px !important;
  display: flex !important;
  align-items: center !important;
}
.stSelectbox > div > div:focus-within {
  border-color: var(--a) !important;
  box-shadow: 0 0 0 3px var(--a-focus) !important;
}
.stSelectbox [data-baseweb="select"] {
  min-height: 38px !important;
}

/* ── Multiselect ────────────────────────────────────────────────────────── */
.stMultiSelect > div > div {
  background: var(--surf2) !important;
  border: 1.5px solid var(--border) !important;
  border-radius: var(--r-s) !important;
}
.stMultiSelect [data-baseweb="tag"] {
  background: var(--a-tag-bg) !important;
  border: 1px solid var(--a-tag-bd) !important;
  border-radius: 6px !important;
  color: var(--al) !important;
}

/* ── Buttons ────────────────────────────────────────────────────────────── */
.stButton > button {
  border-radius: var(--r-s) !important;
  font-weight: 600 !important;
  font-size: 0.875rem !important;
  transition: all .18s ease !important;
  cursor: pointer !important;
  font-family: 'Space Grotesk', sans-serif !important;
}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button {
  height: 38px !important;
  min-height: 38px !important;
  padding: 0 18px !important;
  background: var(--grad-cta) !important;
  border: none !important;
  color: var(--on-a) !important;
  box-shadow: var(--a-btn-sh) !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button:hover {
  opacity: 0.88 !important;
  box-shadow: var(--a-btn-sh-h) !important;
  transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
  height: 38px !important;
  min-height: 38px !important;
  padding: 0 18px !important;
  background: transparent !important;
  border: 1.5px solid var(--border) !important;
  color: var(--t2) !important;
  line-height: 1 !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
}
.stButton > button[kind="secondary"]:hover {
  border-color: var(--border-h) !important;
  color: var(--t1) !important;
  background: var(--a-hover) !important;
}
.stButton > button[kind="tertiary"] {
  background: transparent !important;
  border: none !important;
  color: var(--al) !important;
  font-size: 0.84rem !important;
  line-height: 1 !important;
}
.stButton > button[kind="tertiary"]:hover { color: var(--a) !important; }

/* ── Tabs ───────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
  background: var(--surf) !important;
  border: 1.5px solid var(--border) !important;
  border-radius: var(--r-m) !important;
  padding: 6px !important;
  gap: 4px !important;
  box-shadow: var(--sh-sm) !important;
  min-height: 48px !important;
  align-items: center !important;
}
.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  border: none !important;
  border-radius: var(--r-s) !important;
  color: var(--t3) !important;
  font-weight: 500 !important;
  font-size: 0.84rem !important;
  padding: 0 1.1rem !important;
  min-height: 34px !important;
  height: 34px !important;
  transition: all .18s !important;
  cursor: pointer !important;
  font-family: 'Space Grotesk', sans-serif !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  line-height: 1 !important;
}
.stTabs [data-baseweb="tab"]:hover {
  color: var(--t1) !important;
  background: var(--a-hover) !important;
}
.stTabs [aria-selected="true"] {
  background: var(--grad) !important;
  color: var(--on-a) !important;
  font-weight: 600 !important;
  box-shadow: var(--a-tab-sh) !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* ── Metric cards ───────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
  background: var(--card) !important;
  border: 1.5px solid var(--border) !important;
  border-radius: var(--r-m) !important;
  padding: 1rem 1.2rem !important;
  transition: border-color .25s, transform .2s, box-shadow .22s !important;
  box-shadow: var(--sh-sm) !important;
  min-height: 104px !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
}
[data-testid="metric-container"]:hover {
  border-color: var(--border-h) !important;
  transform: translateY(-2px) !important;
  box-shadow: var(--glow), var(--sh-md) !important;
}
[data-testid="stMetricLabel"] p {
  color: var(--t3) !important;
  font-size: 0.69rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.1em !important;
  font-family: 'Space Grotesk', sans-serif !important;
  margin-bottom: 0.45rem !important;
}
[data-testid="stMetricValue"] {
  color: var(--t1) !important;
  font-size: 1.65rem !important;
  font-weight: 800 !important;
  font-family: 'Space Grotesk', sans-serif !important;
  letter-spacing: -0.03em !important;
}
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }

/* ── Dividers ───────────────────────────────────────────────────────────── */
hr {
  border: none !important;
  border-top: 1.5px solid var(--border) !important;
  margin: 1.25rem 0 !important;
  opacity: 1 !important;
}

/* ── Form containers ────────────────────────────────────────────────────── */
[data-testid="stForm"] {
  background: var(--surf) !important;
  border: 1.5px solid var(--border) !important;
  border-radius: var(--r-m) !important;
  padding: 1.5rem !important;
  box-shadow: var(--sh-md) !important;
}

/* ── Expanders ──────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
  background: var(--surf) !important;
  border: 1.5px solid var(--border) !important;
  border-radius: var(--r-s) !important;
  color: var(--t2) !important;
  font-size: 0.83rem !important;
  font-weight: 500 !important;
  transition: all .2s !important;
}
.streamlit-expanderHeader:hover {
  border-color: var(--a) !important;
  color: var(--t1) !important;
}
.streamlit-expanderContent {
  background: var(--surf) !important;
  border: 1.5px solid var(--border) !important;
  border-top: none !important;
  padding: 0.875rem !important;
}

/* ── Posts table (HTML — fully theme-aware) ─────────────────────────────── */
.dp-tbl-wrap {
  overflow-x: auto;
  border: 1.5px solid var(--border);
  border-radius: var(--r-m);
  box-shadow: var(--sh-sm);
  margin-bottom: 0.5rem;
}
.dp-tbl {
  width: 100%;
  border-collapse: collapse;
  background: var(--surf);
}
.dp-tbl-th {
  background: var(--surf2);
  color: var(--t3);
  font-weight: 700;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  padding: 10px 14px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1.5px solid var(--border);
}
.dp-tbl-td {
  padding: 10px 14px;
  color: var(--t1);
  font-size: 0.83rem;
  border-bottom: 1px solid var(--border);
  max-width: 340px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dp-tbl-tr:last-child .dp-tbl-td { border-bottom: none; }
.dp-tbl-tr:hover .dp-tbl-td { background: var(--a-hover); }
.dp-tbl-muted { color: var(--t3) !important; }
.dp-tbl-num { color: var(--t2); font-variant-numeric: tabular-nums; }
.dp-tbl-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px;
  border-top: 1.5px solid var(--border);
  background: var(--surf2);
  border-radius: 0 0 var(--r-m) var(--r-m);
}
.dp-tbl-page-info {
  font-size: 0.75rem; color: var(--t3); font-weight: 500;
  font-variant-numeric: tabular-nums;
}

/* ── Captions & Markdown ────────────────────────────────────────────────── */
.stCaption p {
  color: var(--t3) !important;
  font-size: 0.78rem !important;
  line-height: 1.65 !important;
}
.stMarkdown p { color: var(--t2) !important; line-height: 1.75 !important; }
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
  color: var(--t1) !important;
  font-weight: 700 !important;
  letter-spacing: -0.025em !important;
  font-family: 'Space Grotesk', sans-serif !important;
}
.stMarkdown a { color: var(--a2) !important; }
.stMarkdown a:hover { text-decoration: underline !important; }
.stMarkdown code {
  background: var(--surf2) !important;
  color: var(--al) !important;
  border-radius: 5px !important;
  padding: 2px 7px !important;
  font-size: 0.87em !important;
  font-family: 'Fira Code', monospace !important;
}
.stMarkdown blockquote {
  border-left: 3px solid var(--a) !important;
  background: var(--surf2) !important;
  margin: 8px 0 !important;
  padding: 8px 16px !important;
  border-radius: 0 var(--r-s) var(--r-s) 0 !important;
}
.stMarkdown ul li, .stMarkdown ol li {
  color: var(--t2) !important;
  line-height: 1.7 !important;
}

/* ── Misc Streamlit ─────────────────────────────────────────────────────── */
.stSpinner > div { border-top-color: var(--a) !important; }
.stAlert { border-radius: var(--r-s) !important; }
.stSlider [role="slider"] { background: var(--a) !important; }
.stNumberInput [data-baseweb="input"] {
  min-height: 38px !important;
}
.stNumberInput button {
  background: var(--surf2) !important;
  color: var(--t2) !important;
  min-height: 38px !important;
  width: 36px !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
}

/* ════════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENT CLASSES
   ════════════════════════════════════════════════════════════════════════ */

/* Logo */
.dp-logo {
  font-size: 1.5rem; font-weight: 800; color: var(--t1);
  letter-spacing: -0.035em;
  display: inline-flex; align-items: center; gap: 9px; line-height: 1;
  font-family: 'Space Grotesk', sans-serif;
}
.dp-logo-wrap {
  min-height: 38px;
  display: flex;
  align-items: center;
}
.dp-logo-pulse {
  width: 8px; height: 8px; background: var(--a); border-radius: 50%;
  box-shadow: 0 0 8px var(--a);
  animation: dp-pulse 2.5s ease-in-out infinite;
  flex-shrink: 0;
}
.dp-logo-grad {
  background: var(--grad);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* Pulse animation */
@keyframes dp-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(0.75); }
}

/* Hero tag badge */
.dp-hero-tag {
  display: inline-flex; align-items: center; gap: 9px;
  background: var(--a-tag-bg);
  border: 1px solid var(--a-tag-bd);
  color: var(--al);
  font-size: 10.5px; font-weight: 700;
  letter-spacing: 0.13em; text-transform: uppercase;
  padding: 6px 16px; border-radius: 50px; margin-bottom: 26px;
}
.dp-tag-dot {
  width: 6px; height: 6px; background: var(--al); border-radius: 50%;
  box-shadow: 0 0 6px var(--a);
  animation: dp-pulse 2.2s ease-in-out infinite;
}

/* Hero title + subtitle */
.dp-hero-title {
  font-size: clamp(2rem, 4vw, 3.2rem); font-weight: 900; line-height: 1.07;
  color: var(--t1); margin: 0 0 18px 0; letter-spacing: -0.04em;
  font-family: 'Space Grotesk', sans-serif;
}
.dp-hero-title .grad {
  background: var(--grad);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.dp-hero-sub {
  font-size: 1rem; color: var(--t2); line-height: 1.78; margin-bottom: 28px; max-width: 500px;
}

/* Landing stats strip */
.dp-stats { display: flex; gap: 40px; margin: 24px 0 30px 0; }
.dp-stat { display: flex; flex-direction: column; gap: 3px; }
.dp-stat-num {
  font-size: 1.7rem; font-weight: 800; letter-spacing: -0.04em;
  font-family: 'Space Grotesk', sans-serif;
  background: var(--grad);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.dp-stat-lbl {
  font-size: 0.72rem; color: var(--t3); font-weight: 700;
  text-transform: uppercase; letter-spacing: .09em;
}

/* Feature cards (glassmorphism in dark, clean in light) */
.dp-feature {
  display: flex; align-items: flex-start; gap: 14px;
  margin-bottom: 10px; padding: 14px 16px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-bord);
  border-radius: var(--r-s);
  transition: transform .22s, border-color .25s;
  cursor: default;
}
.dp-feature:hover { transform: translateX(4px); border-color: var(--border-h) !important; }
.dp-feature-icon {
  width: 38px; height: 38px;
  background: var(--grad-soft);
  border: 1.5px solid var(--border); border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 17px; flex-shrink: 0;
}
.dp-feature-text { font-size: 0.86rem; color: var(--t2); line-height: 1.55; }
.dp-feature-text strong {
  color: var(--t1); display: block; margin-bottom: 2px;
  font-weight: 600; font-family: 'Space Grotesk', sans-serif;
}

/* ── Theme toggle pill ────────────────────────────────────────── */
/* Marker makes the column uniquely targetable via :has() */
.dp-theme-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-theme-button-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-nav-actions-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-nav-back-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-nav-logo-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-nav-login-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-nav-signup-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-dash-badge-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-dash-logout-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
.dp-dash-actions-marker {
    height: 0 !important; line-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
    display: block !important;
}
[data-testid="stMarkdownContainer"]:has(.dp-theme-marker) {
    height: 0 !important; overflow: hidden !important;
    margin: 0 !important; padding: 0 !important;
}
[data-testid="stMarkdownContainer"]:has(.dp-theme-button-marker) {
    height: 0 !important; overflow: hidden !important;
    margin: 0 !important; padding: 0 !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-marker),
[data-testid="stElementContainer"]:has(.dp-theme-button-marker),
[data-testid="stElementContainer"]:has(.dp-dash-badge-marker),
[data-testid="stElementContainer"]:has(.dp-dash-logout-marker),
[data-testid="stElementContainer"]:has(.dp-dash-actions-marker),
[data-testid="stElementContainer"]:has(.dp-nav-logo-marker),
[data-testid="stElementContainer"]:has(.dp-nav-actions-marker),
[data-testid="stElementContainer"]:has(.dp-nav-login-marker),
[data-testid="stElementContainer"]:has(.dp-nav-signup-marker),
[data-testid="stElementContainer"]:has(.dp-nav-back-marker) {
    height: 0 !important; min-height: 0 !important; max-height: 0 !important;
    overflow: hidden !important; margin: 0 !important; padding: 0 !important;
}
[data-testid="stMarkdownContainer"]:has(.dp-nav-actions-marker) {
    height: 0 !important; overflow: hidden !important;
    margin: 0 !important; padding: 0 !important;
}
[data-testid="stMarkdownContainer"]:has(.dp-nav-back-marker) {
    height: 0 !important; overflow: hidden !important;
    margin: 0 !important; padding: 0 !important;
}
[data-testid="stMarkdownContainer"]:has(.dp-nav-logo-marker) {
    height: 0 !important; overflow: hidden !important;
    margin: 0 !important; padding: 0 !important;
}
[data-testid="stMarkdownContainer"]:has(.dp-nav-login-marker),
[data-testid="stMarkdownContainer"]:has(.dp-nav-signup-marker) {
    height: 0 !important; overflow: hidden !important;
    margin: 0 !important; padding: 0 !important;
}
[data-testid="stMarkdownContainer"]:has(.dp-dash-badge-marker),
[data-testid="stMarkdownContainer"]:has(.dp-dash-logout-marker),
[data-testid="stMarkdownContainer"]:has(.dp-dash-actions-marker) {
    height: 0 !important; overflow: hidden !important;
    margin: 0 !important; padding: 0 !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-back-marker):has(.dp-nav-actions-marker) {
    align-items: center !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-back-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) {
    display: flex !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    gap: 12px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-back-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"] {
    min-width: 0 !important;
    align-self: center !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-back-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:nth-child(3) {
    flex: 1 1 auto !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-back-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:has(.dp-theme-marker) {
    flex: 0 0 44px !important;
    width: 44px !important;
    max-width: 44px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-back-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:has(.dp-nav-login-marker) {
    flex: 0 0 124px !important;
    width: 124px !important;
    max-width: 124px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-back-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:has(.dp-nav-signup-marker) {
    flex: 0 0 140px !important;
    width: 140px !important;
    max-width: 140px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) {
    display: flex !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 12px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"] {
    min-width: 0 !important;
    align-self: center !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:has(.dp-nav-logo-marker) {
    flex: 0 1 auto !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:has(.dp-theme-marker) {
    flex: 0 0 44px !important;
    width: 44px !important;
    max-width: 44px !important;
    margin-top: 20px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:has(.dp-nav-login-marker) {
    flex: 0 0 124px !important;
    width: 124px !important;
    max-width: 124px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-nav-login-marker):has(.dp-nav-signup-marker) > [data-testid="stColumn"]:has(.dp-nav-signup-marker) {
    flex: 0 0 140px !important;
    width: 140px !important;
    max-width: 140px !important;
}
[data-testid="stColumn"]:has(.dp-nav-back-marker) {
    display: flex !important;
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-nav-back-marker) > div,
[data-testid="stColumn"]:has(.dp-nav-back-marker) [data-testid="stVerticalBlock"] {
    width: auto !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    display: flex !important;
    align-items: center !important;
    min-height: 38px !important;
}
[data-testid="stColumn"]:has(.dp-nav-back-marker) .stButton {
    display: flex !important;
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-nav-back-marker) .stButton > button[kind="tertiary"] {
    height: 38px !important;
    min-height: 38px !important;
    padding: 0 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    line-height: 1 !important;
    margin: 0 !important;
}
[data-testid="stColumn"]:has(.dp-nav-logo-marker) {
    display: flex !important;
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-nav-logo-marker) > div,
[data-testid="stColumn"]:has(.dp-nav-logo-marker) [data-testid="stVerticalBlock"] {
    width: auto !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    display: flex !important;
    align-items: center !important;
    min-height: 38px !important;
}
[data-testid="stColumn"]:has(.dp-dash-badge-marker),
[data-testid="stColumn"]:has(.dp-dash-logout-marker) {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-dash-badge-marker):has(.dp-dash-logout-marker) {
    display: flex !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    justify-content: flex-end !important;
    gap: 12px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-dash-badge-marker):has(.dp-dash-logout-marker) > [data-testid="stColumn"] {
    min-width: 0 !important;
    align-self: center !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-dash-badge-marker):has(.dp-dash-logout-marker) > [data-testid="stColumn"]:nth-child(2) {
    flex: 1 1 auto !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-dash-badge-marker):has(.dp-dash-logout-marker) > [data-testid="stColumn"]:has(.dp-theme-marker) {
    flex: 0 0 44px !important;
    width: 44px !important;
    max-width: 44px !important;
    margin-top: 15px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-dash-badge-marker):has(.dp-dash-logout-marker) > [data-testid="stColumn"]:has(.dp-dash-badge-marker) {
    flex: 0 1 auto !important;
    width: auto !important;
    max-width: none !important;
    margin-top: -2px !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-nav-logo-marker):has(.dp-dash-badge-marker):has(.dp-dash-logout-marker) > [data-testid="stColumn"]:has(.dp-dash-logout-marker) {
    flex: 0 0 112px !important;
    width: 112px !important;
    max-width: 112px !important;
    margin-top: 6px !important;
}
[data-testid="stColumn"]:has(.dp-dash-actions-marker) {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
    margin-left: auto !important;
    width: 100% !important;
}
[data-testid="stColumn"]:has(.dp-dash-actions-marker) > div,
[data-testid="stColumn"]:has(.dp-dash-actions-marker) [data-testid="stVerticalBlock"] {
    width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-dash-actions-marker) {
    width: 100% !important;
    align-items: center !important;
}
[data-testid="stHorizontalBlock"]:has(.dp-dash-actions-marker) > [data-testid="stColumn"]:has(.dp-dash-actions-marker) {
    margin-left: auto !important;
}
[data-testid="stColumn"]:has(.dp-dash-actions-marker) [data-testid="stHorizontalBlock"] {
    display: flex !important;
    align-items: stretch !important;
    justify-content: flex-end !important;
    gap: 12px !important;
    min-height: 38px !important;
}
[data-testid="stColumn"]:has(.dp-dash-actions-marker) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 0 !important;
    display: flex !important;
    align-items: center !important;
    align-self: stretch !important;
}
[data-testid="stColumn"]:has(.dp-dash-actions-marker) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div,
[data-testid="stColumn"]:has(.dp-dash-actions-marker) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] [data-testid="stVerticalBlock"] {
    width: auto !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    min-height: 38px !important;
}
[data-testid="stColumn"]:has(.dp-dash-actions-marker) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
    margin-top: 0 !important;
}
[data-testid="stColumn"]:has(.dp-dash-badge-marker) > div,
[data-testid="stColumn"]:has(.dp-dash-badge-marker) [data-testid="stVerticalBlock"],
[data-testid="stColumn"]:has(.dp-dash-logout-marker) > div,
[data-testid="stColumn"]:has(.dp-dash-logout-marker) [data-testid="stVerticalBlock"] {
    width: auto !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: flex-end !important;
    justify-content: center !important;
    min-height: 38px !important;
}
[data-testid="stColumn"]:has(.dp-dash-logout-marker) .stButton {
    display: flex !important;
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-dash-logout-marker) .stButton > button {
    min-width: 94px !important;
    height: 38px !important;
    min-height: 38px !important;
}
[data-testid="stColumn"]:has(.dp-dash-badge-marker) > div,
[data-testid="stColumn"]:has(.dp-dash-badge-marker) [data-testid="stVerticalBlock"] {
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-dash-logout-marker) > div,
[data-testid="stColumn"]:has(.dp-dash-logout-marker) [data-testid="stVerticalBlock"] {
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-dash-logout-marker) .stButton,
[data-testid="stColumn"]:has(.dp-dash-logout-marker) .stButton > button {
    width: 100% !important;
}
[data-testid="stColumn"]:has(.dp-nav-actions-marker) [data-testid="stHorizontalBlock"] {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
    gap: 10px !important;
}
[data-testid="stColumn"]:has(.dp-nav-actions-marker) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 0 0 auto !important;
    min-width: 0 !important;
    width: auto !important;
    display: flex !important;
    align-items: center !important;
    align-self: center !important;
}
[data-testid="stColumn"]:has(.dp-nav-actions-marker) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div,
[data-testid="stColumn"]:has(.dp-nav-actions-marker) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] [data-testid="stVerticalBlock"] {
    width: auto !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    display: flex !important;
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-nav-login-marker),
[data-testid="stColumn"]:has(.dp-nav-signup-marker) {
    flex: 0 0 124px !important;
    min-width: 124px !important;
    max-width: 124px !important;
    display: flex !important;
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-nav-login-marker) > div,
[data-testid="stColumn"]:has(.dp-nav-login-marker) [data-testid="stVerticalBlock"],
[data-testid="stColumn"]:has(.dp-nav-signup-marker) > div,
[data-testid="stColumn"]:has(.dp-nav-signup-marker) [data-testid="stVerticalBlock"] {
    width: 100% !important;
    min-width: 124px !important;
    max-width: 124px !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    display: flex !important;
    align-items: center !important;
}
[data-testid="stColumn"]:has(.dp-nav-login-marker) .stButton,
[data-testid="stColumn"]:has(.dp-nav-signup-marker) .stButton {
    width: 100% !important;
}
[data-testid="stColumn"]:has(.dp-nav-login-marker) .stButton > button,
[data-testid="stColumn"]:has(.dp-nav-signup-marker) .stButton > button {
    width: 100% !important;
    min-width: 124px !important;
    white-space: nowrap !important;
}
[data-testid="stColumn"]:has(.dp-nav-signup-marker),
[data-testid="stColumn"]:has(.dp-nav-signup-marker) > div,
[data-testid="stColumn"]:has(.dp-nav-signup-marker) [data-testid="stVerticalBlock"],
[data-testid="stColumn"]:has(.dp-nav-signup-marker) .stButton > button {
    min-width: 140px !important;
    max-width: 140px !important;
}
/* The pill button itself — height/padding inherited from global secondary rule */
[data-testid="stColumn"]:has(.dp-theme-marker) {
    flex: 0 0 44px !important;
    width: 44px !important;
    min-width: 0 !important;
    max-width: 44px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
}
[data-testid="stColumn"]:has(.dp-theme-marker) > div,
[data-testid="stColumn"]:has(.dp-theme-marker) [data-testid="stVerticalBlock"] {
    width: 44px !important;
    min-width: 44px !important;
    max-width: 44px !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    min-height: 38px !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    height: 24px !important;
    min-height: 24px !important;
    width: 44px !important;
    min-width: 44px !important;
    max-width: 44px !important;
    flex: 0 0 44px !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] {
    width: 44px !important;
    min-width: 44px !important;
    max-width: 44px !important;
    flex: 0 0 44px !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button {
    width: 44px !important;
    min-width: 44px !important;
    max-width: 44px !important;
    height: 24px !important;
    min-height: 24px !important;
    padding: 0 !important;
    border: 2px solid #272424 !important;
    border-radius: 999px !important;
    margin: 0 !important;
    position: relative !important;
    overflow: hidden !important;
    color: transparent !important;
    font-size: 0 !important;
    line-height: 0 !important;
    box-sizing: border-box !important;
    display: block !important;
    flex: 0 0 44px !important;
    background-clip: padding-box !important;
    transition: background .3s ease, box-shadow .3s ease, border-color .3s ease !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button:hover,
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button:focus,
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button:focus-visible,
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button:active {
    border-color: #272424 !important;
    outline: none !important;
}
[data-testid="stColumn"]:has(.dp-theme-light-marker) [data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button {
    background:
        linear-gradient(180deg, #ffffff 0%, #f4efea 100%) !important;
    box-shadow: 0 8px 18px rgba(17, 12, 12, 0.10) !important;
}
[data-testid="stColumn"]:has(.dp-theme-dark-marker) [data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button {
    background:
        linear-gradient(180deg, #3d5f8d 0%, #2d476d 100%) !important;
    box-shadow: inset 0 2px 4px rgba(11, 16, 27, 0.18), 0 8px 18px rgba(12, 25, 45, 0.18) !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button::before {
    content: "" !important;
    position: absolute !important;
    width: 14px !important;
    height: 14px !important;
    top: 3px !important;
    border-radius: 999px !important;
    box-shadow: 0 3px 10px rgba(0,0,0,.18) !important;
    transition: left .25s ease, right .25s ease, background-color .3s ease, box-shadow .3s ease !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button::after {
    content: "" !important;
    position: absolute !important;
    top: 50% !important;
    width: 10px !important;
    height: 10px !important;
    transform: translateY(-50%) !important;
    opacity: 0.9 !important;
    background-repeat: no-repeat !important;
    background-position: center !important;
    background-size: contain !important;
    pointer-events: none !important;
}
[data-testid="stColumn"]:has(.dp-theme-light-marker) [data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button::before {
    left: 3px !important;
    background-color: #272324 !important;
    box-shadow: 0 4px 10px rgba(39, 35, 36, 0.18) !important;
}
[data-testid="stColumn"]:has(.dp-theme-light-marker) [data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button::after {
    right: 5px !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 44 44'%3E%3Cg fill='none' stroke='%231e1a1b' stroke-linecap='round' stroke-width='3'%3E%3Cpath d='M22 5v5'/%3E%3Cpath d='M22 34v5'/%3E%3Cpath d='M5 22h5'/%3E%3Cpath d='M34 22h5'/%3E%3Cpath d='M10.4 10.4l3.5 3.5'/%3E%3Cpath d='M30.1 30.1l3.5 3.5'/%3E%3Cpath d='M33.6 10.4l-3.5 3.5'/%3E%3Cpath d='M13.9 30.1l-3.5 3.5'/%3E%3C/g%3E%3Ccircle cx='22' cy='22' r='8.2' fill='%231e1a1b'/%3E%3C/svg%3E") !important;
}
[data-testid="stColumn"]:has(.dp-theme-dark-marker) [data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button::before {
    left: 23px !important;
    background-color: #f7f3ec !important;
    box-shadow: 0 4px 12px rgba(14, 28, 48, 0.24) !important;
}
[data-testid="stColumn"]:has(.dp-theme-dark-marker) [data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button::after {
    left: 5px !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 44 44'%3E%3Cg fill='%23ecf3ff'%3E%3Cpath d='M15 8c-1.4 4.1.1 8.6 3.6 11.3 3.5 2.8 8.3 3.3 12.3 1.5-1.3 2.7-3.7 4.8-6.8 5.6-5.8 1.6-11.8-1.8-13.4-7.6C9.4 13 11.2 9.3 15 8Z'/%3E%3Ccircle cx='24' cy='12' r='1.4'/%3E%3Ccircle cx='29.5' cy='16.5' r='1.1'/%3E%3Ccircle cx='23.5' cy='20.5' r='1.1'/%3E%3Ccircle cx='33.5' cy='22.5' r='1.2'/%3E%3Ccircle cx='18' cy='18' r='0.9'/%3E%3C/g%3E%3C/svg%3E") !important;
}
[data-testid="stElementContainer"]:has(.dp-theme-button-marker) + [data-testid="stElementContainer"] .stButton > button p {
    display: none !important;
}

/* Nav separator */
.dp-nav-sep { border: none; border-top: 1.5px solid var(--border); margin: 8px 0 28px 0; }

/* User badge */
.dp-user-badge {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--surf2); border: 1.5px solid var(--border);
  border-radius: 50px; padding: 0 14px 0 9px;
  min-height: 38px;
  font-size: 0.8rem; color: var(--t2);
  white-space: nowrap;
  margin: 0 !important;
}
.dp-user-dot {
  width: 7px; height: 7px; background: var(--pos); border-radius: 50%;
  box-shadow: 0 0 7px var(--pos); flex-shrink: 0;
}

/* Auth form text (above the form box) */
.dp-form-title {
  font-size: 1.8rem; font-weight: 800; color: var(--t1);
  margin: 0 0 6px 0; letter-spacing: -0.035em;
  font-family: 'Space Grotesk', sans-serif;
}
.dp-form-sub { font-size: 0.875rem; color: var(--t3); margin: 0 0 22px 0; line-height: 1.6; }

/* Password requirement list */
.dp-pw-req {
  background: var(--surf2);
  border: 1.5px solid var(--border);
  border-radius: var(--r-s); padding: 12px 16px; margin: 8px 0 16px 0;
}
.dp-pw-req-title {
  font-size: 0.69rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .1em; color: var(--t3); margin-bottom: 8px; display: block;
}
.dp-pw-item {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.77rem; color: var(--t3); margin-bottom: 4px; line-height: 1.4;
}
.dp-pw-item.met { color: var(--pos) !important; }
.dp-pw-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--t4); flex-shrink: 0; }
.dp-pw-item.met .dp-pw-dot { background: var(--pos); box-shadow: 0 0 5px rgba(52,211,153,.5); }

/* Dashboard tab section headers */
.dp-tab-header {
  padding: 0.45rem 0 1rem 0;
  border-bottom: 1.5px solid var(--border); margin-bottom: 1.4rem;
}
.dp-tab-title {
  font-size: 1.35rem; font-weight: 800; color: var(--t1);
  margin: 0 0 0.55rem 0; letter-spacing: -0.03em;
  display: flex !important; align-items: center !important; gap: 16px !important;
  font-family: 'Space Grotesk', sans-serif;
  line-height: 1;
}
.dp-tab-title-icon {
  display: inline-flex !important; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  background: var(--grad-soft);
  border: 1.5px solid var(--border);
  border-radius: 8px; font-size: 15px; flex-shrink: 0; line-height: 1;
  align-self: center !important;
  transform: translateY(-7px);
  margin-right: 6px !important;
}
.dp-tab-desc { font-size: 0.82rem; color: var(--t3); margin: 0; line-height: 1.55; max-width: 920px; }

/* Filter label */
.dp-filter-label {
  font-size: 0.67rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.11em; color: var(--t4); display: block; margin-bottom: 10px;
}
.dp-live-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 12px rgba(239,68,68,.5);
  display: inline-block;
}

/* Intelligence report UI */
.dp-query-hint {
  font-size: 0.68rem; color: var(--t3); font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.09em; margin-bottom: 7px; display: block;
}

/* Quick-question suggestion buttons — more breathing room for wrapped text */
[data-testid="stMarkdownContainer"]:has(.dp-query-hint) ~ div .stButton > button,
[data-testid="column"]:nth-child(2) .stButton > button {
  padding: 10px 14px;
  line-height: 1.4;
  white-space: normal;
  text-align: center;
  height: auto;
  min-height: 2.8rem;
}

/* Cache/fresh badges */
.dp-badge {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 0.73rem; font-weight: 700; padding: 5px 14px;
  border-radius: 50px; margin-bottom: 14px; letter-spacing: .02em;
}
.dp-badge-cached {
  background: var(--a-tag-bg);
  border: 1px solid var(--a-tag-bd);
  color: var(--a2);
}
.dp-badge-fresh {
  background: rgba(52,211,153,.09);
  border: 1px solid rgba(52,211,153,.28);
  color: var(--pos);
}

/* RAG source rows */
.dp-source-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; margin-bottom: 6px;
  background: var(--surf2); border: 1.5px solid var(--border);
  border-radius: var(--r-s); font-size: 0.8rem; color: var(--t2);
  transition: border-color .2s;
}
.dp-source-row:hover { border-color: var(--a) !important; }
.dp-source-row a { color: var(--a2) !important; text-decoration: none !important; }
.dp-source-row a:hover { text-decoration: underline !important; }
.dp-source-num {
  width: 22px; height: 22px;
  background: var(--a-tag-bg);
  border: 1px solid var(--a-tag-bd);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.67rem; font-weight: 800; color: var(--al); flex-shrink: 0;
}

/* Alert rows */
.dp-alert-row {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 16px; margin-bottom: 7px;
  background: var(--neg-b);
  border: 1.5px solid rgba(248,113,113,.22);
  border-radius: var(--r-s); transition: border-color .2s;
}
.dp-alert-row:hover { border-color: rgba(248,113,113,.45); }
.dp-alert-topic {
  font-weight: 700; color: var(--t1); font-size: 0.88rem; flex: 1;
  font-family: 'Space Grotesk', sans-serif;
}
.dp-alert-pct { font-weight: 800; color: var(--neg); font-size: 0.92rem; white-space: nowrap; }
.dp-alert-meta { font-size: 0.72rem; color: var(--t3); white-space: nowrap; }

/* Theme toggle chip */
.dp-theme-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 0.75rem; font-weight: 600;
  padding: 5px 12px; border-radius: 50px;
  background: var(--surf2); border: 1.5px solid var(--border);
  color: var(--t3); cursor: pointer; letter-spacing: .02em;
}
"""

# Silver Ghost SVG illustration — monochrome with green/red data pops
def _dashboard_svg(theme: str) -> str:
    wave_start = "#2f2f2f" if theme == "light" else "#ffffff"
    wave_mid = "#6a6a6a" if theme == "light" else "#d0d0d0"
    wave_opacity = "0.7" if theme == "light" else "0.38"
    baseline_opacity = "0.45" if theme == "light" else "0.6"

    return f"""<svg width="100%" viewBox="0 0 500 490" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#888888"/>
    </linearGradient>
    <linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{wave_start}" stop-opacity="0"/>
      <stop offset="40%" stop-color="{wave_mid}"/>
      <stop offset="60%" stop-color="{wave_mid}"/>
      <stop offset="100%" stop-color="{wave_start}" stop-opacity="0"/>
    </linearGradient>
  </defs>

  <ellipse cx="250" cy="215" rx="220" ry="170" fill="url(#glow)"/>

  <!-- Posts badge (top-left) -->
  <rect x="10" y="8" width="160" height="64" rx="13" fill="#1a1a1a" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <text x="28" y="31" font-family="DM Sans,sans-serif" font-size="8.5" fill="#555555" font-weight="700" letter-spacing="1">POSTS ANALYSED</text>
  <text x="28" y="59" font-family="Space Grotesk,sans-serif" font-size="23" font-weight="800" fill="#f0f0f0">12,847</text>

  <!-- Sentiment badge (top-right) -->
  <rect x="330" y="8" width="160" height="64" rx="13" fill="#1a1a1a" stroke="rgba(92,214,92,0.3)" stroke-width="1"/>
  <circle cx="356" cy="29" r="4.5" fill="#5cd65c"/>
  <circle cx="356" cy="29" r="10" fill="#5cd65c" opacity="0.14"/>
  <text x="370" y="29" font-family="DM Sans,sans-serif" font-size="8.5" fill="#555555" font-weight="700" dominant-baseline="middle">SENTIMENT</text>
  <text x="344" y="58" font-family="Space Grotesk,sans-serif" font-size="16" font-weight="800" fill="#5cd65c">Positive +72%</text>

  <!-- Terminal window -->
  <rect x="10" y="86" width="480" height="268" rx="14" fill="#111111" stroke="rgba(255,255,255,0.10)" stroke-width="1.5"/>
  <rect x="10" y="86" width="480" height="40" rx="14" fill="#1a1a1a"/>
  <rect x="10" y="108" width="480" height="18" fill="#1a1a1a"/>
  <circle cx="60"  cy="106" r="5.5" fill="#ff4444" opacity="0.75"/>
  <circle cx="80"  cy="106" r="5.5" fill="#e0a020" opacity="0.75"/>
  <circle cx="100" cy="106" r="5.5" fill="#5cd65c" opacity="0.75"/>
  <text x="210" y="111" font-family="Fira Code,monospace" font-size="11" fill="#444444">devpulse · intelligence</text>

  <text x="56" y="150" font-family="Fira Code,monospace" font-size="11" fill="url(#g1)">$</text>
  <text x="70" y="150" font-family="Fira Code,monospace" font-size="11" fill="#707070">analysing developer discussions</text>
  <text x="404" y="150" font-family="Fira Code,monospace" font-size="11" fill="#5cd65c">✓</text>

  <text x="56" y="172" font-family="Fira Code,monospace" font-size="10" fill="#444444">›</text>
  <text x="70" y="172" font-family="Fira Code,monospace" font-size="10" fill="#444444">source</text>
  <rect x="115" y="161" width="50" height="15" rx="4" fill="rgba(92,214,92,.10)"/>
  <text x="121" y="172" font-family="Fira Code,monospace" font-size="10" fill="#5cd65c">reddit</text>
  <text x="172" y="172" font-family="Fira Code,monospace" font-size="10" fill="#505050">r/rust · r/golang · r/python</text>

  <text x="56" y="193" font-family="Fira Code,monospace" font-size="10" fill="#444444">›</text>
  <text x="70" y="193" font-family="Fira Code,monospace" font-size="10" fill="#444444">source</text>
  <rect x="115" y="182" width="26" height="15" rx="4" fill="rgba(224,160,32,.10)"/>
  <text x="121" y="193" font-family="Fira Code,monospace" font-size="10" fill="#e0a020">HN</text>
  <text x="150" y="193" font-family="Fira Code,monospace" font-size="10" fill="#505050">TypeScript · Rust · AI tooling</text>

  <text x="56" y="215" font-family="Fira Code,monospace" font-size="10" fill="#444444">›</text>
  <text x="70" y="215" font-family="Fira Code,monospace" font-size="10" fill="#444444">sentiment</text>
  <rect x="134" y="204" width="100" height="13" rx="3" fill="rgba(0,0,0,.5)"/>
  <rect x="134" y="204" width="72"  height="13" rx="3" fill="#5cd65c" opacity="0.70"/>
  <text x="242" y="215" font-family="Fira Code,monospace" font-size="10" fill="#5cd65c">positive · 72%</text>

  <text x="56" y="237" font-family="Fira Code,monospace" font-size="10" fill="#444444">›</text>
  <text x="70" y="237" font-family="Fira Code,monospace" font-size="10" fill="#444444">trending</text>
  <rect x="134" y="226" width="58" height="14" rx="4" fill="rgba(255,255,255,.07)"/>
  <text x="140" y="237" font-family="Fira Code,monospace" font-size="10" fill="#d0d0d0">rust-lang</text>
  <rect x="200" y="226" width="72" height="14" rx="4" fill="rgba(255,255,255,.07)"/>
  <text x="206" y="237" font-family="Fira Code,monospace" font-size="10" fill="#d0d0d0">typescript</text>
  <rect x="280" y="226" width="44" height="14" rx="4" fill="rgba(255,255,255,.05)"/>
  <text x="286" y="237" font-family="Fira Code,monospace" font-size="10" fill="#909090">python</text>

  <text x="56" y="259" font-family="Fira Code,monospace" font-size="10" fill="#444444">›</text>
  <text x="70" y="259" font-family="Fira Code,monospace" font-size="10" fill="#444444">report</text>
  <text x="134" y="259" font-family="Fira Code,monospace" font-size="10" fill="#505050">generating intelligence summary</text>
  <text x="404" y="259" font-family="Fira Code,monospace" font-size="10" fill="#888888">···</text>

  <text x="56" y="298" font-family="Fira Code,monospace" font-size="11" fill="url(#g1)">$</text>
  <rect x="70" y="286" width="9" height="14" rx="1" fill="#ffffff" opacity="0.55"/>

  <!-- Controversy badge (bottom-left) -->
  <rect x="10" y="364" width="160" height="60" rx="13" fill="#1a1a1a" stroke="rgba(255,68,68,0.28)" stroke-width="1"/>
  <text x="28" y="387" font-family="DM Sans,sans-serif" font-size="8.5" fill="#555555" font-weight="700" letter-spacing="0.5">CONTROVERSY SPIKE</text>
  <text x="28" y="412" font-family="Space Grotesk,sans-serif" font-size="12.5" font-weight="700" fill="#ff4444">React · HN +34%</text>

  <!-- Trending badge (bottom-right) -->
  <rect x="330" y="364" width="160" height="60" rx="13" fill="#1a1a1a" stroke="rgba(255,255,255,0.14)" stroke-width="1"/>
  <text x="348" y="387" font-family="DM Sans,sans-serif" font-size="8.5" fill="#555555" font-weight="700" letter-spacing="0.5">TRENDING NOW</text>
  <text x="348" y="412" font-family="Space Grotesk,sans-serif" font-size="16" font-weight="800" fill="#f0f0f0">Rust Lang</text>

  <!-- Connector dots -->
  <circle cx="170" cy="40" r="2.5" fill="rgba(255,255,255,0.28)"/>
  <circle cx="330" cy="40" r="2.5" fill="rgba(92,214,92,0.4)"/>
  <circle cx="170" cy="394" r="2.5" fill="rgba(255,68,68,0.4)"/>
  <circle cx="330" cy="394" r="2.5" fill="rgba(255,255,255,0.2)"/>

  <!-- Pulse wave -->
  <polyline
    points="30,474 74,464 118,476 162,458 206,470 250,452 294,464 338,450 382,462 426,450 470,460"
    stroke="url(#g2)" stroke-width="1.8" fill="none" opacity="{wave_opacity}"
    stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="30" y1="480" x2="470" y2="480" stroke="url(#g2)" stroke-width="0.7" opacity="{baseline_opacity}"/>
</svg>"""


# ══════════════════════════════════════════════════════════════════════════════
# THEME HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _t() -> str:
    """Return current theme: 'dark' | 'light'."""
    return st.session_state.get("theme", "dark")


def _inject() -> None:
    """Inject full CSS into the Streamlit page."""
    theme = _t()
    vars_block = _DARK_VARS if theme == "dark" else _LIGHT_VARS
    st.markdown(f"<style>{vars_block}{_SHARED_CSS}</style>", unsafe_allow_html=True)


def _toggle_theme() -> None:
    st.session_state.theme = "light" if _t() == "dark" else "dark"


def _theme_toggle(key: str) -> None:
    st.button(
        "Theme",
        key=f"{key}_button",
        on_click=_toggle_theme,
        type="secondary",
    )


# ══════════════════════════════════════════════════════════════════════════════
# NAVIGATION BAR
# ══════════════════════════════════════════════════════════════════════════════

def _nav_bar(active_page: str) -> None:
    _inject()
    theme = _t()

    if active_page != "landing":
        back_col, logo_col, spacer_col, theme_col, login_col, signup_col = st.columns(
            [0.10, 0.30, 1.00, 0.09, 0.14, 0.17],
            gap="small", vertical_alignment="center",
        )
        with back_col:
            st.markdown('<span class="dp-nav-back-marker"></span>', unsafe_allow_html=True)
            if st.button("← Home", key="nav_home", type="tertiary"):
                st.session_state.auth_page = "landing"
                st.rerun()
    else:
        logo_col, spacer_col, theme_col, login_col, signup_col = st.columns(
            [0.38, 1.00, 0.09, 0.14, 0.17],
            gap="small", vertical_alignment="center",
        )

    with logo_col:
        st.markdown('<span class="dp-nav-logo-marker"></span>', unsafe_allow_html=True)
        st.markdown(
            '<div class="dp-logo-wrap">'
            '<div class="dp-logo">'
            '<span class="dp-logo-pulse"></span>'
            'Dev<span class="dp-logo-grad">Pulse</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    if active_page == "landing":
        with spacer_col:
            st.empty()

        with theme_col:
            marker_class = "dp-theme-dark-marker" if theme == "dark" else "dp-theme-light-marker"
            st.markdown(f'<span class="dp-theme-marker {marker_class}"></span>', unsafe_allow_html=True)
            st.markdown('<span class="dp-theme-button-marker"></span>', unsafe_allow_html=True)
            _theme_toggle("nav_theme")

        with login_col:
            st.markdown('<span class="dp-nav-login-marker"></span>', unsafe_allow_html=True)
            if st.button(
                "Login",
                use_container_width=True,
                type="secondary",
                key="nav_login",
            ):
                st.session_state.auth_page = "login"
                st.session_state.show_reset = False
                st.session_state.reset_token_sent = False
                st.session_state.reset_dev_token = None
                st.rerun()

        with signup_col:
            st.markdown('<span class="dp-nav-signup-marker"></span>', unsafe_allow_html=True)
            if st.button(
                "Sign Up →",
                use_container_width=True,
                type="primary",
                key="nav_register",
            ):
                st.session_state.auth_page = "register"
                st.rerun()
    else:
        with spacer_col:
            st.empty()

        with theme_col:
            marker_class = "dp-theme-dark-marker" if theme == "dark" else "dp-theme-light-marker"
            st.markdown(f'<span class="dp-theme-marker {marker_class}"></span>', unsafe_allow_html=True)
            st.markdown('<span class="dp-theme-button-marker"></span>', unsafe_allow_html=True)
            _theme_toggle("nav_theme")

        with login_col:
            st.markdown('<span class="dp-nav-login-marker"></span>', unsafe_allow_html=True)
            if st.button(
                "Login",
                use_container_width=True,
                type="secondary",
                key="nav_login",
            ):
                st.session_state.auth_page = "login"
                st.session_state.show_reset = False
                st.session_state.reset_token_sent = False
                st.session_state.reset_dev_token = None
                st.rerun()

        with signup_col:
            st.markdown('<span class="dp-nav-signup-marker"></span>', unsafe_allow_html=True)
            if st.button(
                "Sign Up →",
                use_container_width=True,
                type="primary",
                key="nav_register",
            ):
                st.session_state.auth_page = "register"
                st.rerun()

    st.markdown("<hr class='dp-nav-sep'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# LANDING PAGE
# ══════════════════════════════════════════════════════════════════════════════

def _show_landing() -> None:
    _nav_bar("landing")

    hero_col, _, img_col = st.columns([1.05, 0.08, 0.87])

    with hero_col:
        st.markdown(
            '<div class="dp-hero-tag">'
            '<span class="dp-tag-dot"></span>'
            'Real-Time Developer Intelligence'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<h1 class="dp-hero-title">'
            'What are developers<br>saying about your <span class="grad">stack</span>?'
            '</h1>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="dp-hero-sub">'
            'DevPulse aggregates and analyses real-time discussions from Reddit and Hacker News — '
            'surfacing sentiment trends, emotional signals, and community divergence across tools, '
            'frameworks, and the topics developers care about.'
            '</p>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="dp-stats">'
            '<div class="dp-stat">'
            '<span class="dp-stat-num">12,847</span>'
            '<span class="dp-stat-lbl">Posts analysed</span>'
            '</div>'
            '<div class="dp-stat">'
            '<span class="dp-stat-num">13</span>'
            '<span class="dp-stat-lbl">Topics tracked</span>'
            '</div>'
            '<div class="dp-stat">'
            '<span class="dp-stat-num">2</span>'
            '<span class="dp-stat-lbl">Live sources</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        for icon, title, desc in [
            ("🔴", "Live Feed", "Real-time stream of developer discussions as they happen"),
            ("📈", "Sentiment Trends", "Mood shifts across tools and topics over time"),
            ("⚔️", "Community Divergence", "See exactly where Reddit and Hacker News disagree"),
            ("🧠", "Intelligence Reports", "AI-generated summaries powered by Corrective RAG"),
        ]:
            st.markdown(
                f'<div class="dp-feature">'
                f'<div class="dp-feature-icon">{icon}</div>'
                f'<div class="dp-feature-text"><strong>{title}</strong>{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)
        cta1, cta2, _ = st.columns([0.24, 0.18, 0.58])
        with cta1:
            if st.button("Get Started →", type="primary", use_container_width=True, key="hero_signup"):
                st.session_state.auth_page = "register"
                st.rerun()
        with cta2:
            if st.button("Sign In", type="secondary", use_container_width=True, key="hero_login"):
                st.session_state.auth_page = "login"
                st.rerun()

    with img_col:
        _svg_b64 = base64.b64encode(_dashboard_svg(_t()).strip().encode()).decode()
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{_svg_b64}" '
            f'width="100%" style="margin-top:4px; max-width:520px">',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ══════════════════════════════════════════════════════════════════════════════

def _show_login_page() -> None:
    # Patch Streamlit's <form> elements to include action/method attributes so
    # browsers (Chrome/Firefox) recognise password inputs as contained in a form
    # and suppress the "Password field is not contained in a form" console warning.
    stcomponents.html(
        """<script>
        (function () {
            function patchForms() {
                var doc = window.parent.document;
                doc.querySelectorAll('form').forEach(function (f) {
                    if (!f.getAttribute('action')) { f.setAttribute('action', '#'); }
                    if (!f.getAttribute('method')) { f.setAttribute('method', 'post'); }
                });
            }
            var mo = new MutationObserver(patchForms);
            mo.observe(window.parent.document.body, { childList: true, subtree: true });
            patchForms();
        })();
        </script>""",
        height=0,
    )
    _nav_bar("login")
    _, center, _ = st.columns([1, 1.2, 1])

    with center:
        if st.session_state.pop("reset_success", False):
            st.markdown(
                '<p class="dp-form-title">Password updated!</p>'
                '<p class="dp-form-sub">Your password has been reset. You can now sign in.</p>',
                unsafe_allow_html=True,
            )
            st.success("Password updated successfully.")
            if st.button("← Back to sign in", use_container_width=True):
                st.rerun()
        elif not st.session_state.get("show_reset"):
            st.markdown(
                '<p class="dp-form-title">Welcome back</p>'
                '<p class="dp-form-sub">Sign in to your DevPulse account</p>',
                unsafe_allow_html=True,
            )
            with st.form("login_form"):
                email = st.text_input("Email address")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in →", use_container_width=True)
                if submitted:
                    if login(email, password):
                        _write_session_cookies(st.session_state["token"], st.session_state["email"])
                        st.rerun()
            if st.button("Forgot your password?", type="tertiary"):
                st.session_state.show_reset = True
                st.rerun()

        elif not st.session_state.get("reset_token_sent"):
            st.markdown(
                '<p class="dp-form-title">Reset password</p>'
                '<p class="dp-form-sub">Enter your email and we\'ll send you a one-time code.</p>',
                unsafe_allow_html=True,
            )
            with st.form("forgot_form"):
                email = st.text_input("Email address")
                c1, c2 = st.columns(2)
                with c1:
                    submitted = st.form_submit_button("Send OTP →", use_container_width=True)
                with c2:
                    cancel = st.form_submit_button("← Back to login", use_container_width=True)
                if cancel:
                    st.session_state.show_reset = False
                    st.rerun()
                if submitted and email:
                    data = forgot_password(email)
                    if _forgot_password_started(data):
                        st.session_state.reset_token_sent = True
                        st.session_state.reset_dev_token = data.get("reset_token")
                        st.session_state.reset_email = email
                        st.session_state.reset_message = data.get("message", "")
                        st.session_state.otp_verified = False
                        st.session_state.verified_otp_token = None
                        st.session_state.pop("otp_error", None)
                        st.session_state.pop("otp_input", None)
                        st.rerun()
                    elif data is not None:
                        st.error(data.get("message", "Password reset could not be started."))

        else:
            st.markdown(
                '<p class="dp-form-title">Set new password</p>',
                unsafe_allow_html=True,
            )
            st.info(st.session_state.get("reset_message", "Check your email for the OTP code."))

            otp_verified = st.session_state.get("otp_verified", False)

            # ── Stage 1: OTP entry & verification ────────────────────────────
            if not otp_verified:
                # Clear the input field if flagged (must happen before widget is created).
                if st.session_state.pop("clear_otp_input", False):
                    st.session_state.pop("otp_input", None)
                # Seed with dev token on first render or after a clear.
                if "otp_input" not in st.session_state:
                    st.session_state["otp_input"] = st.session_state.get("reset_dev_token") or ""

                if st.session_state.get("otp_error"):
                    st.error(st.session_state["otp_error"])

                st.text_input("OTP code", key="otp_input")
                v1, v2 = st.columns(2)
                with v1:
                    verify_clicked = st.button("Verify OTP →", use_container_width=True)
                with v2:
                    cancel = st.button("← Cancel", use_container_width=True)

                if cancel:
                    st.session_state.show_reset = False
                    st.session_state.reset_token_sent = False
                    st.session_state.reset_dev_token = None
                    st.session_state.otp_verified = False
                    st.session_state.pop("otp_input", None)
                    st.session_state.pop("otp_error", None)
                    st.rerun()

                if verify_clicked:
                    token = st.session_state.get("otp_input", "").strip()
                    if not token:
                        st.session_state["otp_error"] = "Please enter the OTP code."
                        st.rerun()
                    else:
                        verification = verify_reset_otp(token)
                        if verification.get("valid"):
                            st.session_state.otp_verified = True
                            st.session_state.verified_otp_token = token
                            st.session_state.pop("otp_error", None)
                            st.rerun()
                        st.session_state["otp_error"] = verification.get(
                            "message",
                            "Incorrect OTP. Please check your email and try again.",
                        )
                        if "incorrect otp" in st.session_state["otp_error"].lower():
                            st.session_state["clear_otp_input"] = True
                        st.rerun()
            else:
                st.success("OTP verified. Please set your new password below.")

            # ── Stage 2: Password fields (only after OTP verified) ────────────
            if otp_verified:
                with st.form("reset_form"):
                    new_password = st.text_input("New password", type="password")
                    confirm = st.text_input("Confirm new password", type="password")
                    rules = _password_requirements(new_password)
                    all_met = all(ok for ok, _ in rules)
                    if new_password and not all_met:
                        unmet_rules = " • ".join(label for ok, label in rules if not ok)
                        st.caption(f"Password requirements: {unmet_rules}")
                    else:
                        st.caption("Password requirements match registration.")
                    submitted = st.form_submit_button("Reset Password →", use_container_width=True)
                    if submitted:
                        if not new_password:
                            st.error("Please enter a new password.")
                        elif new_password != confirm:
                            st.error("Passwords do not match.")
                        elif not all_met:
                            st.error("Password must include at least 8 characters, one uppercase letter, one number, and one special character.")
                        elif reset_password(st.session_state.get("verified_otp_token", ""), new_password):
                            st.session_state.show_reset = False
                            st.session_state.reset_token_sent = False
                            st.session_state.reset_dev_token = None
                            st.session_state.otp_verified = False
                            st.session_state.verified_otp_token = None
                            st.session_state.pop("otp_input", None)
                            st.session_state.reset_success = True
                            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# REGISTER PAGE
# ══════════════════════════════════════════════════════════════════════════════

def _show_register_page() -> None:
    _nav_bar("register")
    _, center, _ = st.columns([1, 1.2, 1])

    with center:
        if not st.session_state.get("verify_token_sent"):
            st.markdown(
                '<p class="dp-form-title">Create account</p>'
                '<p class="dp-form-sub">Join DevPulse and start tracking developer sentiment.</p>',
                unsafe_allow_html=True,
            )

            reg_email = st.text_input("Email address", key="reg_email")
            reg_password = st.text_input("Password", type="password", key="reg_password")

            pw = st.session_state.get("reg_password", "")
            rules = _password_requirements(pw)
            all_met = all(ok for ok, _ in rules)

            items = "".join(
                f'<div class="dp-pw-item {"met" if ok else ""}">'
                f'<span class="dp-pw-dot"></span>{label}</div>'
                for ok, label in rules
            )
            st.markdown(
                f'<div class="dp-pw-req">'
                f'<span class="dp-pw-req-title">Password requirements</span>'
                f'{items}'
                f'</div>',
                unsafe_allow_html=True,
            )

            if st.button("Create Account →", use_container_width=True, type="primary", key="register_btn"):
                if not reg_email:
                    st.toast("Please enter your email address.", icon="⚠️")
                elif not all_met:
                    st.toast("Please satisfy all password requirements.", icon="⚠️")
                else:
                    data = register(reg_email, reg_password)
                    if data is not None:
                        st.session_state.verify_token_sent = True
                        st.session_state.verify_dev_token = data.get("verify_token")
                        st.session_state.verify_email_addr = reg_email
                        st.rerun()

        else:
            st.markdown(
                '<p class="dp-form-title">Verify your email</p>',
                unsafe_allow_html=True,
            )
            dev_token = st.session_state.get("verify_dev_token")
            if dev_token:
                st.warning(
                    "Email delivery failed (SMTP error). "
                    f"Use this code to verify: **`{dev_token}`**"
                )
            else:
                st.info(
                    f"A verification code was sent to "
                    f"**{st.session_state.get('verify_email_addr', 'your email')}**. "
                    "Check your spam folder if it doesn't appear — it expires in 5 minutes."
                )

            with st.form("verify_form"):
                token = st.text_input(
                    "Verification code",
                    value=st.session_state.get("verify_dev_token", ""),
                )
                c1, c2 = st.columns(2)
                with c1:
                    submitted = st.form_submit_button("Verify Email →", use_container_width=True)
                with c2:
                    cancel = st.form_submit_button("← Back", use_container_width=True)
                if cancel:
                    st.session_state.verify_token_sent = False
                    st.session_state.verify_dev_token = None
                    st.session_state.verify_email_addr = None
                    st.rerun()
                if submitted and token:
                    if verify_email(token):
                        st.session_state.verify_token_sent = False
                        st.session_state.verify_dev_token = None
                        st.session_state.verify_email_addr = None
                        st.session_state["email_verified"] = True
                        st.rerun()

        if st.session_state.get("email_verified", False):
            st.success("Email verified! You can now sign in.")
            if st.button("Go to Login →", type="primary", use_container_width=True, key="verified_go_to_login"):
                st.session_state["email_verified"] = False
                st.session_state.auth_page = "login"
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# AUTH GATE
# ══════════════════════════════════════════════════════════════════════════════

def show_login() -> None:
    if "auth_page" not in st.session_state:
        st.session_state.auth_page = "landing"
    page = st.session_state.auth_page
    if page == "login":
        _show_login_page()
    elif page == "register":
        _show_register_page()
    else:
        _show_landing()


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def show_dashboard() -> None:
    # Logout is handled as a normal rerender so the app returns to the auth flow
    # even if the browser ignores iframe parent-navigation.
    if st.session_state.get("logging_out"):
        _clear_session_cookies()
        st.session_state.clear()
        st.session_state["auth_page"] = "landing"
        st.query_params.clear()
        st.query_params["logged_out"] = "1"
        st.rerun()

    # Inject CSS first so elements are styled before they paint to the browser,
    # preventing a flash of unstyled/default Streamlit components.
    _inject()
    theme = _t()

    # Strip any URL query params that may have leaked credentials in older builds.
    if st.query_params:
        st.query_params.clear()

    # Refresh cookies on every dashboard render so they survive manual page reloads.
    # st.context.cookies reads from the HTTP request, so must be written here (iframe JS)
    # before the next reload — not just at login time.
    _write_session_cookies(st.session_state["token"], st.session_state["email"])

    from dashboard.tabs import (  # noqa: PLC0415
        community_comparison,
        intelligence_reports,
        live_feed,
        tool_tracker,
        trends,
    )

    email = st.session_state.get("email", "")
    logo_col, spacer_col, theme_col, badge_col, logout_col = st.columns(
        [0.82, 1.30, 0.08, 0.56, 0.22], gap="small", vertical_alignment="center"
    )

    with logo_col:
        st.markdown('<span class="dp-nav-logo-marker"></span>', unsafe_allow_html=True)
        st.markdown(
            '<div class="dp-logo-wrap">'
            '<div class="dp-logo">'
            '<span class="dp-logo-pulse"></span>'
            'Dev<span class="dp-logo-grad">Pulse</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with spacer_col:
        st.empty()

    with theme_col:
        marker_class = "dp-theme-dark-marker" if theme == "dark" else "dp-theme-light-marker"
        st.markdown(f'<span class="dp-theme-marker {marker_class}"></span>', unsafe_allow_html=True)
        st.markdown('<span class="dp-theme-button-marker"></span>', unsafe_allow_html=True)
        _theme_toggle("dash_theme")

    with badge_col:
        st.markdown('<span class="dp-dash-badge-marker"></span>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="dp-user-badge">'
            f'<span class="dp-user-dot"></span>{email}'
            f'</div>',
            unsafe_allow_html=True,
        )

    with logout_col:
        st.markdown('<span class="dp-dash-logout-marker"></span>', unsafe_allow_html=True)
        if st.button("Logout", key="top_logout", type="secondary", use_container_width=True):
            st.session_state["logging_out"] = True
            st.rerun()

    st.markdown(
        "<hr style='border:none;border-top:1.5px solid var(--border);margin:6px 0 20px 0'>",
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "  Live Feed  ",
        "  Trends  ",
        "  Community  ",
        "  Tool Tracker  ",
        "  Ask AI  ",
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


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if "token" not in st.session_state:
    # logged_out param: set by logout and kept in the URL until the user
    # successfully logs in, preventing stale cookies from restoring the session.
    if st.query_params.get("logged_out"):
        show_login()
    else:
        _saved_token = unquote(st.context.cookies.get(_COOKIE_TOKEN, ""))
        _saved_email = unquote(st.context.cookies.get(_COOKIE_EMAIL, ""))
        if _saved_token and _saved_email:
            st.session_state["token"] = _saved_token
            st.session_state["email"] = _saved_email
            show_dashboard()
        else:
            show_login()
else:
    show_dashboard()
