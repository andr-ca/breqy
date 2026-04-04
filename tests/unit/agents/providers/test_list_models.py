"""Tests for M2 Phase 2: Provider list_models() — base default, copilot override, fallback dict.

Covers MDL-03, MDL-04, MDL-05 success criteria:
1. ModelProvider.list_models() is a concrete method returning [(self.model_id, self.model_id)]
2. CopilotProvider.list_models() calls GET /models with auth token
3. CopilotProvider.list_models() falls back when not authed or on HTTP error
4. PROVIDER_FALLBACK_MODELS dict has entries for all 5 providers
5. Existing tests still pass (no regressions)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# --------------------------------------------------------------------------- #
# SC-1: ModelProvider.list_models() concrete default
# --------------------------------------------------------------------------- #


class TestBaseListModels:
    """ModelProvider.list_models() returns [(self.model_id, self.model_id)]."""

    def test_default_returns_configured_model(self):
        """A concrete subclass that doesn't override list_models() returns its own model."""
        from breqy.agents.providers.base import ModelProvider, ProviderEvent, ProviderRequest

        class StubProvider(ModelProvider):
            @property
            def provider_id(self) -> str:
                return "stub"

            @property
            def model_id(self) -> str:
                return "stub-model-v1"

            @property
            def supports_tool_calls(self) -> bool:
                return False

            def stream(self, request: ProviderRequest):
                yield ProviderEvent(kind="text", text="stub")

        provider = StubProvider()
        result = provider.list_models()
        assert result == [("stub-model-v1", "stub-model-v1")]

    def test_default_returns_list_of_tuples(self):
        """Return type is list[tuple[str, str]]."""
        from breqy.agents.providers.base import ModelProvider, ProviderEvent, ProviderRequest

        class StubProvider(ModelProvider):
            @property
            def provider_id(self) -> str:
                return "test"

            @property
            def model_id(self) -> str:
                return "test-model"

            @property
            def supports_tool_calls(self) -> bool:
                return False

            def stream(self, request: ProviderRequest):
                yield ProviderEvent(kind="text", text="test")

        result = StubProvider().list_models()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], tuple)
        assert len(result[0]) == 2

    def test_list_models_is_not_abstract(self):
        """list_models() is concrete — not decorated with @abstractmethod."""
        from breqy.agents.providers.base import ModelProvider
        import inspect

        # If it were abstract, it would be in __abstractmethods__
        assert "list_models" not in ModelProvider.__abstractmethods__


# --------------------------------------------------------------------------- #
# SC-2: CopilotProvider.list_models() calls GET /models
# --------------------------------------------------------------------------- #


