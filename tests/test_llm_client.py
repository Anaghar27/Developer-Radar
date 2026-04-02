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
