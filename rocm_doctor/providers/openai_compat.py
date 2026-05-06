from __future__ import annotations

import json
from typing import Any

from .base import LLMDiagnosisProvider, ProviderError


class OpenAICompatibleDiagnosisProvider(LLMDiagnosisProvider):
    """Diagnosis brain over any OpenAI Chat Completions-compatible endpoint.

    Targets servers that implement ``POST {base_url}/chat/completions`` —
    OpenRouter, vLLM, LM Studio, Ollama's /v1, Together, etc.
    """

    label = "OpenAI-compatible"

    def _api_key_env(self) -> str:
        return str(self.spec.get("api_key_env") or "OPENAI_API_KEY")

    def _default_model(self) -> str:
        return "gpt-4o-mini"

    def _endpoint_url(self) -> str:
        base_url = str(self.spec.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        return str(self.spec.get("endpoint") or f"{base_url}/chat/completions")

    def _build_body(
        self,
        instructions: str,
        schema_name: str,
        schema: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(data, sort_keys=True)},
            ],
        }
        if bool(self.spec.get("supports_json_schema", True)):
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        elif bool(self.spec.get("supports_json_object", True)):
            body["response_format"] = {"type": "json_object"}
        max_tokens = self.spec.get("max_tokens")
        if max_tokens is not None:
            body["max_tokens"] = int(max_tokens)
        return body

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for key, value in (self.spec.get("extra_headers") or {}).items():
            headers[str(key)] = str(value)
        return headers

    def _extract_text(self, payload: Any, schema_name: str) -> str:
        if not isinstance(payload, dict):
            raise ProviderError("OpenAI-compatible payload was not a JSON object")
        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError("OpenAI-compatible payload had no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            chunks = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
            text = "".join(chunks).strip()
            if text:
                return text
        if isinstance(content, str) and content.strip():
            return content
        raise ProviderError("OpenAI-compatible payload had no message content")
