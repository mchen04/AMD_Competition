from __future__ import annotations

import json
from typing import Any

from .base import LLMDiagnosisProvider, ProviderError


class OpenAIResponsesProvider(LLMDiagnosisProvider):
    label = "Responses API"

    def _api_key_env(self) -> str:
        return str(self.spec.get("api_key_env") or "OPENAI_API_KEY")

    def _endpoint_url(self) -> str:
        return str(self.spec["endpoint"])

    def _build_body(
        self,
        instructions: str,
        schema_name: str,
        schema: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(data, sort_keys=True)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
            "reasoning": {"effort": "low"},
            "store": False,
        }

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _extract_text(self, payload: Any, schema_name: str) -> str:
        chunks: list[str] = []
        for output in (payload or {}).get("output", []):
            if output.get("type") != "message":
                continue
            for item in output.get("content", []):
                if item.get("type") == "output_text":
                    chunks.append(str(item.get("text", "")))
        if not chunks:
            raise ProviderError("Responses API payload had no output_text")
        return "".join(chunks)
