import streamlit as st
import pandas as pd
from dashboard.api_client import api_get
from dashboard.components.filters import topic_filter, source_filter, days_filter
from dashboard.components.charts import sentiment_line_chart, sentiment_bar_chart, metric_row


def render():
    st.header("📈 Sentiment Trends")
    st.caption("Daily sentiment aggregates from dbt mart_daily_sentiment")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        topic = topic_filter("tr_topic")
    with col2:
        source = source_filter("tr_source")
    with col3:
        days = days_filter("tr_days", default=30)

    params = {"days": days}
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

    # Metrics
    metric_row([
        {"label": "Data Points", "value": len(df)},
        {"label": "Avg Sentiment", "value": f"{df['avg_sentiment'].mean():.3f}"},
        {"label": "Total Posts", "value": int(df["post_count"].sum())},
        {"label": "Days Covered", "value": df["post_date"].nunique()},
    ])

    st.divider()

    # Charts
    sentiment_line_chart(df, title="Sentiment Over Time")
    sentiment_bar_chart(df, x_col="post_date", title="Post Volume by Sentiment")

    # Raw data expander
    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True, hide_index=True)
