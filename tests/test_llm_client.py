from unittest.mock import MagicMock, patch

import pytest


def test_call_llm_routes_to_openrouter():
    """call_llm with provider='openrouter' calls _call_openrouter."""
    from processing.llm_client import call_llm

    with patch("processing.llm_client._call_openrouter", return_value="test response") as mock_or:
        result = call_llm("test prompt", provider="openrouter")
        assert result == "test response"
        mock_or.assert_called_once()


def test_call_llm_routes_to_openai():
    """call_llm with provider='openai' calls _call_openai."""
    from processing.llm_client import call_llm

    with patch("processing.llm_client._call_openai", return_value="openai response") as mock_oa:
        result = call_llm("test prompt", provider="openai")
        assert result == "openai response"
        mock_oa.assert_called_once()


def test_call_llm_invalid_provider():
    """call_llm raises ValueError for unknown provider."""
    from processing.llm_client import call_llm

    with pytest.raises(ValueError, match="Unknown provider"):
        call_llm("test prompt", provider="anthropic")


def test_call_llm_openrouter_fallback():
    """OpenRouter tries all models before failing."""
    from processing.llm_client import _call_openrouter

    call_count = {"n": 0}

    def mock_post(*args, **kwargs):
        call_count["n"] += 1
        mock_resp = MagicMock()
        if call_count["n"] < 3:
            mock_resp.status_code = 500
            mock_resp.raise_for_status.side_effect = Exception("Server error")
        else:
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "success on 3rd try"}}]
            }
        return mock_resp

    with patch("processing.llm_client.requests.post", side_effect=mock_post):
        result = _call_openrouter("test prompt")
        assert result == "success on 3rd try"
        assert call_count["n"] == 3


def test_get_embedding_returns_1536_dims():
    """get_embedding returns 1536-dimensional vector."""
    from processing.llm_client import get_embedding

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value.data = [MagicMock(embedding=[0.1] * 1536)]

    # OpenAI is imported locally inside get_embedding — patch at the source
    with patch("openai.OpenAI", return_value=mock_client):
        result = get_embedding("test text")
        assert len(result) == 1536
        assert isinstance(result[0], float)


def test_get_embedding_empty_text_returns_zero_vector():
    """get_embedding returns zero vector for empty text."""
    from processing.llm_client import get_embedding

    result = get_embedding("")
    assert len(result) == 1536
    assert all(v == 0.0 for v in result)


def test_call_llm_passes_model_override():
    """Model override is passed through to _call_openai correctly."""
    from processing.llm_client import call_llm

    with patch("processing.llm_client._call_openai", return_value="response") as mock_oa:
        call_llm("prompt", provider="openai", model="gpt-4o")
        call_args = mock_oa.call_args
        assert call_args.kwargs.get("model") == "gpt-4o" or (
            call_args.args and "gpt-4o" in call_args.args
        )


def test_call_llm_max_tokens_passed_through():
    """max_tokens parameter is passed to the underlying provider."""
    from processing.llm_client import call_llm

    with patch("processing.llm_client._call_openai",
               return_value="response") as mock_oa:
        call_llm("prompt", provider="openai", max_tokens=800)
        call_kwargs = mock_oa.call_args
        # max_tokens should be 800
        assert 800 in call_kwargs.args or \
               call_kwargs.kwargs.get("max_tokens") == 800


def test_openrouter_all_models_fail_raises_exception():
    """
    _call_openrouter raises Exception when all models in fallback chain fail.
    Caller must handle this exception.
    """
    from processing.llm_client import _call_openrouter

    with patch("processing.llm_client.requests.post",
               side_effect=Exception("Network error")):
        with pytest.raises(Exception, match="All OpenRouter models failed"):
            _call_openrouter("test prompt")


def test_get_embedding_truncates_long_text():
    """
    get_embedding truncates text to 8000 chars before calling OpenAI.
    Prevents token limit errors on very long posts.
    """
    from processing.llm_client import get_embedding

    long_text = "x" * 20000  # 20K chars — well over 8K limit

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value.data = [
        MagicMock(embedding=[0.1] * 1536)
    ]

    # get_embedding imports OpenAI locally — patch at the source module
    with patch("openai.OpenAI", return_value=mock_client):
        result = get_embedding(long_text)

    # Verify API was called with truncated text
    call_args = mock_client.embeddings.create.call_args
    input_text = call_args.kwargs.get("input") or call_args.args[0]
    assert len(input_text) <= 8000, \
        f"Text not truncated — sent {len(input_text)} chars to API"
    assert len(result) == 1536


def test_call_llm_openrouter_uses_default_model_when_none():
    """
    _call_openrouter uses OPENROUTER_MODELS[0] when no model specified.
    """
    from processing.llm_client import _call_openrouter, OPENROUTER_MODELS

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "response"}}]
    }

    with patch("processing.llm_client.requests.post",
               return_value=mock_resp) as mock_post:
        _call_openrouter("test prompt", model=None)

    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs.get("json", {})
    assert body.get("model") == OPENROUTER_MODELS[0]


def test_unified_client_openai_error_propagates():
    """
    OpenAI errors propagate up from call_llm so callers can handle them.
    """
    from processing.llm_client import call_llm

    with patch("processing.llm_client._call_openai",
               side_effect=Exception("OpenAI down")):
        with pytest.raises(Exception, match="OpenAI down"):
            call_llm("prompt", provider="openai")
