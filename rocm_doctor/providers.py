from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from .config import ConfigError, get_active_profile, get_diagnosis_provider_config
from .recipes import RECIPE_REGISTRY
from .schemas import (
    DIAGNOSIS_JSON_SCHEMA,
    REPAIR_PLAN_JSON_SCHEMA,
    DiagnosisResult,
    EvidenceBundle,
    RepairPlan,
    RetryPolicy,
    SchemaError,
    provider_output_invalid,
    provider_skipped,
    to_jsonable,
)
from .state import load_state
from .templates import TemplateRenderError, render_template
from .transport import request_json


class ProviderError(RuntimeError):
    pass


class OptionalProviderUnavailable(ProviderError):
    pass


class Provider(Protocol):
    name: str

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult | Mapping[str, Any]:
        ...

    def plan(
        self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]
    ) -> RepairPlan | Mapping[str, Any]:
        ...


class RulesProvider:
    def __init__(self, name: str = "rules") -> None:
        self.name = name

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
        checks = evidence.health.checks
        profile = get_active_profile(config)
        endpoint_bits = evidence.endpoint
        models_probe = endpoint_bits.get("models", {})
        chat_probe = endpoint_bits.get("chat", {})
        tool_probe = endpoint_bits.get("tool_call", {})
        if not checks.get("endpoint_models", False):
            configured = profile.base_url
            expected = profile.expected_base_url
            if configured != expected:
                return DiagnosisResult(
                    failure_class="wrong_endpoint_port",
                    confidence=0.95,
                    evidence=[
                        f"GET /v1/models failed for {configured}",
                        f"expected endpoint is {expected}",
                    ],
                    suspected_cause="Configured endpoint URL does not match the expected endpoint.",
                    recommended_recipe_ids=["update_endpoint_url"],
                    provider=self.name,
                )
            if _probe_status(models_probe) == 429:
                failure_class = _rate_limit_class(models_probe, profile.retry.max_attempts)
                recipes = (
                    ["retry_without_config_change"]
                    if failure_class == "one_time_rate_limit"
                    else ["increase_retry_backoff", "fallback_model_provider"]
                )
                return DiagnosisResult(
                    failure_class=failure_class,
                    confidence=0.9,
                    evidence=[
                        f"GET /v1/models returned HTTP 429 after {models_probe.get('attempts', 1)} attempt(s)"
                    ],
                    suspected_cause="The provider rate-limited the health check.",
                    recommended_recipe_ids=recipes,
                    provider=self.name,
                )
            if _probe_status(models_probe) and int(_probe_status(models_probe) or 0) >= 500:
                return DiagnosisResult(
                    failure_class="permanent_500",
                    confidence=0.88,
                    evidence=[
                        f"GET /v1/models returned HTTP {models_probe.get('status_code')} "
                        f"after {models_probe.get('attempts', 1)} attempt(s)"
                    ],
                    suspected_cause="The provider returned a persistent server error.",
                    recommended_recipe_ids=["fallback_model_provider", "restart_known_service"],
                    provider=self.name,
                )
            if _looks_like_timeout(str(models_probe.get("error", ""))):
                return DiagnosisResult(
                    failure_class="timeout",
                    confidence=0.86,
                    evidence=[f"GET /v1/models timed out: {models_probe.get('error', 'unknown')}"],
                    suspected_cause="The provider did not answer before the configured timeout.",
                    recommended_recipe_ids=["increase_timeout", "increase_retry_backoff"],
                    provider=self.name,
                )
            return DiagnosisResult(
                failure_class="endpoint_unreachable",
                confidence=0.82,
                evidence=[f"GET /v1/models failed: {models_probe.get('error', 'unknown')}"],
                suspected_cause="Configured model endpoint is unreachable.",
                missing_evidence=["process table", "service logs"],
                recommended_recipe_ids=["fallback_model_provider", "restart_known_service"],
                provider=self.name,
            )
        if not checks.get("context_length", True):
            return DiagnosisResult(
                failure_class="context_length_too_large",
                confidence=0.93,
                evidence=[
                    f"max_model_len={profile.max_model_len}",
                    f"safe_max_model_len={profile.safe_max_model_len}",
                ],
                suspected_cause="Configured context length is above the active provider safety threshold.",
                recommended_recipe_ids=["lower_max_model_len"],
                provider=self.name,
            )
        if not checks.get("chat_completion", True):
            chat_error = str(chat_probe.get("error", ""))
            chat_status = _probe_status(chat_probe)
            if _looks_like_template_error(chat_error):
                return DiagnosisResult(
                    failure_class="bad_template",
                    confidence=0.94,
                    evidence=[f"health template failed: {chat_error}"],
                    suspected_cause="The configured health prompt template is missing or invalid.",
                    recommended_recipe_ids=["switch_prompt_template"],
                    provider=self.name,
                )
            if chat_status == 429:
                failure_class = _rate_limit_class(chat_probe, profile.retry.max_attempts)
                recipes = (
                    ["retry_without_config_change"]
                    if failure_class == "one_time_rate_limit"
                    else ["increase_retry_backoff", "fallback_model_provider"]
                )
                return DiagnosisResult(
                    failure_class=failure_class,
                    confidence=0.9,
                    evidence=[
                        f"POST /v1/chat/completions returned HTTP 429 after {chat_probe.get('attempts', 1)} attempt(s)"
                    ],
                    suspected_cause="The provider rate-limited the health chat request.",
                    recommended_recipe_ids=recipes,
                    provider=self.name,
                )
            if chat_status and chat_status >= 500:
                return DiagnosisResult(
                    failure_class="permanent_500",
                    confidence=0.88,
                    evidence=[
                        f"POST /v1/chat/completions returned HTTP {chat_status} "
                        f"after {chat_probe.get('attempts', 1)} attempt(s)"
                    ],
                    suspected_cause="The provider returned a persistent server error.",
                    recommended_recipe_ids=["fallback_model_provider", "restart_known_service"],
                    provider=self.name,
                )
            if _looks_like_timeout(chat_error):
                recipes = ["increase_timeout", "lower_health_max_tokens"]
                if profile.stream:
                    recipes.append("disable_streaming")
                return DiagnosisResult(
                    failure_class="timeout",
                    confidence=0.88,
                    evidence=[f"POST /v1/chat/completions timed out: {chat_error}"],
                    suspected_cause="The health chat did not complete before the configured timeout.",
                    recommended_recipe_ids=recipes,
                    provider=self.name,
                )
            if "empty chat response content" in chat_error:
                return DiagnosisResult(
                    failure_class="empty_qwen_output",
                    confidence=0.92,
                    evidence=[chat_error],
                    suspected_cause="The model returned an empty health response, often because reasoning consumed the output budget.",
                    recommended_recipe_ids=["increase_health_max_tokens", "switch_prompt_template"],
                    provider=self.name,
                )
            if "repetitive output loop detected" in chat_error:
                return DiagnosisResult(
                    failure_class="repetitive_loop",
                    confidence=0.92,
                    evidence=[chat_error],
                    suspected_cause="The model repeated tokens instead of returning the health sentinel.",
                    recommended_recipe_ids=["switch_prompt_template", "lower_health_max_tokens"],
                    provider=self.name,
                )
            if "invalid streaming JSON chunk" in chat_error or "streaming response" in chat_error:
                return DiagnosisResult(
                    failure_class="broken_streaming",
                    confidence=0.9,
                    evidence=[chat_error],
                    suspected_cause="The streaming health response was interrupted or malformed.",
                    recommended_recipe_ids=["disable_streaming"],
                    provider=self.name,
                )
            if (
                "expected health response" in chat_error
                or "chat response exceeded" in chat_error
                or "hallucinated tool call" in chat_error
            ):
                return DiagnosisResult(
                    failure_class="instruction_drift",
                    confidence=0.9,
                    evidence=[chat_error],
                    suspected_cause="The health prompt did not force the expected sentinel-only response.",
                    recommended_recipe_ids=["switch_prompt_template", "tighten_expected_health_response"],
                    provider=self.name,
                )
            return DiagnosisResult(
                failure_class="unknown_failure",
                confidence=0.7,
                evidence=[f"chat completion failed: {chat_error or 'unknown'}"],
                suspected_cause="The model endpoint responded to /v1/models but did not return a valid chat completion.",
                missing_evidence=["server logs", "provider runtime status"],
                recommended_recipe_ids=["noop"],
                provider=self.name,
            )
        if not checks.get("tool_call_parser", True):
            recipes = ["set_tool_parser"]
            if profile.runtime_type in {"ollama", "harness-test", "fake"}:
                recipes.append("disable_tool_probe_for_weak_model")
            return DiagnosisResult(
                failure_class="tool_parser_mismatch",
                confidence=0.9,
                evidence=[
                    f"tool_parser={profile.tool_parser}",
                    f"expected_tool_parser={profile.expected_tool_parser}",
                    f"deterministic tool-call check failed: {tool_probe.get('error', 'unknown')}",
                ],
                suspected_cause="Configured tool parser does not match the model/runtime expectation.",
                recommended_recipe_ids=recipes,
                provider=self.name,
            )
        if not checks.get("rocm_device_flags", True):
            return DiagnosisResult(
                failure_class="missing_rocm_device_flags",
                confidence=0.92,
                evidence=[
                    "missing required ROCm launch flags: "
                    + ", ".join(evidence.endpoint.get("missing_rocm_device_flags", []))
                ],
                suspected_cause="The launch config does not mount required ROCm device nodes.",
                recommended_recipe_ids=["set_rocm_device_flags"],
                provider=self.name,
            )
        return DiagnosisResult(
            failure_class="no_failure",
            confidence=1.0,
            evidence=["all health checks passed"],
            suspected_cause="No active failure detected.",
            recommended_recipe_ids=["noop"],
            provider=self.name,
        )

    def plan(self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]) -> RepairPlan:
        recipe_id = diagnosis.recommended_recipe_ids[0] if diagnosis.recommended_recipe_ids else "noop"
        profile = get_active_profile(config)
        if recipe_id not in profile.safe_repair_recipes:
            recipe_id = "noop"
        recipe = RECIPE_REGISTRY.get(recipe_id)
        changes = recipe.build_changes(config) if recipe else {}
        return RepairPlan(
            recipe_id=recipe_id,
            failure_class=diagnosis.failure_class,
            repairable=recipe_id != "noop",
            rationale=diagnosis.suspected_cause,
            config_patch={"path": Path(evidence.config_path).name, "changes": changes},
            template_patch={},
            state_patch={},
            command_preview=[],
            risk_level=recipe.risk_level if recipe else "low",
            rollback=recipe.rollback_strategy if recipe else "No changes were made.",
            verification_steps=list(recipe.verification_steps) if recipe else [],
            provider=self.name,
            expected_success_signal="verification health is healthy",
            unrecoverable_reason="",
        )


