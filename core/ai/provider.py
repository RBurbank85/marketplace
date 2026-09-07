from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx


class AIProviderError(Exception):
    """Base exception for AI provider errors."""

    pass


class BaseAIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport

    def _validate_configuration(self, *, api_key_required: bool = False) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise AIProviderError("AI provider model must be configured")
        if api_key_required and not self.api_key:
            raise AIProviderError("AI provider API key must be configured")
        if self.timeout <= 0:
            raise AIProviderError("AI provider timeout must be greater than zero")
        if self.max_retries < 0:
            raise AIProviderError("AI provider max_retries cannot be negative")

    def _client(self) -> httpx.Client:
        options: dict[str, Any] = {"timeout": self.timeout}
        if self.transport is not None:
            options["transport"] = self.transport
        return httpx.Client(**options)

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt to the AI provider and return the text response."""
        pass

    def generate_json(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Send a prompt and expect a JSON response."""
        response = self.complete(prompt, **kwargs)
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                first_line, separator, remainder = cleaned.partition("\n")
                if not separator or first_line[3:].strip().lower() not in {"", "json"}:
                    raise ValueError("unsupported code fence")
                if not remainder.rstrip().endswith("```"):
                    raise ValueError("unterminated code fence")
                cleaned = remainder.rstrip()[:-3].strip()
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("response must be a JSON object")
            return parsed
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise AIProviderError(f"Failed to parse AI response as JSON: {exc}") from exc


class LocalProvider(BaseAIProvider):
    """Provider for local LLMs (e.g., Ollama)."""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self._validate_configuration()
        url = self.base_url or "http://localhost:11434/api/generate"
        payload = {"model": self.model, "prompt": prompt, "stream": False, **kwargs}

        try:
            with self._client() as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or not isinstance(result.get("response"), str):
                    raise AIProviderError("Local provider response is missing a text response")
                return result["response"]
        except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"Local provider request failed: {type(exc).__name__}") from exc


class OpenRouterProvider(BaseAIProvider):
    """Provider for OpenRouter API."""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self._validate_configuration(api_key_required=True)
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/maie-ai/maie",
            "X-Title": "MAIE",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            **kwargs,
        }

        try:
            with self._client() as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("content is not text")
                return content
        except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                f"OpenRouter provider response/request failed: {type(exc).__name__}"
            ) from exc


class HuggingFaceProvider(BaseAIProvider):
    """Provider for Hugging Face Inference API."""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self._validate_configuration(api_key_required=True)
        url = f"https://api-inference.huggingface.co/models/{self.model}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"inputs": prompt, "parameters": kwargs}

        try:
            with self._client() as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, list) or not result or not isinstance(result[0], dict):
                    raise ValueError("response must contain a generated-text object")
                generated_text = result[0].get("generated_text")
                if not isinstance(generated_text, str):
                    raise ValueError("response is missing generated_text")
                return generated_text
        except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise AIProviderError(
                f"HuggingFace provider response/request failed: {type(exc).__name__}"
            ) from exc
