"""Lumina filter components — clean, minimal UI."""
import streamlit as st


def source_filter(key: str = "source") -> str | None:
    val = st.selectbox(
        "Source",
        options=["All", "reddit", "hackernews"],
        key=key,
        index=0,
    )
    return None if val == "All" else val


def topic_filter(key: str = "topic") -> str | None:
    topics = [
        "All", "LLM", "Agents", "RAG", "MLOps", "Python", "WebDev",
        "DevTools", "Cloud", "Hardware", "Security", "Career", "OpenSource", "Other",
    ]
    val = st.selectbox("Topic", options=topics, key=key, index=0)
    return None if val == "All" else val


def sentiment_filter(key: str = "sentiment") -> str | None:
    val = st.selectbox(
        "Sentiment",
        options=["All", "positive", "negative", "neutral"],
        key=key,
        index=0,
    )
    return None if val == "All" else val


def days_filter(key: str = "days", default: int = 28) -> int:
    valid_default = min(max(default, 7), 84)
    valid_default -= (valid_default - 7) % 7
    return st.slider(
        "Days to look back",
        min_value=7,
        max_value=84,
        value=valid_default,
        step=7,
        key=key,
    )


def tool_multiselect(key: str = "tools") -> str | None:
    tools = st.multiselect(
        "Select tools to compare",
        options=[
            "pytorch", "tensorflow", "kubernetes", "docker",
            "rust", "python", "javascript", "react", "fastapi",
            "airflow", "kafka", "dbt",
        ],
        key=key,
    )
    return ",".join(tools) if tools else None