class FakeProvider:
    def __init__(self, name: str, spec: dict[str, Any]) -> None:
        self.name = name
        self.spec = spec
        self._rules = RulesProvider(name)

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult | Mapping[str, Any]:
        mode = self._mode()
        if mode == "invalid_schema":
            return {"failure_class": "tool_parser_mismatch"}
        diagnosis = self._rules.diagnose(evidence, config)
        diagnosis.provider = self.name
        return diagnosis

    def plan(
        self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]
    ) -> RepairPlan | Mapping[str, Any]:
        mode = self._mode()
        plan = self._rules.plan(diagnosis, evidence, config)
        plan.provider = self.name
        if mode == "unknown_recipe":
            plan.recipe_id = "unknown_recipe_id"
            return plan
        if mode == "unsafe_command":
            plan.command_preview = ["rm -rf /tmp/rocm-doctor-demo"]
            return plan
        if mode == "path_traversal":
            plan.config_patch["path"] = "../outside.yaml"
            return plan
        if mode == "credential_modification":
            plan.config_patch["changes"] = {"credentials.openai_api_key": "not-allowed"}
            return plan
        if mode == "malformed_plan":
            return {"recipe_id": "set_tool_parser"}
        return plan

    def _mode(self) -> str:
        return str(self.spec.get("mode", "normal"))


