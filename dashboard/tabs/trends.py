"""Lumina — Sentiment Trends tab."""
import pandas as pd
import streamlit as st

from dashboard.api_client import api_get
from dashboard.components.charts import (
    filters_label,
    metric_row,
    section_header,
    sentiment_bar_chart,
    sentiment_line_chart,
)
from dashboard.components.filters import days_filter, source_filter, topic_filter


def render() -> None:
    section_header(
        "📈",
        "Sentiment Trends",
        "Daily sentiment aggregates from the dbt mart — track mood shifts across tools and topics over time.",
    )

    # ── Filters ───────────────────────────────────────────────────────────────
    filters_label()
    col1, col2, col3 = st.columns(3)
    with col1:
        topic = topic_filter("tr_topic")
    with col2:
        source = source_filter("tr_source")
    with col3:
        days = days_filter("tr_days", default=28)

    params: dict = {"days": days}
    if topic:
        params["topic"] = topic
    if source and source != "All":
        params["source"] = source

    data = api_get("/trends", params=params)
    if not data or not data.get("data"):
        st.info("No trend data available for the selected filters.")
        return

    df = pd.DataFrame(data["data"])
    df["post_date"] = pd.to_datetime(df["post_date"])

    # ── Metrics ───────────────────────────────────────────────────────────────
    avg_sent = df["avg_sentiment"].mean()
    metric_row([
        {"label": "Data Points",   "value": len(df)},
        {"label": "Avg Sentiment", "value": f"{avg_sent:.3f}"},
        {"label": "Total Posts",   "value": f"{int(df['post_count'].sum()):,}"},
        {"label": "Days Covered",  "value": df["post_date"].nunique()},
    ])

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    if not topic:
        chart_df = (
            df.groupby("post_date")
            .agg(
                avg_sentiment=("avg_sentiment",  "mean"),
                positive_count=("positive_count", "sum"),
                negative_count=("negative_count", "sum"),
                neutral_count=("neutral_count",  "sum"),
                post_count=("post_count",    "sum"),
            )
            .reset_index()
        )
        sentiment_line_chart(chart_df, title="Overall Sentiment Over Time — All Topics")
        st.caption(
            "Average daily sentiment across all topics. "
            "Values above 0 indicate positive community mood; below 0 indicate negative. "
            "Select a specific topic above to isolate its individual trend line."
        )
        sentiment_bar_chart(chart_df, x_col="post_date", title="Post Volume by Sentiment")
        st.caption(
            "Daily post count split by sentiment. "
            "Taller green bars mean more positive posts that day; taller red bars mean more negative."
        )
    else:
        sentiment_line_chart(df, title=f"Sentiment Over Time — {topic}")
        st.caption(
            f"Daily average sentiment for the '{topic}' topic. "
            "Sustained dips suggest growing frustration; sustained rises suggest growing excitement."
        )
        sentiment_bar_chart(df, x_col="post_date", title=f"Post Volume by Sentiment — {topic}")
        st.caption(
            f"Volume of positive, neutral, and negative posts about '{topic}' per day. "
            "Spikes in volume often coincide with a new release, incident, or viral discussion."
        )

    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True, hide_index=True)
