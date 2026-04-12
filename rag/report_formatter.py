"""Helpers to format saved reports into presentation-friendly markdown."""

from processing.llm_client import call_llm


def format_report_for_presentation(report_text: str, query: str, source_items: list[dict] | None = None) -> str:
    """
    Rewrite a saved report into cleaner presentation-style markdown without
    introducing new facts. Returns the original report text on failure.
    """
    source_items = source_items or []
    source_lines = []
    for idx, item in enumerate(source_items[:12], 1):
        label = str(item.get("label", "")).strip()
        url = str(item.get("url", "")).strip()
        source_lines.append(f"{idx}. {label} | {url}")

    prompt = f"""You are editing a weekly intelligence brief for a product dashboard.

Rewrite the report below into a more visually pleasing markdown format for business users.

Rules:
- Use ONLY the information already present in the report and source list.
- Do NOT introduce new claims, new statistics, or new interpretations.
- Keep it concise and polished.
- Use this structure exactly when possible:
  # Weekly Developer Radar
  ## Executive Summary
  ## Key Themes
  ## Notable Signals
  ## Watch Next Week
- Put every section heading on its own line.
- Add a blank line after each heading.
- Do not write headings inline with paragraph text.
- Use short bullets where they improve readability.
- Keep source citations like [1], [2] if they already exist.
- Return ONLY markdown.

Original query:
{query}

Original report:
{report_text}

Available sources:
{chr(10).join(source_lines)}
"""

    try:
        formatted = call_llm(
            prompt,
            provider="openai",
            model="gpt-4o-mini",
            max_tokens=900,
        ).strip()
        return formatted or report_text
    except Exception:
        return report_text
