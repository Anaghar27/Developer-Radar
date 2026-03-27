"""Unit tests for processing components."""

import json
import re
from unittest.mock import MagicMock, patch

import numpy as np

from processing.embedder import embed_post
from processing.llm_processor import _parse_response, classify_post
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
    """format_prompt should truncate long bodies to 500 chars plus ellipsis."""
    prompt = format_prompt("Title", "x" * 3000)
    match = re.search(r"Post body: (.*)\nReturn exactly this structure:", prompt, re.DOTALL)
    assert match is not None
    assert len(match.group(1)) <= 503


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
    """classify_post should return parsed JSON when call_openrouter is mocked."""
    with patch("processing.llm_processor.call_openrouter", return_value=VALID_RESPONSE):
        result = classify_post({"title": "test", "body": "test body"}, post_id="post-1")

    assert isinstance(result, dict)
    assert {
        "sentiment",
        "emotion",
        "topic",
        "tool_mentioned",
        "controversy_score",
        "reasoning",
    }.issubset(result.keys())


def test_classify_post_3_model_fallback():
    """
    When the first two models fail, classify_post() should try the third model.
    If the third succeeds, it should return parsed output and not call insert_failed_event.
    """
    from processing.llm_processor import MODELS

    call_count = {"n": 0}
    spy = MagicMock()

    def mock_call_openrouter(prompt, model=None):
        spy(prompt, model=model)
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise Exception(f"Simulated failure for model {model}")
        return json.dumps(
            {
                "sentiment": "positive",
                "emotion": "curious",
                "topic": "Python",
                "tool_mentioned": "pytorch",
                "controversy_score": 1,
                "reasoning": "The post is positive about a Python tool.",
            }
        )

    with patch("processing.llm_processor.call_openrouter", side_effect=mock_call_openrouter):
        with patch("processing.llm_processor.insert_failed_event") as mock_dead_letter:
            result = classify_post(
                {"title": "Test post about PyTorch", "body": "Some body text here"},
                post_id="test_123",
            )
            assert result is not None
            assert result["sentiment"] == "positive"
            assert call_count["n"] == 3
            assert [call.kwargs["model"] for call in spy.call_args_list] == MODELS
            mock_dead_letter.assert_not_called()


def test_classify_post_all_models_fail_routes_to_dead_letter():
    """
    When all 3 models fail, classify_post() returns None
    and insert_failed_event is called once.
    """
    with patch("processing.llm_processor.call_openrouter", side_effect=Exception("API down")):
        with patch("processing.llm_processor.insert_failed_event") as mock_dead_letter:
            result = classify_post(
                {"title": "Test post title here", "body": "Some body text"},
                post_id="test_456",
            )
            assert result is None
            mock_dead_letter.assert_called_once()
            call_args = mock_dead_letter.call_args
            assert call_args.kwargs["event_type"] == "classification"


def test_embed_post_shape():
    """embed_post should return a 384-dimensional embedding vector."""
    fake_vector = np.zeros(384)
    with patch("processing.embedder.model.encode", return_value=fake_vector):
        result = embed_post({"title": "hello", "body": "world"})
    assert isinstance(result, list)
    assert len(result) == 384


def test_embed_post_returns_list():
    """embed_post should return a Python list rather than a numpy ndarray."""
    fake_vector = np.zeros(384)
    with patch("processing.embedder.model.encode", return_value=fake_vector):
        result = embed_post({"title": "hello", "body": "world"})
    assert isinstance(result, list)
    assert not isinstance(result, np.ndarray)
