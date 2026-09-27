"""LLM abstraction: response parsing, error handling and key hygiene."""

from __future__ import annotations

import json
import urllib.error

import pytest

from repomind.llm import (
    EchoLLMClient,
    GeminiClient,
    LLMError,
    LLMNotConfigured,
    build_llm,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


def answer_payload(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_generate_returns_the_model_text(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = request.headers
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(answer_payload("auth lives in app/auth.py:1-10"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = GeminiClient(api_key="test-key", model="gemini-2.0-flash")
    assert client.generate("system", "user") == "auth lives in app/auth.py:1-10"
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "user"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "system"


def test_api_key_travels_in_a_header_not_the_url(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        return FakeResponse(answer_payload("ok"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    GeminiClient(api_key="super-secret").generate("s", "u")
    assert "super-secret" not in captured["url"]
    assert captured["headers"]["X-goog-api-key".lower()] == "super-secret"


def test_http_errors_do_not_leak_the_response_body(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(LLMError) as excinfo:
        GeminiClient(api_key="k").generate("s", "u")
    assert "400" in str(excinfo.value)


def test_network_errors_become_llm_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(LLMError):
        GeminiClient(api_key="k").generate("s", "u")


def test_blocked_prompts_raise_with_the_reason(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        return FakeResponse({"promptFeedback": {"blockReason": "SAFETY"}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(LLMError) as excinfo:
        GeminiClient(api_key="k").generate("s", "u")
    assert "SAFETY" in str(excinfo.value)


def test_empty_answers_raise(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        return FakeResponse(answer_payload("   "))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(LLMError):
        GeminiClient(api_key="k").generate("s", "u")


def test_client_requires_an_api_key() -> None:
    with pytest.raises(LLMNotConfigured):
        GeminiClient(api_key="")


def test_build_llm_falls_back_to_the_offline_client() -> None:
    client = build_llm("gemini", "", "gemini-2.0-flash")
    assert isinstance(client, EchoLLMClient)
    assert "no llm provider is configured" in client.generate("s", "u").lower()


def test_build_llm_rejects_unknown_providers() -> None:
    with pytest.raises(LLMNotConfigured):
        build_llm("mystery-provider", "key", "model")


def test_build_llm_returns_gemini_when_configured() -> None:
    assert isinstance(build_llm("gemini", "key", "gemini-2.0-flash"), GeminiClient)