class OpenAIResponsesProvider:
    def __init__(self, name: str, spec: dict[str, Any]) -> None:
        self.name = name
        self.spec = spec
        self.api_key = os.environ.get(str(spec["api_key_env"]))
        model_env = os.environ.get(str(spec.get("model_env", "")))
        self.model = model_env or str(spec["model"])
        if not self.api_key:
            raise OptionalProviderUnavailable(f"{spec['api_key_env']} is absent")

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
        payload = self._structured_request(
            evidence,
            "rocm_doctor_diagnosis",
            DIAGNOSIS_JSON_SCHEMA,
            self.spec["templates"]["diagnosis_system"],
            {"evidence": to_jsonable(evidence), "known_recipes": sorted(RECIPE_REGISTRY)},
        )
        payload["provider"] = self.name
        return DiagnosisResult.from_mapping(payload, provider=self.name)

    def plan(self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]) -> RepairPlan:
        payload = self._structured_request(
            evidence,
            "rocm_doctor_repair_plan",
            REPAIR_PLAN_JSON_SCHEMA,
            self.spec["templates"]["repair_system"],
            {
                "diagnosis": to_jsonable(diagnosis),
                "evidence": to_jsonable(evidence),
                "provider": to_jsonable(get_active_profile(config)),
                "health": to_jsonable(evidence.health),
                "previous_attempts": load_state(evidence.config_path).get("self_heal_attempts", []),
                "learned_fixes": load_state(evidence.config_path).get("learned_fixes", {}),
                "config": to_jsonable(config),
                "developer_repair_mode": bool(config.get("self_healing", {}).get("developer_repair_mode", False)),
                "recipes": {
                    recipe_id: {
                        "config_paths": list(recipe.config_paths(config)),
                        "risk_level": recipe.risk_level,
                        "supported_failure_classes": list(recipe.supported_failure_classes),
                    }
                    for recipe_id, recipe in RECIPE_REGISTRY.items()
                },
            },
        )
        payload["provider"] = self.name
        return RepairPlan.from_mapping(payload, provider=self.name)

    def _structured_request(
        self,
        evidence: EvidenceBundle,
        name: str,
        schema: dict[str, Any],
        template_ref: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            instructions = render_template(
                evidence.config_path,
                template_ref,
                {"provider_name": self.name, "schema_name": name, "data": data},
            )
        except TemplateRenderError as exc:
            raise ProviderError(str(exc)) from exc
        body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(data, sort_keys=True)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "strict": True,
                    "schema": schema,
                }
            },
            "reasoning": {"effort": "low"},
            "store": False,
        }
        retry = _retry_from_spec(self.spec["retry"])
        result = request_json(
            "POST",
            str(self.spec["endpoint"]),
            payload=body,
            timeout=float(self.spec["timeout_seconds"]),
            retry=retry,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        if not result.ok:
            raise ProviderError(f"Responses API request failed: {result.error}: {result.raw or result.payload}")
        text = _extract_output_text(result.payload)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"OpenAI provider returned non-JSON text: {exc}") from exc
        if not isinstance(value, dict):
            raise ProviderError("OpenAI provider returned non-object JSON")
        return value


