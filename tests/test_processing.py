"""Unit tests for processing components."""

import json
import re
from threading import Event
from unittest.mock import MagicMock, patch

from processing.embedder import embed_post
from processing.llm_processor import _parse_response, _process_single, classify_post
from processing.prompts import format_prompt

VALID_RESPONSE = json.dumps(
    {
        "sentiment": "positive",
        "emotion": "curious",
        "topic": "Python",
        "tool_mentioned": None,
        "controversy_score": 3,
        "reasoning": "The post shares a constructive technical project with a positive tone.",
    }
)


def test_format_prompt_normal():
    """format_prompt should include both title and body for normal input."""
    prompt = format_prompt("Test title", "Test body")
    assert "Test title" in prompt
    assert "Test body" in prompt


def test_format_prompt_empty_body():
    """format_prompt should substitute [no body] when body is empty."""
    prompt = format_prompt("Title", "")
    assert "[no body]" in prompt


def test_format_prompt_truncation():
    """format_prompt should truncate body to (2000 - title_len) chars plus ellipsis."""
    title = "Title"
    prompt = format_prompt(title, "x" * 3000)
    match = re.search(r"Post body: (.*)\nReturn exactly this structure:", prompt, re.DOTALL)
    assert match is not None
    expected_budget = max(200, 2000 - len(title))
    assert len(match.group(1)) <= expected_budget + 3  # +3 for "..."


def test_parse_response_valid():
    """_parse_response should return a dict with all required keys for valid JSON."""
    parsed = _parse_response(VALID_RESPONSE)
    assert parsed is not None
    assert {
        "sentiment",
        "emotion",
        "topic",
        "tool_mentioned",
        "controversy_score",
        "reasoning",
    }.issubset(parsed.keys())


def test_parse_response_with_code_fences():
    """_parse_response should parse JSON wrapped in markdown code fences."""
    raw = f"```json\n{VALID_RESPONSE}\n```"
    parsed = _parse_response(raw)
    assert isinstance(parsed, dict)


def test_parse_response_null_tool():
    """_parse_response should convert string 'null' tool values to Python None."""
    raw = json.dumps(
        {
            "sentiment": "neutral",
            "emotion": "neutral",
            "topic": "Other",
            "tool_mentioned": "null",
            "controversy_score": 0,
            "reasoning": "The post is informational and does not mention a tool.",
        }
    )
    parsed = _parse_response(raw)
    assert parsed is not None
    assert parsed["tool_mentioned"] is None


def test_parse_response_missing_key():
    """_parse_response should return None when a required key is missing."""
    raw = json.dumps(
        {
            "sentiment": "positive",
            "topic": "Python",
            "tool_mentioned": None,
            "controversy_score": 2,
            "reasoning": "The post sounds positive.",
        }
    )
    assert _parse_response(raw) is None


def test_classify_post_mocked():
    """classify_post should return parsed JSON when call_llm is mocked."""
    with patch("processing.llm_processor.call_llm", return_value=VALID_RESPONSE):
        result = classify_post({"title": "test", "body": "test body"}, post_id="post-1", openai_fallback=Event())

    assert isinstance(result, dict)
    assert {
        "sentiment",
        "emotion",
        "topic",
        "tool_mentioned",
        "controversy_score",
        "reasoning",
    }.issubset(result.keys())


def test_classify_post_invalid_response_routes_to_dead_letter():
    """
    When call_llm returns an unparseable response, classify_post() returns None
    and insert_failed_event is called once.
    """
    with patch("processing.llm_processor.call_llm", return_value="not valid json"):
        with patch("processing.llm_processor.insert_failed_event") as mock_dead_letter:
            result = classify_post(
                {"title": "Test post about PyTorch", "body": "Some body text here"},
                post_id="test_123",
                openai_fallback=Event(),
            )
            assert result is None
            mock_dead_letter.assert_called_once()
            assert mock_dead_letter.call_args.kwargs["event_type"] == "classification"


def test_classify_post_llm_failure_routes_to_dead_letter():
    """
    When call_llm raises an exception, classify_post() returns None
    and insert_failed_event is called once.
    """
    with patch("processing.llm_processor.call_llm", side_effect=Exception("API down")):
        with patch("processing.llm_processor.insert_failed_event") as mock_dead_letter:
            result = classify_post(
                {"title": "Test post title here", "body": "Some body text"},
                post_id="test_456",
                openai_fallback=Event(),
            )
            assert result is None
            mock_dead_letter.assert_called_once()
            assert mock_dead_letter.call_args.kwargs["event_type"] == "classification"


def test_process_single_treats_conflicting_insert_as_skipped():
    """A duplicate processed row should be treated as an idempotent skip, not a worker error."""
    counters = {"processed": 0, "failed": 0, "skipped": 0}
    lock = MagicMock()
    post = {"id": "post-1", "title": "Test", "body": "Body"}

    with patch("processing.llm_processor.db_client.post_is_processed", return_value=False), \
         patch("processing.llm_processor.classify_post", return_value=json.loads(VALID_RESPONSE)), \
         patch("processing.llm_processor.db_client.insert_processed_post", return_value=False):
        _process_single(
            post=post,
            index=1,
            total=1,
            lock=lock,
            counters=counters,
            openai_fallback=Event(),
        )

    assert counters == {"processed": 0, "failed": 0, "skipped": 1}


def test_embed_post_shape():
    """embed_post should return a 1536-dimensional embedding vector."""
    with patch("processing.embedder._get_embedding", return_value=[0.1] * 1536), \
         patch("processing.embedder.insert_embedding"):
        result = embed_post(post_id="p1", title="hello", body="world")
    assert isinstance(result, list)
    assert len(result) == 1536


def test_embed_post_returns_list():
    """embed_post should return a Python list."""
    with patch("processing.embedder._get_embedding", return_value=[0.1] * 1536), \
         patch("processing.embedder.insert_embedding"):
        result = embed_post(post_id="p1", title="hello", body="world")
    assert isinstance(result, list)
