from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import ConfigError, get_active_profile
from .schemas import RuntimeProfile, to_jsonable
from .templates import TemplateRenderError, render_template
from .transport import HTTPResult, request_json


@dataclass
class ProbeResult:
    ok: bool
    payload: Any = None
    error: str = ""
    attempts: int = 1
    status_code: int | None = None


class ModelProviderAdapter(Protocol):
    profile: RuntimeProfile

    def models(self) -> ProbeResult:
        ...

    def chat_completion(self) -> ProbeResult:
        ...

    def tool_call(self) -> ProbeResult:
        ...


class OpenAICompatibleAdapter:
    def __init__(self, config_path: str | Path, config: dict[str, Any]) -> None:
        self.config_path = Path(config_path)
        self.config = config
        self.profile = get_active_profile(config)

    def models(self) -> ProbeResult:
        result = request_json(
            "GET",
            f"{self.profile.base_url.rstrip('/')}/models",
            timeout=self.profile.request_timeout_seconds,
            retry=self.profile.retry,
        )
        return _probe_from_http(result)

    def chat_completion(self) -> ProbeResult:
        try:
            prompt = self._render("health_chat", {"probe": "health_chat"})
        except TemplateRenderError as exc:
            return ProbeResult(ok=False, error=str(exc))
        payload = {
            "model": self.profile.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": int(self.profile.validation.get("health_max_tokens", 32)),
        }
        if self.profile.stream:
            payload["stream"] = True
        result = request_json(
            "POST",
            f"{self.profile.base_url.rstrip('/')}/chat/completions",
            payload=payload,
            timeout=self.profile.request_timeout_seconds,
            retry=self.profile.retry,
        )
        probe = _probe_from_http(result)
        if not probe.ok:
            return probe
        validation_error = _validate_chat_response(probe.payload, self.profile)
        if validation_error:
            return ProbeResult(
                ok=False,
                payload=probe.payload,
                error=validation_error,
                attempts=probe.attempts,
                status_code=probe.status_code,
            )
        return probe

    def tool_call(self) -> ProbeResult:
        try:
            prompt = self._render("tool_call", {"probe": "tool_call", "tool": {"name": "rocm_doctor_ping"}})
        except TemplateRenderError as exc:
            return ProbeResult(ok=False, error=str(exc))
        payload = {
            "model": self.profile.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "rocm_doctor_ping",
                        "description": "Deterministic ROCm Doctor tool-call check.",
                        "parameters": {
                            "type": "object",
                            "properties": {"status": {"type": "string"}},
                            "required": ["status"],
                        },
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "rocm_doctor_ping"},
            },
            "temperature": 0,
        }
        result = request_json(
            "POST",
            f"{self.profile.base_url.rstrip('/')}/chat/completions",
            payload=payload,
            timeout=self.profile.request_timeout_seconds,
            retry=self.profile.retry,
            headers={self.profile.tool_parser_header: self.profile.tool_parser},
        )
        probe = _probe_from_http(result)
        if not probe.ok:
            return probe
        validation_error = _validate_tool_call_response(probe.payload)
        if validation_error:
            return ProbeResult(
                ok=False,
                payload=probe.payload,
                error=validation_error,
                attempts=probe.attempts,
                status_code=probe.status_code,
            )
        return probe

    def _render(self, template_key: str, extra_context: dict[str, Any]) -> str:
        template_ref = self.profile.templates.get(template_key)
        if not template_ref:
            raise TemplateRenderError(f"template key is not configured: {template_key}")
        context = {
            "config": self.config,
            "provider": to_jsonable(self.profile),
            "model": {
                "id": self.profile.model_name,
                "max_context_tokens": self.profile.max_model_len,
                "safe_context_tokens": self.profile.safe_max_model_len,
            },
            "hardware": self.config.get("hardware", {}),
        }
        context.update(extra_context)
        return render_template(self.config_path, template_ref, context)


def get_model_provider_adapter(config_path: str | Path, config: dict[str, Any]) -> ModelProviderAdapter:
    profile = get_active_profile(config)
    if profile.adapter == "openai-compatible":
        return OpenAICompatibleAdapter(config_path, config)
    raise ConfigError(f"unsupported model provider adapter: {profile.adapter}")


def _probe_from_http(result: HTTPResult) -> ProbeResult:
    return ProbeResult(
        ok=result.ok,
        payload=result.payload,
        error=result.error,
        attempts=result.attempts,
        status_code=result.status_code,
    )


def _validate_chat_response(payload: Any, profile: RuntimeProfile) -> str:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return "chat response did not contain choices[0].message"
    if message.get("tool_calls"):
        return "hallucinated tool call in plain health response"
    content = str(message.get("content", ""))
    if not content.strip():
        return "empty chat response content"
    max_chars = int(profile.validation.get("max_health_response_chars", 120))
    if len(content) > max_chars:
        return f"chat response exceeded {max_chars} characters"
    repeated_limit = int(profile.validation.get("max_repeated_token_count", 8))
    tokens = content.split()
    if tokens:
        current = 1
        previous = tokens[0]
        for token in tokens[1:]:
            if token == previous:
                current += 1
                if current > repeated_limit:
                    return "repetitive output loop detected"
            else:
                current = 1
                previous = token
    return ""


def _validate_tool_call_response(payload: Any) -> str:
    try:
        message = payload["choices"][0]["message"]
        calls = message.get("tool_calls", [])
        first = calls[0]
        name = first["function"]["name"]
    except (KeyError, IndexError, TypeError):
        return "response did not contain a tool call"
    if name != "rocm_doctor_ping":
        return f"unexpected tool call name: {name}"
    return ""
