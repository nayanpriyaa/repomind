"""LLM abstraction."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models"
)


class LLMError(RuntimeError):
    """Raised when the provider fails or returns an unusable response."""


class LLMNotConfigured(LLMError):
    """Raised when an LLM provider is not configured."""


@runtime_checkable
class LLMClient(Protocol):

    @property
    def model(self) -> str:
        ...

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        ...


class GeminiClient:

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout: float = 60.0,
        max_output_tokens: int = 1024,
        temperature: float = 0.1,
        endpoint: str = GEMINI_ENDPOINT,
    ) -> None:
        if not api_key:
            raise LLMNotConfigured(
                "GEMINI_API_KEY is not set"
            )

        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._endpoint = endpoint.rstrip("/")

    @property
    def model(self) -> str:
        return self._model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": self._max_output_tokens,
            },
        }

        response = self._post(
            f"{self._endpoint}/{self._model}:generateContent",
            payload,
        )

        return _extract_text(response)

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self._timeout,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            raise LLMError(
                f"gemini request failed with status {exc.code}"
            ) from None

        except urllib.error.URLError as exc:
            raise LLMError(
                f"gemini request failed: {exc.reason}"
            ) from None

        except json.JSONDecodeError as exc:
            raise LLMError(
                "gemini returned a malformed response"
            ) from exc


class OllamaClient:
    """Local Ollama client using /api/generate."""

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
        max_output_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> None:

        if not model.strip():
            raise LLMNotConfigured(
                "OLLAMA_MODEL is not set"
            )

        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature

    @property
    def model(self) -> str:
        return self._model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:

        payload = {
            "model": self._model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_output_tokens,
            },
        }

        response = self._post(
            f"{self._base_url}/api/generate",
            payload,
        )

        text = str(
            response.get("response", "")
        ).strip()

        if not text:
            raise LLMError(
                "ollama returned an empty answer"
            )

        return text

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json"
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self._timeout,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            raise LLMError(
                f"ollama request failed with status {exc.code}"
            ) from None

        except urllib.error.URLError as exc:
            raise LLMError(
                f"ollama request failed: {exc.reason}"
            ) from None

        except json.JSONDecodeError as exc:
            raise LLMError(
                "ollama returned a malformed response"
            ) from exc


class EchoLLMClient:

    @property
    def model(self) -> str:
        return "offline-echo"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:

        del system_prompt, user_prompt

        return (
            "No LLM provider is configured, so no generated answer "
            "is available. The retrieved source excerpts are listed "
            "under sources; configure Ollama or GEMINI_API_KEY to "
            "enable generated answers."
        )


def build_llm(
    provider: str,
    api_key: str,
    model: str,
    timeout: float = 60.0,
    max_output_tokens: int = 1024,
    ollama_base_url: str = "http://localhost:11434",
    ollama_model: str = "qwen2.5-coder:7b",
) -> LLMClient:

    normalized = provider.strip().lower()

    if normalized == "ollama":
        return OllamaClient(
            model=ollama_model,
            base_url=ollama_base_url,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
        )

    if normalized == "gemini":
        if not api_key:
            logger.warning(
                "no Gemini API key configured; "
                "using offline client"
            )
            return EchoLLMClient()

        return GeminiClient(
            api_key=api_key,
            model=model,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
        )

    if normalized in {
        "",
        "none",
        "offline",
        "echo",
    }:
        return EchoLLMClient()

    raise LLMNotConfigured(
        f"unsupported LLM provider: {provider!r}"
    )


def _extract_text(
    response: dict[str, Any],
) -> str:

    candidates = response.get("candidates") or []

    if not candidates:
        feedback = response.get(
            "promptFeedback",
            {},
        )

        reason = feedback.get(
            "blockReason",
            "no candidates returned",
        )

        raise LLMError(
            f"gemini produced no answer ({reason})"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts")
        or []
    )

    text = "".join(
        part.get("text", "")
        for part in parts
    ).strip()

    if not text:
        raise LLMError(
            "gemini returned an empty answer"
        )

    return text