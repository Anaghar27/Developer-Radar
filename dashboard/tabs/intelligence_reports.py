"""Lumina — Intelligence Reports tab."""
import pandas as pd
import streamlit as st

from dashboard.api_client import api_get, api_post
from dashboard.components.charts import section_header

_SUGGESTIONS = [
    "What are the most discussed ML tools this week?",
    "How do developers feel about Rust vs Python?",
    "What are the top frustrations with Kubernetes?",
    "Which AI tools are generating the most excitement?",
    "What career topics are trending in the developer community?",
]


def _run_query(query: str, limit: int) -> None:
    with st.spinner("Running Corrective RAG pipeline… (first query may take 30–60 s)"):
        result = api_post("/query", {"query": query.strip(), "limit": limit})
    if result:
        st.session_state["rag_result"] = result


def render() -> None:
    section_header(
        "🧠",
        "Intelligence Reports",
        "Ask questions to the system — answers are grounded entirely in Reddit and Hacker News posts.",
    )

    # ── Two-column layout ─────────────────────────────────────────────────────
    query_col, sugg_col = st.columns([1.65, 1])

    with query_col:
        st.markdown('<span class="dp-query-hint">Your question</span>', unsafe_allow_html=True)
        with st.form("rag_query_form"):
            query = st.text_area(
                "question",
                label_visibility="collapsed",
                placeholder="e.g. What are developers saying about PyTorch vs TensorFlow this month?",
                height=110,
            )
            c1, c2 = st.columns([2.5, 1])
            with c1:
                limit = st.slider("Max sources", min_value=3, max_value=20, value=10)
            with c2:
                submitted = st.form_submit_button("Generate →", use_container_width=True)

        if submitted and query.strip():
            _run_query(query, limit)
        elif submitted:
            st.warning("Please enter a question before submitting.")

    with sugg_col:
        st.markdown('<span class="dp-query-hint">Quick questions</span><span class="dp-sugg-marker"></span>', unsafe_allow_html=True)
        for i, suggestion in enumerate(_SUGGESTIONS):
            if st.button(suggestion, key=f"sugg_{i}", use_container_width=True, type="secondary"):
                st.session_state["suggested_query"] = suggestion
                st.rerun()

    # Handle suggestion click outside column context
    if "suggested_query" in st.session_state:
        sq = st.session_state.pop("suggested_query")
        _run_query(sq, limit=10)

    # ── Report display ────────────────────────────────────────────────────────
    result = st.session_state.get("rag_result")
    if result:
        st.divider()

        if result.get("cached"):
            st.markdown(
                '<span class="dp-badge dp-badge-cached">⚡ Served from cache</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="dp-badge dp-badge-fresh">✦ Fresh report generated</span>',
                unsafe_allow_html=True,
            )

        st.markdown("#### Report")
        st.markdown(result["report"])
        st.caption(
            "This report is grounded entirely in posts from Hacker News and Reddit — "
            "the model cannot fabricate claims. Each paragraph cites [1], [2] etc. "
            "referring to the source URLs listed below."
        )

        sources = result.get("sources_used", [])
        if sources:
            st.markdown(f"**Sources ({len(sources)})**")
            rows = ""
            for i, src in enumerate(sources, 1):
                label = src if not src.startswith("http") else (src.split("/")[-1][:40] or src)
                link = (
                    f'<a href="{src}" target="_blank" rel="noopener">{label}</a>'
                    if src.startswith("http")
                    else f"<code>{src}</code>"
                )
                rows += (
                    f'<div class="dp-source-row">'
                    f'<span class="dp-source-num">{i}</span>'
                    f'{link}'
                    f'</div>'
                )
            st.markdown(rows, unsafe_allow_html=True)

        with st.expander("Report metadata"):
            st.json({
                "query":         result.get("query"),
                "generated_at":  result.get("generated_at"),
                "cached":        result.get("cached"),
                "sources_count": len(sources),
            })

    # ── Volume spike alerts ───────────────────────────────────────────────────
    st.divider()
    st.markdown(
        '<div class="dp-tab-header" style="border-bottom:none;padding-bottom:0">'
        '<h2 class="dp-tab-title">'
        '<span class="dp-tab-title-icon">🚨</span>'
        'Volume Spike Alerts'
        '</h2>'
        '<p class="dp-tab-desc">'
        'Topics with unusual post volume compared to their 7-day rolling average.'
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # CSS: style each alert card green and make the expander blend in as part of the card.
    st.markdown("""
    <style>
    .dp-alert-card {
        background: #0d2818;
        border: 1px solid #1a4a2e;
        border-radius: 8px;
        margin-bottom: 10px;
        overflow: hidden;
    }
    .dp-alert-card-header {
        display: flex;
        align-items: center;
        padding: 14px 18px;
        gap: 12px;
    }
    .dp-alert-card-topic {
        font-weight: 600;
        font-size: 15px;
        color: #e2e8f0;
        flex: 1;
    }
    .dp-alert-card-meta {
        font-size: 13px;
        color: #718096;
    }
    .dp-alert-card-pct {
        font-size: 14px;
        font-weight: 700;
        color: #48bb78;
        min-width: 52px;
        text-align: right;
    }
    /* Target the expander that immediately follows this card header —
       strip its default border/background so it merges with the card */
    .dp-alert-card + div [data-testid="stExpander"] {
        border: none !important;
        border-top: 1px solid #1a4a2e !important;
        border-radius: 0 !important;
        background: transparent !important;
    }
    </style>
    """, unsafe_allow_html=True)

    alerts_data = api_get("/alerts", params={"limit": 10})
    if alerts_data and alerts_data.get("alerts"):
        df = pd.DataFrame(alerts_data["alerts"])
        df["triggered_at"] = pd.to_datetime(df["triggered_at"])

        for _, row in df.iterrows():
            pct       = row.get("pct_increase", 0)
            triggered = row["triggered_at"].strftime("%b %d, %H:%M")
            today     = int(row.get("today_count", 0))
            avg       = int(row.get("rolling_avg", 0))
            topic     = row["topic"]

            with st.container():
                st.markdown(
                    f'<div class="dp-alert-card">'
                    f'<div class="dp-alert-card-header">'
                    f'<span class="dp-alert-card-topic">{topic}</span>'
                    f'<span class="dp-alert-card-meta">{today:,} posts · 7d avg {avg:,}</span>'
                    f'<span class="dp-alert-card-pct">+{pct:.0f}%</span>'
                    f'<span class="dp-alert-card-meta">{triggered}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                with st.expander(f"Show latest posts in {topic} ↓", expanded=False):
                    posts_data = api_get("/posts", params={"topic": topic, "limit": 5})
                    if posts_data and posts_data.get("posts"):
                        for post in posts_data["posts"]:
                            sentiment = post.get("sentiment") or "neutral"
                            tool      = post.get("tool_mentioned")
                            url       = post.get("url", "")
                            title     = post.get("title", "Untitled")
                            source    = post.get("source", "")
                            post_date = post.get("post_date", "")

                            title_html = (
                                f'<a href="{url}" target="_blank" rel="noopener" '
                                f'style="color:#90cdf4;text-decoration:none">{title}</a>'
                                if url else title
                            )
                            meta = f"{source} · {post_date}"
                            if tool:
                                meta += f" · {tool}"

                            st.markdown(
                                f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06)">'
                                f'<div style="font-size:14px;margin-bottom:4px">{title_html}</div>'
                                f'<div style="font-size:12px;color:#718096">{meta} · '
                                f'<span style="text-transform:capitalize">{sentiment}</span>'
                                f'</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("No recent posts found for this topic.")
    else:
        st.info("No volume spike alerts detected recently.")