class AnthropicProvider:
    """Anthropic Messages API diagnosis brain.

    Coerces schema-valid JSON via Anthropic's tool-use API: a single tool
    whose ``input_schema`` is the same JSON Schema used by the OpenAI
    Responses provider. Anthropic guarantees the model emits tool input
    matching the declared schema, which gives us strict-equivalent
    structured output without requiring a Responses-style ``json_schema``
    response format.
    """

    DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
    DEFAULT_MODEL = "claude-sonnet-4-6"
    DEFAULT_API_VERSION = "2023-06-01"
    DEFAULT_MAX_TOKENS = 1024

    def __init__(self, name: str, spec: dict[str, Any]) -> None:
        self.name = name
        self.spec = spec
        env_name = str(spec.get("api_key_env") or "ANTHROPIC_API_KEY")
        self.api_key = os.environ.get(env_name)
        model_env = os.environ.get(str(spec.get("model_env", "")))
        self.model = model_env or str(spec.get("model") or self.DEFAULT_MODEL)
        if not self.api_key:
            raise OptionalProviderUnavailable(f"{env_name} is absent")

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
        payload = self._tool_request(
            evidence,
            "rocm_doctor_diagnosis",
            DIAGNOSIS_JSON_SCHEMA,
            self.spec["templates"]["diagnosis_system"],
            {"evidence": to_jsonable(evidence), "known_recipes": sorted(RECIPE_REGISTRY)},
        )
        payload["provider"] = self.name
        return DiagnosisResult.from_mapping(payload, provider=self.name)

    def plan(self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]) -> RepairPlan:
        payload = self._tool_request(
            evidence,
            "rocm_doctor_repair_plan",
            REPAIR_PLAN_JSON_SCHEMA,
            self.spec["templates"]["repair_system"],
            {
                "diagnosis": to_jsonable(diagnosis),
                "evidence": to_jsonable(evidence),
                "provider": to_jsonable(get_active_profile(config)),
                "health": to_jsonable(evidence.health),
                "previous_attempts": load_state(evidence.config_path).get("self_heal_attempts", []),
                "learned_fixes": load_state(evidence.config_path).get("learned_fixes", {}),
                "config": to_jsonable(config),
                "developer_repair_mode": bool(config.get("self_healing", {}).get("developer_repair_mode", False)),
                "recipes": {
                    recipe_id: {
                        "config_paths": list(recipe.config_paths(config)),
                        "risk_level": recipe.risk_level,
                        "supported_failure_classes": list(recipe.supported_failure_classes),
                    }
                    for recipe_id, recipe in RECIPE_REGISTRY.items()
                },
            },
        )
        payload["provider"] = self.name
        return RepairPlan.from_mapping(payload, provider=self.name)

    def _tool_request(
        self,
        evidence: EvidenceBundle,
        name: str,
        schema: dict[str, Any],
        template_ref: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            instructions = render_template(
                evidence.config_path,
                template_ref,
                {"provider_name": self.name, "schema_name": name, "data": data},
            )
        except TemplateRenderError as exc:
            raise ProviderError(str(exc)) from exc
        body = {
            "model": self.model,
            "max_tokens": int(self.spec.get("max_tokens", self.DEFAULT_MAX_TOKENS)),
            "system": instructions,
            "tools": [
                {
                    "name": name,
                    "description": "Return the structured ROCm Doctor result.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": name},
            "messages": [
                {"role": "user", "content": json.dumps(data, sort_keys=True)},
            ],
        }
        retry = _retry_from_spec(self.spec["retry"])
        endpoint = str(self.spec.get("endpoint") or self.DEFAULT_ENDPOINT)
        api_version = str(self.spec.get("api_version") or self.DEFAULT_API_VERSION)
        result = request_json(
            "POST",
            endpoint,
            payload=body,
            timeout=float(self.spec["timeout_seconds"]),
            retry=retry,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": api_version,
                "Content-Type": "application/json",
            },
        )
        if not result.ok:
            raise ProviderError(f"Anthropic Messages request failed: {result.error}: {result.raw or result.payload}")
        value = _extract_anthropic_tool_input(result.payload, name)
        if not isinstance(value, dict):
            raise ProviderError("Anthropic provider returned non-object tool input")
        return value


class OpenAICompatibleDiagnosisProvider:
    """Diagnosis brain over any OpenAI Chat Completions-compatible endpoint.

    Targets servers that implement ``POST {base_url}/chat/completions`` —
    OpenRouter, vLLM, LM Studio, Ollama's /v1, Together, etc. Uses
    ``response_format={"type": "json_schema", ...}`` when ``json_schema``
    capability is declared (default), and falls back to plain JSON parsing
    of ``choices[0].message.content``.
    """

    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, name: str, spec: dict[str, Any]) -> None:
        self.name = name
        self.spec = spec
        env_name = str(spec.get("api_key_env") or "OPENAI_API_KEY")
        self.api_key = os.environ.get(env_name)
        model_env = os.environ.get(str(spec.get("model_env", "")))
        self.model = model_env or str(spec.get("model") or self.DEFAULT_MODEL)
        # Allow public endpoints with no key (e.g. local vLLM / LM Studio).
        require_api_key = bool(spec.get("require_api_key", True))
        if require_api_key and not self.api_key:
            raise OptionalProviderUnavailable(f"{env_name} is absent")

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
        payload = self._chat_request(
            evidence,
            "rocm_doctor_diagnosis",
            DIAGNOSIS_JSON_SCHEMA,
            self.spec["templates"]["diagnosis_system"],
            {"evidence": to_jsonable(evidence), "known_recipes": sorted(RECIPE_REGISTRY)},
        )
        payload["provider"] = self.name
        return DiagnosisResult.from_mapping(payload, provider=self.name)

    def plan(self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]) -> RepairPlan:
        payload = self._chat_request(
            evidence,
            "rocm_doctor_repair_plan",
            REPAIR_PLAN_JSON_SCHEMA,
            self.spec["templates"]["repair_system"],
            {
                "diagnosis": to_jsonable(diagnosis),
                "evidence": to_jsonable(evidence),
                "provider": to_jsonable(get_active_profile(config)),
                "health": to_jsonable(evidence.health),
                "previous_attempts": load_state(evidence.config_path).get("self_heal_attempts", []),
                "learned_fixes": load_state(evidence.config_path).get("learned_fixes", {}),
                "config": to_jsonable(config),
                "developer_repair_mode": bool(config.get("self_healing", {}).get("developer_repair_mode", False)),
                "recipes": {
                    recipe_id: {
                        "config_paths": list(recipe.config_paths(config)),
                        "risk_level": recipe.risk_level,
                        "supported_failure_classes": list(recipe.supported_failure_classes),
                    }
                    for recipe_id, recipe in RECIPE_REGISTRY.items()
                },
            },
        )
        payload["provider"] = self.name
        return RepairPlan.from_mapping(payload, provider=self.name)

    def _chat_request(
        self,
        evidence: EvidenceBundle,
        name: str,
        schema: dict[str, Any],
        template_ref: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            instructions = render_template(
                evidence.config_path,
                template_ref,
                {"provider_name": self.name, "schema_name": name, "data": data},
            )
        except TemplateRenderError as exc:
            raise ProviderError(str(exc)) from exc
        base_url = str(self.spec.get("base_url") or self.DEFAULT_BASE_URL).rstrip("/")
        url = str(self.spec.get("endpoint") or f"{base_url}/chat/completions")
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
                    "name": name,
                    "strict": True,
                    "schema": schema,
                },
            }
        elif bool(self.spec.get("supports_json_object", True)):
            body["response_format"] = {"type": "json_object"}
        max_tokens = self.spec.get("max_tokens")
        if max_tokens is not None:
            body["max_tokens"] = int(max_tokens)
        extra_headers = self.spec.get("extra_headers") or {}
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for key, value in extra_headers.items():
            headers[str(key)] = str(value)
        retry = _retry_from_spec(self.spec["retry"])
        result = request_json(
            "POST",
            url,
            payload=body,
            timeout=float(self.spec["timeout_seconds"]),
            retry=retry,
            headers=headers,
        )
        if not result.ok:
            raise ProviderError(f"OpenAI-compatible request failed: {result.error}: {result.raw or result.payload}")
        text = _extract_chat_completion_text(result.payload)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"OpenAI-compatible provider returned non-JSON content: {exc}") from exc
        if not isinstance(value, dict):
            raise ProviderError("OpenAI-compatible provider returned non-object JSON")
        return value


