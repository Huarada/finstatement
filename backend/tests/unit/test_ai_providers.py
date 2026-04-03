"""
Unit tests for the AI provider adapters.

All network calls are mocked — no real API requests are made.
Tests verify:
  - Correct provider is instantiated from key prefix (auto-detect)
  - get_provider raises ValueError for unknown names
  - Each provider correctly parses its own response shape
  - ProviderHttpError and ProviderNetworkError are raised on failures
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.application.ai_providers import (
    AnthropicProvider,
    GeminiProvider,
    OpenAiProvider,
    ProviderHttpError,
    ProviderNetworkError,
    detect_provider_from_key,
    get_provider,
)


class TestDetectProviderFromKey(unittest.TestCase):

    def test_anthropic_prefix(self):
        self.assertEqual(detect_provider_from_key("sk-ant-api03-xxx"), "anthropic")

    def test_openai_prefix(self):
        self.assertEqual(detect_provider_from_key("sk-proj-xxx"), "openai")

    def test_gemini_prefix(self):
        self.assertEqual(detect_provider_from_key("AIzaSyXXX"), "gemini")

    def test_unknown_defaults_to_anthropic(self):
        self.assertEqual(detect_provider_from_key("some-random-key"), "anthropic")


class TestGetProvider(unittest.TestCase):

    def test_returns_anthropic_instance(self):
        p = get_provider("anthropic", "sk-ant-xxx")
        self.assertIsInstance(p, AnthropicProvider)

    def test_alias_claude_returns_anthropic(self):
        p = get_provider("claude", "sk-ant-xxx")
        self.assertIsInstance(p, AnthropicProvider)

    def test_returns_openai_instance(self):
        p = get_provider("openai", "sk-xxx")
        self.assertIsInstance(p, OpenAiProvider)

    def test_returns_gemini_instance(self):
        p = get_provider("gemini", "AIzaXXX")
        self.assertIsInstance(p, GeminiProvider)

    def test_unknown_provider_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_provider("mistral", "key")
        self.assertIn("mistral", str(ctx.exception))


class TestAnthropicProvider(unittest.TestCase):

    def _make_mock_response(self, text: str):
        body = {"content": [{"text": text}]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_returns_text(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response('{"key": "value"}')
        provider = AnthropicProvider("sk-ant-test")
        result = provider.complete("test prompt")
        self.assertEqual(result, '{"key": "value"}')

    @patch("urllib.request.urlopen")
    def test_http_error_raises_provider_http_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=401, msg="Unauthorized", hdrs=None, fp=MagicMock(read=lambda: b"bad key")
        )
        provider = AnthropicProvider("bad-key")
        with self.assertRaises(ProviderHttpError) as ctx:
            provider.complete("test")
        self.assertEqual(ctx.exception.status, 401)


class TestOpenAiProvider(unittest.TestCase):

    def _make_mock_response(self, content: str):
        body = {"choices": [{"message": {"content": content}}]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_returns_text(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response('{"verdict": "COMPRAR"}')
        provider = OpenAiProvider("sk-test")
        result = provider.complete("test prompt")
        self.assertEqual(result, '{"verdict": "COMPRAR"}')


class TestGeminiProvider(unittest.TestCase):

    def _make_mock_response(self, text: str):
        body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_returns_text(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response('{"verdict": "AGUARDAR"}')
        provider = GeminiProvider("AIzaTest")
        result = provider.complete("test prompt")
        self.assertEqual(result, '{"verdict": "AGUARDAR"}')

    @patch("urllib.request.urlopen")
    def test_network_error_raises_provider_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("connection refused")
        provider = GeminiProvider("AIzaTest")
        with self.assertRaises(ProviderNetworkError):
            provider.complete("test")


if __name__ == "__main__":
    unittest.main()
