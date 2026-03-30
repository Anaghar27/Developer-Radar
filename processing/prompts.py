"""Prompt templates for the LLM processing layer."""


CLASSIFICATION_PROMPT = """
You are analyzing a developer community post from Reddit or Hacker News.
Extract the following and return ONLY valid JSON. No explanation, no markdown, no code fences.
Post title: {title}
Post body: {body}
Return exactly this structure:
{{
"sentiment": "positive" | "negative" | "neutral",
"emotion": "excited" | "frustrated" | "skeptical" | "curious" | "hopeful" | "neutral",
"topic": "LLM" | "Agents" | "RAG" | "MLOps" | "Python" | "WebDev" | "DevTools" | "Cloud" | "Hardware" | "Security" | "Career" | "OpenSource" | "Other",
"tool_mentioned": "<specific library, framework, or product name as a string, or null if none>",
"controversy_score": <integer 0-10>,
"reasoning": "<one sentence explaining your classification>"
}}

Topic guidelines:
- LLM: language models, AI chat, GPT, Claude, Gemini, model benchmarks
- Agents: AI agents, autonomous systems, multi-agent workflows, tool use
- RAG: retrieval-augmented generation, vector search, embeddings, semantic search
- MLOps: model deployment, training pipelines, experiment tracking, monitoring
- Python: Python language, standard library, packaging, pip, conda, typing
- WebDev: web frameworks, frontend, backend APIs, React, FastAPI, databases
- DevTools: IDEs, CLIs, git, CI/CD, linters, debuggers, productivity tooling
- Cloud: AWS, GCP, Azure, serverless, containers, Kubernetes, infrastructure
- Hardware: GPUs, CPUs, edge devices, inference hardware, Apple Silicon
- Security: vulnerabilities, authentication, privacy, supply chain, exploits
- Career: jobs, interviews, salaries, layoffs, remote work, work culture
- OpenSource: open source releases, licensing, contributions, community governance
- Other: anything that does not clearly fit the above categories
"""


def format_prompt(title: str, body: str) -> str:
    """Format the classification prompt with title/body and apply basic length guards."""
    safe_title = title if title else "[no title]"
    safe_body = body if body else "[no body]"

    if len(safe_title) + len(safe_body) > 2000:
        safe_body = safe_body[:500] + "..."

    return CLASSIFICATION_PROMPT.format(title=safe_title, body=safe_body)
