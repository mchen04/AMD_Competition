from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..templates import TemplateRenderError, render_template
from .base import LLMDiagnosisProvider, ProviderError


class AnthropicProvider(LLMDiagnosisProvider):
    """Anthropic Messages API diagnosis brain via tool-use input_schema.

    Coerces schema-valid JSON via a single tool whose ``input_schema`` is
    the same JSON Schema used by the OpenAI Responses provider. Anthropic
    guarantees the model emits tool input matching the declared schema.
    """

    label = "Anthropic Messages"
    _DEFAULT_TOOL_DESCRIPTION_TEMPLATE = "../templates/anthropic_tool_description.j2"

    def _api_key_env(self) -> str:
        return str(self.spec.get("api_key_env") or "ANTHROPIC_API_KEY")

    def _default_model(self) -> str:
        return "claude-sonnet-4-6"

    def _endpoint_url(self) -> str:
        return str(self.spec.get("endpoint") or "https://api.anthropic.com/v1/messages")

    def _build_body(
        self,
        instructions: str,
        schema_name: str,
        schema: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": int(self.spec.get("max_tokens", 1024)),
            "system": instructions,
            "tools": [
                {
                    "name": schema_name,
                    "description": self._tool_description(),
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": schema_name},
            "messages": [
                {"role": "user", "content": json.dumps(data, sort_keys=True)},
            ],
        }

    def _build_headers(self) -> dict[str, str]:
        api_version = str(self.spec.get("api_version") or "2023-06-01")
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": api_version,
            "Content-Type": "application/json",
        }

    def _extract_text(self, payload: Any, schema_name: str) -> str:
        if not isinstance(payload, dict):
            raise ProviderError("Anthropic payload was not a JSON object")
        for block in payload.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == schema_name:
                value = block.get("input")
                if isinstance(value, dict):
                    return json.dumps(value)
        raise ProviderError(f"Anthropic payload had no tool_use block for {schema_name}")

    def _tool_description(self) -> str:
        ref = str(
            self.spec.get("tool_description_template") or self._DEFAULT_TOOL_DESCRIPTION_TEMPLATE
        )
        try:
            text = render_template(
                _project_anchor(),
                ref,
                {"provider_name": self.name},
            )
            if text:
                return text
        except TemplateRenderError:
            pass
        return "Return the structured ROCm Doctor result."


def _project_anchor() -> str:
    return str(Path(__file__).resolve().parent.parent.parent / "demo" / "rocm-doctor.yaml")