def get_provider(name: str, config: dict[str, Any]) -> Provider:
    try:
        spec = get_diagnosis_provider_config(config, name)
    except ConfigError as exc:
        raise ProviderError(str(exc)) from exc
    provider_type = str(spec.get("type", name))
    if provider_type == "rules":
        return RulesProvider(name)
    if provider_type == "fake":
        return FakeProvider(name, spec)
    if provider_type == "openai-responses":
        return OpenAIResponsesProvider(name, spec)
    if provider_type == "anthropic-messages":
        return AnthropicProvider(name, spec)
    if provider_type == "openai-chat-completions":
        return OpenAICompatibleDiagnosisProvider(name, spec)
    raise ProviderError(f"unknown diagnosis provider type: {provider_type}")


def diagnose_with_provider(name: str, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
    try:
        provider = get_provider(name, config)
        raw = provider.diagnose(evidence, config)
        if isinstance(raw, DiagnosisResult):
            return raw
        return DiagnosisResult.from_mapping(raw, provider=name)
    except OptionalProviderUnavailable as exc:
        return provider_skipped(str(exc), name)
    except (ProviderError, SchemaError, TypeError, ValueError) as exc:
        return provider_output_invalid(str(exc), name)


def plan_with_provider(
    name: str, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]
) -> RepairPlan:
    try:
        provider = get_provider(name, config)
        raw = provider.plan(diagnosis, evidence, config)
    except OptionalProviderUnavailable as exc:
        raise ProviderError(str(exc)) from exc
    if isinstance(raw, RepairPlan):
        return raw
    try:
        return RepairPlan.from_mapping(raw, provider=name)
    except (SchemaError, TypeError, ValueError) as exc:
        raise ProviderError(f"provider repair plan invalid: {exc}") from exc


