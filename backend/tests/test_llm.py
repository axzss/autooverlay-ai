from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from backend.app.llm import chat_completion


def _reset_env() -> None:
    for key in [
        "AI_ROUTER_BASE_URL",
        "AI_ROUTER_API_KEY",
        "AI_ROUTER_MODEL",
        "LLM_FALLBACK_BASE_URL",
        "LLM_FALLBACK_API_KEY",
        "LLM_FALLBACK_MODEL",
    ]:
        if key in os.environ:
            del os.environ[key]


def test_primary_success() -> None:
    _reset_env()
    os.environ["AI_ROUTER_BASE_URL"] = "https://primary.test/v1"
    os.environ["AI_ROUTER_API_KEY"] = "primary-key"
    os.environ["AI_ROUTER_MODEL"] = "primary-model"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="primary-ok"))]
    )

    with patch("backend.app.llm.OpenAI", return_value=mock_client):
        assert chat_completion([{"role": "user", "content": "hi"}]) == "primary-ok"


def test_fallback_on_primary_model_not_found() -> None:
    _reset_env()
    os.environ["AI_ROUTER_BASE_URL"] = "https://primary.test/v1"
    os.environ["AI_ROUTER_API_KEY"] = "primary-key"
    os.environ["AI_ROUTER_MODEL"] = "primary-model"
    os.environ["LLM_FALLBACK_BASE_URL"] = "https://fallback.test/v1"
    os.environ["LLM_FALLBACK_API_KEY"] = "fallback-key"
    os.environ["LLM_FALLBACK_MODEL"] = "fallback-model"

    primary_client = MagicMock()
    primary_client.chat.completions.create.side_effect = Exception("404 model_not_found")

    fallback_client = MagicMock()
    fallback_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="fallback-ok"))]
    )

    with patch("backend.app.llm.OpenAI", side_effect=[primary_client, fallback_client]):
        assert chat_completion([{"role": "user", "content": "hi"}]) == "fallback-ok"
