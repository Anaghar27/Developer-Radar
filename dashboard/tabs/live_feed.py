"""Lumina — Live Feed tab."""
import pandas as pd
import streamlit as st

from dashboard.api_client import api_get
from dashboard.components.charts import filters_label, metric_row, section_header
from dashboard.components.filters import sentiment_filter, source_filter, topic_filter

# Sentiment badge HTML
_SENT_BADGE = {
    "positive": '<span style="display:inline-block;padding:2px 10px;border-radius:50px;'
                'background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.3);'
                'color:#34D399;font-size:.72rem;font-weight:700">positive</span>',
    "negative": '<span style="display:inline-block;padding:2px 10px;border-radius:50px;'
                'background:rgba(248,113,113,.12);border:1px solid rgba(248,113,113,.3);'
                'color:#F87171;font-size:.72rem;font-weight:700">negative</span>',
    "neutral":  '<span style="display:inline-block;padding:2px 10px;border-radius:50px;'
                'background:rgba(148,163,184,.10);border:1px solid rgba(148,163,184,.2);'
                'color:#94A3B8;font-size:.72rem;font-weight:700">neutral</span>',
}


def render() -> None:
    section_header(
        '<span class="dp-live-dot"></span>',
        "Live Feed",
        "Most recent posts ingested from Reddit and Hacker News, with LLM classification labels.",
    )

    # ── Filters ───────────────────────────────────────────────────────────────
    filters_label()
    col1, col2, col3, col4 = st.columns(4, gap="medium")
    with col1:
        source = source_filter("lf_source")
    with col2:
        topic = topic_filter("lf_topic")
    with col3:
        sentiment = sentiment_filter("lf_sentiment")
    with col4:
        limit = st.number_input("Max posts", min_value=10, max_value=1000, value=50, step=10)

    PAGE_SIZE = 10
    filter_signature = (source, topic, sentiment, int(limit))
    if st.session_state.get("lf_filters") != filter_signature:
        st.session_state["lf_page"] = 0
        st.session_state["lf_filters"] = filter_signature

    page = st.session_state.get("lf_page", 0)
    max_rows = int(limit)
    max_pages = max(1, (max_rows + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, max_pages - 1))
    offset = page * PAGE_SIZE

    # ── Fetch ─────────────────────────────────────────────────────────────────
    params: dict = {"limit": PAGE_SIZE, "offset": offset}
    if source and source != "All":
        params["source"] = source
    if topic:
        params["topic"] = topic
    if sentiment:
        params["sentiment"] = sentiment

    data = api_get("/posts", params=params)
    if not data:
        return

    posts = data.get("posts", [])
    if not posts:
        st.info("No posts found for the selected filters.")
        return

    df = pd.DataFrame(posts)
    total_available = int(data.get("total", len(posts)))
    total_rows = min(total_available, max_rows)
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

    if page >= total_pages:
        st.session_state["lf_page"] = max(0, total_pages - 1)
        st.rerun()

    # ── Metrics ───────────────────────────────────────────────────────────────
    total     = total_available
    pos       = len(df[df["sentiment"] == "positive"])  if "sentiment" in df.columns else 0
    neu       = len(df[df["sentiment"] == "neutral"])   if "sentiment" in df.columns else 0
    neg       = len(df[df["sentiment"] == "negative"])  if "sentiment" in df.columns else 0
    avg_contr = df["controversy_score"].mean()           if "controversy_score" in df.columns else 0

    metric_row([
        {"label": "Total in DB",     "value": f"{total:,}"},
        {"label": "Current Page",    "value": len(posts)},
        {"label": "Positive",        "value": pos},
        {"label": "Neutral",         "value": neu},
        {"label": "Negative",        "value": neg},
        {"label": "Avg Controversy", "value": f"{avg_contr:.2f}"},
    ])

    st.divider()

    # ── Posts table with pagination ────────────────────────────────────────────
    display_cols = ["title", "source", "sentiment", "emotion", "topic", "tool_mentioned", "score"]
    available = [c for c in display_cols if c in df.columns]
    start = page * PAGE_SIZE
    end = min(start + len(df), total_rows)
    page_df = df[available]

    # Build table HTML
    header_html = "".join(
        f'<th class="dp-tbl-th">{col.replace("_", " ")}</th>'
        for col in available
    )
    rows_html = ""
    for _, row in page_df.iterrows():
        cells = ""
        for col in available:
            raw = row[col]
            val = "" if (raw is None or (isinstance(raw, float) and pd.isna(raw))) else str(raw)
            if col == "sentiment":
                cell_inner = _SENT_BADGE.get(val.lower(), f"<span>{val}</span>")
                cells += f'<td class="dp-tbl-td">{cell_inner}</td>'
            elif col == "tool_mentioned" and val.lower() in ("", "none", "nan"):
                cells += '<td class="dp-tbl-td dp-tbl-muted">None</td>'
            elif col == "score":
                cells += f'<td class="dp-tbl-td dp-tbl-num">{val}</td>'
            else:
                cells += f'<td class="dp-tbl-td">{val}</td>'
        rows_html += f'<tr class="dp-tbl-tr">{cells}</tr>'

    st.markdown(
        f'<div class="dp-tbl-wrap">'
        f'<table class="dp-tbl">'
        f'<thead><tr>{header_html}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True,
    )

    # ── Pagination controls ───────────────────────────────────────────────────
    prev_col, info_col, next_col = st.columns([1, 3, 1])
    with prev_col:
        if st.button("← Prev", key="lf_prev", disabled=(page == 0), use_container_width=True):
            st.session_state["lf_page"] = page - 1
            st.rerun()
    with info_col:
        st.markdown(
            f'<div class="dp-tbl-footer">'
            f'<span class="dp-tbl-page-info">'
            f'Rows {start + 1}–{end} of {total_rows} &nbsp;·&nbsp; Page {page + 1} of {total_pages}'
            f'</span></div>',
            unsafe_allow_html=True,
        )
    with next_col:
        if st.button("Next →", key="lf_next", disabled=(page >= total_pages - 1 or end >= total_rows), use_container_width=True):
            st.session_state["lf_page"] = page + 1
            st.rerun()

    st.caption(
        "Each row is one post classified by the LLM pipeline. "
        "Use the filters above to narrow by source, topic, or sentiment. "
        "Controversy score reflects how polarising a post was — higher means more divided reactions."
    )