def _retry_from_spec(spec: dict[str, Any]) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=int(spec["max_attempts"]),
        backoff_seconds=float(spec["backoff_seconds"]),
        retry_status_codes=[int(item) for item in spec["retry_status_codes"]],
        retry_on_timeout=bool(spec["retry_on_timeout"]),
        retry_on_invalid_json=bool(spec["retry_on_invalid_json"]),
    )


def _extract_anthropic_tool_input(payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProviderError("Anthropic payload was not a JSON object")
    blocks = payload.get("content") or []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            value = block.get("input")
            if isinstance(value, dict):
                return value
    raise ProviderError(f"Anthropic payload had no tool_use block for {tool_name}")


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
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


def _extract_output_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for output in payload.get("output", []):
        if output.get("type") != "message":
            continue
        for item in output.get("content", []):
            if item.get("type") == "output_text":
                chunks.append(str(item.get("text", "")))
    if not chunks:
        raise ProviderError("Responses API payload had no output_text")
    return "".join(chunks)


def _probe_status(probe: Any) -> int | None:
    if not isinstance(probe, dict):
        return None
    status = probe.get("status_code")
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _rate_limit_class(probe: dict[str, Any], max_attempts: int) -> str:
    attempts = int(probe.get("attempts", 1) or 1)
    if attempts <= 1 and max_attempts <= 1:
        return "one_time_rate_limit"
    return "repeated_rate_limit"


def _looks_like_timeout(error: str) -> bool:
    lowered = error.casefold()
    return "timed out" in lowered or "timeout" in lowered


def _looks_like_template_error(error: str) -> bool:
    lowered = error.casefold()
    return "template render failed" in lowered or "template does not exist" in lowered