class TestCopilotListModels:
    """CopilotProvider.list_models() queries /models API endpoint."""

    def _make_provider(self, *, authenticator=None, client=None):
        from breqy.agents.providers.copilot import CopilotProvider

        return CopilotProvider(
            model_id="gpt-4o",
            authenticator=authenticator or MagicMock(),
            client=client or MagicMock(),
        )

    def test_returns_models_from_api(self):
        """list_models() parses API response into (id, name) pairs."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
                {
                    "id": "gpt-4o-mini",
                    "name": "GPT-4o Mini",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
                {
                    "id": "o3-mini",
                    "name": "O3 Mini",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        assert result == [
            ("gpt-4o", "GPT-4o"),
            ("gpt-4o-mini", "GPT-4o Mini"),
            ("o3-mini", "O3 Mini"),
        ]

    def test_sends_auth_header(self):
        """list_models() sends Authorization: Bearer header."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=abc;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o", "capabilities": {"type": "chat"}, "model_picker_enabled": True}
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            provider.list_models()

        call_kwargs = mock_httpx.get.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer tid=abc;exp=9999999999"

    def test_model_name_defaults_to_id(self):
        """If model has no 'name' field, use 'id' as display name."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },  # no "name" key
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        assert result == [("gpt-4o", "gpt-4o")]


# --------------------------------------------------------------------------- #
# SC-3: CopilotProvider.list_models() fallback behavior
# --------------------------------------------------------------------------- #


class TestCopilotListModelsFallback:
    """CopilotProvider.list_models() falls back on no auth or HTTP error."""

    def _make_provider(self, *, authenticator=None):
        from breqy.agents.providers.copilot import CopilotProvider

        return CopilotProvider(
            model_id="gpt-4o",
            authenticator=authenticator or MagicMock(),
            client=MagicMock(),
        )

    def test_fallback_when_no_token(self):
        """Returns configured model when authenticator has no token."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = None

        provider = self._make_provider(authenticator=auth)
        result = provider.list_models()
        assert result == [("gpt-4o", "gpt-4o")]

    def test_fallback_on_http_error(self):
        """Returns configured model on non-200 response."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        assert result == [("gpt-4o", "gpt-4o")]

    def test_fallback_on_401(self):
        """Returns configured model on 401 (expired token)."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=expired;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        assert result == [("gpt-4o", "gpt-4o")]

    def test_fallback_on_network_error(self):
        """Returns configured model when HTTP request raises."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("connection refused")
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        assert result == [("gpt-4o", "gpt-4o")]


# --------------------------------------------------------------------------- #
# SC-4: PROVIDER_FALLBACK_MODELS dict
# --------------------------------------------------------------------------- #


class TestProviderFallbackModels:
    """PROVIDER_FALLBACK_MODELS has entries for all 5 providers."""

    def test_dict_exists(self):
        from breqy.agents.providers.adapters import PROVIDER_FALLBACK_MODELS

        assert isinstance(PROVIDER_FALLBACK_MODELS, dict)

    def test_has_all_five_providers(self):
        from breqy.agents.providers.adapters import PROVIDER_FALLBACK_MODELS

        expected_providers = {"copilot", "claude", "codex", "gemini", "qwen"}
        assert set(PROVIDER_FALLBACK_MODELS.keys()) == expected_providers

    def test_each_entry_is_list_of_tuples(self):
        from breqy.agents.providers.adapters import PROVIDER_FALLBACK_MODELS

        for provider_id, models in PROVIDER_FALLBACK_MODELS.items():
            assert isinstance(models, list), f"{provider_id} value is not a list"
            assert len(models) > 0, f"{provider_id} has no models"
            for model_id, display_name in models:
                assert isinstance(model_id, str), f"{provider_id} model_id not str"
                assert isinstance(display_name, str), f"{provider_id} display_name not str"

    def test_copilot_has_gpt4o(self):
        from breqy.agents.providers.adapters import PROVIDER_FALLBACK_MODELS

        copilot_ids = [m[0] for m in PROVIDER_FALLBACK_MODELS["copilot"]]
        assert "gpt-4o" in copilot_ids

    def test_claude_has_sonnet(self):
        from breqy.agents.providers.adapters import PROVIDER_FALLBACK_MODELS

        claude_ids = [m[0] for m in PROVIDER_FALLBACK_MODELS["claude"]]
        assert "sonnet" in claude_ids


# --------------------------------------------------------------------------- #
# SC-5: Runner-based providers inherit default list_models
# --------------------------------------------------------------------------- #


class TestRunnerProviderListModels:
    """Subprocess-based providers use the default list_models() from base."""

    def test_runner_provider_has_list_models(self):
        """_BaseRunnerProvider inherits list_models from ModelProvider."""
        from breqy.agents.providers.adapters import _BaseRunnerProvider

        assert hasattr(_BaseRunnerProvider, "list_models")
        assert "list_models" not in _BaseRunnerProvider.__dict__  # not overridden


# --------------------------------------------------------------------------- #
# SC-6: CopilotProvider.list_models() filtering by capabilities
# --------------------------------------------------------------------------- #


class TestCopilotListModelsFiltering:
    """CopilotProvider.list_models() filters by capabilities and model_picker_enabled."""

    def _make_provider(self, *, authenticator=None, client=None):
        from breqy.agents.providers.copilot import CopilotProvider

        return CopilotProvider(
            model_id="gpt-4o",
            authenticator=authenticator or MagicMock(),
            client=client or MagicMock(),
        )

    def test_filters_out_non_chat_models(self):
        """Models without capabilities.type == 'chat' are excluded."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
                {
                    "id": "text-embedding-ada",
                    "name": "Ada Embedding",
                    "capabilities": {"type": "embeddings"},
                    "model_picker_enabled": True,
                },
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o" in model_ids
        assert "text-embedding-ada" not in model_ids

    def test_filters_out_model_picker_disabled(self):
        """Models with model_picker_enabled == false are excluded."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
                {
                    "id": "gpt-internal",
                    "name": "Internal",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": False,
                },
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o" in model_ids
        assert "gpt-internal" not in model_ids

    def test_graceful_with_missing_capabilities(self):
        """Models without capabilities field are excluded (defensive)."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
                {"id": "mystery", "name": "Mystery Model"},
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o" in model_ids
        assert "mystery" not in model_ids

    def test_deduplicates_by_name_keeping_highest_version(self):
        """When multiple models share a name, keep the one with highest version."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o-2024-08-06",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                    "version": "2024-08-06",
                },
                {
                    "id": "gpt-4o-2025-03-01",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                    "version": "2025-03-01",
                },
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            result = provider.list_models()

        model_ids = [m[0] for m in result]
        assert "gpt-4o-2025-03-01" in model_ids
        assert "gpt-4o-2024-08-06" not in model_ids

    def test_stores_endpoint_metadata(self):
        """list_models() stores supported_endpoints per model for routing."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                    "supported_endpoints": ["/chat/completions", "/responses"],
                },
                {
                    "id": "gpt-5.4-mini",
                    "name": "GPT-5.4 Mini",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                    "supported_endpoints": ["/responses"],
                },
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            provider.list_models()

        assert provider._model_endpoints["gpt-4o"] == ["/chat/completions", "/responses"]
        assert provider._model_endpoints["gpt-5.4-mini"] == ["/responses"]

    def test_defaults_endpoints_to_chat_completions(self):
        """Models without supported_endpoints default to /chat/completions."""
        auth = MagicMock()
        auth.get_copilot_token.return_value = "tid=test;exp=9999999999"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "capabilities": {"type": "chat"},
                    "model_picker_enabled": True,
                },
            ]
        }

        with patch("breqy.agents.providers.copilot.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            provider = self._make_provider(authenticator=auth)
            provider.list_models()

        assert provider._model_endpoints["gpt-4o"] == ["/chat/completions"]
