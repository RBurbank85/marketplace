from __future__ import annotations

import json

import httpx
import pytest

from core.ai.provider import (
    AIProviderError,
    HuggingFaceProvider,
    LocalProvider,
    OpenRouterProvider,
)


def mock_transport(body: object, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body, request=request)

    return httpx.MockTransport(handler)


def test_local_provider_returns_text_from_valid_response() -> None:
    provider = LocalProvider("local-model", transport=mock_transport({"response": "hello"}))

    assert provider.complete("ignored prompt") == "hello"


def test_openrouter_provider_returns_nested_content() -> None:
    body = {"choices": [{"message": {"content": "hello"}}]}
    provider = OpenRouterProvider(
        "router-model", api_key="test-key", transport=mock_transport(body)
    )

    assert provider.complete("ignored prompt") == "hello"


def test_huggingface_provider_returns_generated_text() -> None:
    provider = HuggingFaceProvider(
        "hf-model", api_key="test-key", transport=mock_transport([{"generated_text": "hello"}])
    )

    assert provider.complete("ignored prompt") == "hello"


def test_missing_configuration_fails_before_network_call() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        raise AssertionError("network handler should not be called")

    provider = OpenRouterProvider("router-model", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderError, match="API key"):
        provider.complete("ignored prompt")

    assert called is False


@pytest.mark.parametrize(
    ("provider", "body"),
    [
        (LocalProvider("local-model", transport=mock_transport({"error": "bad"})), {"error": "bad"}),
        (
            OpenRouterProvider(
                "router-model",
                api_key="test-key",
                transport=mock_transport({"choices": []}),
            ),
            {"choices": []},
        ),
        (
            HuggingFaceProvider(
                "hf-model",
                api_key="test-key",
                transport=mock_transport([{}]),
            ),
            [{}],
        ),
    ],
)
def test_missing_response_fields_raise_provider_error(
    provider: LocalProvider | OpenRouterProvider | HuggingFaceProvider,
    body: object,
) -> None:
    del body

    with pytest.raises(AIProviderError):
        provider.complete("ignored prompt")


def test_http_error_is_wrapped_without_response_body() -> None:
    provider = LocalProvider("local-model", transport=mock_transport({"secret": "value"}, 503))

    with pytest.raises(AIProviderError, match="HTTPStatusError") as error:
        provider.complete("sensitive prompt")

    assert "secret" not in str(error.value)
    assert "sensitive prompt" not in str(error.value)


def test_timeout_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = LocalProvider("local-model", timeout=7, transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderError, match="ReadTimeout"):
        provider.complete("ignored prompt")


def test_malformed_json_response_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    provider = LocalProvider("local-model", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderError, match="JSONDecodeError"):
        provider.complete("ignored prompt")


@pytest.mark.parametrize("response", ['{"answer": 42}', '  ```json\n{"answer": 42}\n```  '])
def test_generate_json_accepts_plain_and_fenced_json(response: str) -> None:
    provider = LocalProvider(
        "local-model", transport=mock_transport({"response": response})
    )

    assert provider.generate_json("ignored prompt") == {"answer": 42}


def test_generate_json_rejects_non_object_json_without_echoing_response() -> None:
    response = json.dumps(["sensitive", "content"])
    provider = LocalProvider("local-model", transport=mock_transport({"response": response}))

    with pytest.raises(AIProviderError, match="JSON") as error:
        provider.generate_json("sensitive prompt")

    assert "sensitive" not in str(error.value)
    assert "sensitive prompt" not in str(error.value)
