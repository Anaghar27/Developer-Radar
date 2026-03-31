import streamlit as st
from typing import Optional


def source_filter(key: str = "source") -> Optional[str]:
    return st.selectbox(
        "Source",
        options=["All", "reddit", "hackernews"],
        key=key,
        index=0,
    ) or None


def topic_filter(key: str = "topic") -> Optional[str]:
    topics = [
        "All", "LLM", "Agents", "RAG", "MLOps", "Python", "WebDev",
        "DevTools", "Cloud", "Hardware", "Security", "Career", "OpenSource", "Other",
    ]
    val = st.selectbox("Topic", options=topics, key=key, index=0)
    return None if val == "All" else val


def sentiment_filter(key: str = "sentiment") -> Optional[str]:
    val = st.selectbox(
        "Sentiment",
        options=["All", "positive", "negative", "neutral"],
        key=key,
        index=0,
    )
    return None if val == "All" else val


def days_filter(key: str = "days", default: int = 30) -> int:
    return st.slider(
        "Days to look back",
        min_value=7,
        max_value=90,
        value=default,
        step=7,
        key=key,
    )


def tool_multiselect(key: str = "tools") -> Optional[str]:
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
