"""Prompt templates for the LLM processing layer."""


CLASSIFICATION_PROMPT = """
You are analyzing a developer community post.
Extract the following and return ONLY valid JSON. No explanation, no markdown.
Post title: {title}
Post body: {body}
Return exactly this structure:
{{
"sentiment": "positive" | "negative" | "neutral",
"emotion": "excited" | "frustrated" | "skeptical" | "curious" | "neutral",
"topic": "LLM" | "RAG" | "MLOps" | "Python" | "Cloud" | "Hardware" | "Other",
"tool_mentioned": "<tool name as string, or null>",
"controversy_score": <integer 0-10>,
"reasoning": "<one sentence explaining your classification>"
}}
"""


def format_prompt(title: str, body: str) -> str:
    """Format the classification prompt with title/body and apply basic length guards."""
    safe_title = title if title else "[no title]"
    safe_body = body if body else "[no body]"

    if len(safe_title) + len(safe_body) > 2000:
        safe_body = safe_body[:500] + "..."

    return CLASSIFICATION_PROMPT.format(title=safe_title, body=safe_body)
