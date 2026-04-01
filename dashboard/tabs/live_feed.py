import pandas as pd
import streamlit as st

from dashboard.api_client import api_get
from dashboard.components.charts import metric_row
from dashboard.components.filters import sentiment_filter, source_filter, topic_filter


def render():
    st.header("🔴 Live Feed")
    st.caption("Most recent posts with classification labels")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        source = source_filter("lf_source")
    with col2:
        topic = topic_filter("lf_topic")
    with col3:
        sentiment = sentiment_filter("lf_sentiment")
    with col4:
        limit = st.number_input("Max posts", min_value=10, max_value=1000, value=50, step=10)

    # Fetch data
    params = {"limit": limit}
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

    # Metrics row
    total = data.get("total", len(posts))
    pos = len(df[df["sentiment"] == "positive"]) if "sentiment" in df.columns else 0
    neu = len(df[df["sentiment"] == "neutral"]) if "sentiment" in df.columns else 0
    neg = len(df[df["sentiment"] == "negative"]) if "sentiment" in df.columns else 0
    avg_score = df["controversy_score"].mean() if "controversy_score" in df.columns else 0

    metric_row([
        {"label": "Total in DB", "value": total},
        {"label": "Showing", "value": len(posts)},
        {"label": "Positive", "value": pos},
        {"label": "Neutral", "value": neu},
        {"label": "Negative", "value": neg},
        {"label": "Avg Controversy", "value": f"{avg_score:.2f}"},
    ])

    st.divider()

    # Posts table
    display_cols = ["title", "source", "sentiment", "emotion", "topic", "tool_mentioned", "score"]
    available_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[available_cols],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Each row is one post ingested from Reddit or Hacker News and classified by the LLM. "
        "Use filters above to narrow by source, topic, or sentiment. "
        "Controversy score reflects how polarising the post was — higher means more divided reactions."
    )
