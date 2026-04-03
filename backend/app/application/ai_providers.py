"""
AI Provider Adapters — Strategy Pattern.

FIX v2.1:
  - OpenAI: added system message (required for json_object response_format)
  - OpenAI: default tokens raised to 4000 (2000 insufficient for full schema)
  - Gemini: responseMimeType set to application/json for consistent parsing
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional


class AiProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 4000) -> str:
        """Send a prompt and return the raw text response."""


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

class AnthropicProvider(AiProvider):
    _API_URL = "https://api.anthropic.com/v1/messages"
    _DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self._key = api_key
        self._model = model or self._DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "anthropic"

    def complete(self, prompt: str, max_tokens: int = 4000) -> str:
        payload = json.dumps({
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            self._API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        return self._send(req)

    def _send(self, req: urllib.request.Request) -> str:
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read())
            return body["content"][0]["text"]
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:500].decode("utf-8", errors="replace")
            raise ProviderHttpError(self.name, exc.code, detail) from exc
        except Exception as exc:
            raise ProviderNetworkError(self.name, str(exc)) from exc


# ---------------------------------------------------------------------------
# OpenAI (GPT)
# ---------------------------------------------------------------------------

class OpenAiProvider(AiProvider):
    _API_URL = "https://api.openai.com/v1/chat/completions"
    _DEFAULT_MODEL = "gpt-4o"

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self._key = api_key
        self._model = model or self._DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "openai"

    def complete(self, prompt: str, max_tokens: int = 4000) -> str:
        # OpenAI's json_object response_format REQUIRES the word "json" to appear
        # in the messages — we use a system message to guarantee this, and to
        # prime the model to return valid JSON without markdown fences.
        system_msg = (
            "Você é um Analista de Equity Research Sênior e Gestor de Portfólio de um banco de investimentos global. "
            "Sua análise deve ser rigorosa, cética, baseada em fundamentos e focada em geração de caixa, "
            "vantagens competitivas sustentáveis (moats), alocação de capital e riscos ocultos. "
            "Avalie os dados com a frieza, precisão e exigência de um investidor institucional. "
            "Responda SEMPRE com JSON válido e puro — sem markdown, sem blocos de código, "
            "sem texto fora do objeto JSON. O JSON deve seguir exatamente o schema solicitado."
        )

        payload = json.dumps({
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }).encode()

        req = urllib.request.Request(
            self._API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read())
            return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:500].decode("utf-8", errors="replace")
            raise ProviderHttpError(self.name, exc.code, detail) from exc
        except Exception as exc:
            raise ProviderNetworkError(self.name, str(exc)) from exc


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiProvider(AiProvider):
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    _DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self._key = api_key
        self._model = model or self._DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "gemini"

    def complete(self, prompt: str, max_tokens: int = 4000) -> str:
        url = f"{self._BASE_URL}/{self._model}:generateContent?key={self._key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",  # force JSON output
            },
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read())
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:500].decode("utf-8", errors="replace")
            raise ProviderHttpError(self.name, exc.code, detail) from exc
        except Exception as exc:
            raise ProviderNetworkError(self.name, str(exc)) from exc


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"[{provider}] {reason}")


class ProviderHttpError(ProviderError):
    def __init__(self, provider: str, status: int, detail: str) -> None:
        self.status = status
        super().__init__(provider, f"HTTP {status}: {detail}")


class ProviderNetworkError(ProviderError):
    pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, type[AiProvider]] = {
    "anthropic": AnthropicProvider,
    "claude":    AnthropicProvider,
    "openai":    OpenAiProvider,
    "gpt":       OpenAiProvider,
    "gemini":    GeminiProvider,
    "google":    GeminiProvider,
}


def get_provider(provider_name: str, api_key: str) -> AiProvider:
    cls = _PROVIDER_MAP.get(provider_name.lower())
    if cls is None:
        supported = ", ".join(sorted(_PROVIDER_MAP.keys()))
        raise ValueError(f"Unknown AI provider '{provider_name}'. Supported: {supported}")
    return cls(api_key)


def detect_provider_from_key(api_key: str) -> str:
    key = api_key.strip()
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("sk-") and not key.startswith("sk-ant-"):
        return "openai"
    if key.startswith("AIza"):
        return "gemini"
    return "anthropic"
