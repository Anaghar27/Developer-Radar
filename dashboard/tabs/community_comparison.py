"""Lumina — Community Comparison tab."""
import pandas as pd
import streamlit as st

from dashboard.api_client import api_get
from dashboard.components.charts import (
    community_overlay_chart,
    divergence_chart,
    filters_label,
    metric_row,
    section_header,
)
from dashboard.components.filters import days_filter, topic_filter


def render() -> None:
    section_header(
        "⚔️",
        "Community Comparison",
        "Reddit vs Hacker News sentiment divergence — where the two communities disagree most.",
    )

    # ── Filters ───────────────────────────────────────────────────────────────
    filters_label()
    col1, col2 = st.columns(2)
    with col1:
        topic = topic_filter("cc_topic")
    with col2:
        days = days_filter("cc_days", default=28)

    params: dict = {"days": days}
    if topic:
        params["topic"] = topic

    data = api_get("/community/divergence", params=params)
    if not data or not data.get("data"):
        st.info("No community divergence data available.")
        return

    df = pd.DataFrame(data["data"])
    df["post_date"] = pd.to_datetime(df["post_date"])

    def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
        total_weight = weights.sum()
        if total_weight <= 0:
            return 0.0
        return float((values * weights).sum() / total_weight)

    topic_rows = []
    for topic_name, group in df.groupby("topic", sort=True):
        topic_rows.append(
            {
                "topic": topic_name,
                "reddit_count": int(group["reddit_count"].sum()),
                "hn_count": int(group["hn_count"].sum()),
                "reddit_sentiment": _weighted_average(group["reddit_sentiment"], group["reddit_count"]),
                "hn_sentiment": _weighted_average(group["hn_sentiment"], group["hn_count"]),
            }
        )
    topic_df = pd.DataFrame(topic_rows)
    topic_df["sentiment_delta"] = (topic_df["reddit_sentiment"] - topic_df["hn_sentiment"]).round(4)
    topic_df = topic_df.sort_values("sentiment_delta", key=lambda col: col.abs(), ascending=False)

    # ── Metrics ───────────────────────────────────────────────────────────────
    avg_delta   = topic_df["sentiment_delta"].mean()
    max_div_row = topic_df.loc[topic_df["sentiment_delta"].abs().idxmax()] if not topic_df.empty else None

    metric_row([
        {"label": "Avg Delta",          "value": f"{avg_delta:+.3f}"},
        {"label": "Total Reddit Posts", "value": f"{int(df['reddit_count'].sum()):,}"},
        {"label": "Total HN Posts",     "value": f"{int(df['hn_count'].sum()):,}"},
        {"label": "Most Divergent",     "value": max_div_row["topic"] if max_div_row is not None else "N/A"},
    ])

    st.divider()

    # ── Divergence bar — aggregated across selected range ─────────────────────
    divergence_chart(topic_df, title=f"Sentiment Delta by Topic  (Last {days} Days)")
    st.caption(
        "Each bar shows Reddit sentiment minus HN sentiment for that topic across the selected date range. "
        "Green (positive delta) = Reddit is more positive than HN. "
        "Red (negative delta) = HN is more positive than Reddit. "
        "Near zero = communities broadly agree."
    )

    # ── Reddit vs HN overlay line chart ───────────────────────────────────────
    if not df.empty:
        daily = (
            df.groupby("post_date")[["reddit_sentiment", "hn_sentiment"]]
            .mean()
            .reset_index()
        )
        community_overlay_chart(daily)
        st.caption(
            "Reddit (orange-red) vs Hacker News (amber) average daily sentiment over the selected period. "
            "When lines diverge, the communities hold opposing views on the same topics. "
            "When they converge, sentiment is broadly shared across both platforms."
        )

    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True, hide_index=True)
