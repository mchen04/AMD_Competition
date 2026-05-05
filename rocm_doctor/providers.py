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
            return DiagnosisResult(
                failure_class="endpoint_unreachable",
                confidence=0.85,
                evidence=[f"GET /v1/models failed: {endpoint_bits['models'].get('error', 'unknown')}"],
                suspected_cause="Configured model endpoint is unreachable.",
                missing_evidence=["process table", "service logs"],
                recommended_recipe_ids=["restart_known_service"],
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
            return DiagnosisResult(
                failure_class="unknown_failure",
                confidence=0.7,
                evidence=[f"chat completion failed: {endpoint_bits['chat'].get('error', 'unknown')}"],
                suspected_cause="The model endpoint responded to /v1/models but did not return a valid chat completion.",
                missing_evidence=["server logs", "provider runtime status"],
                recommended_recipe_ids=["noop"],
                provider=self.name,
            )
        if not checks.get("tool_call_parser", True):
            return DiagnosisResult(
                failure_class="tool_parser_mismatch",
                confidence=0.9,
                evidence=[
                    f"tool_parser={profile.tool_parser}",
                    f"expected_tool_parser={profile.expected_tool_parser}",
                    "deterministic tool-call check failed",
                ],
                suspected_cause="Configured tool parser does not match the model/runtime expectation.",
                recommended_recipe_ids=["set_tool_parser"],
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
            rationale=diagnosis.suspected_cause,
            config_patch={"path": Path(evidence.config_path).name, "changes": changes},
            command_preview=[],
            risk_level=recipe.risk_level if recipe else "low",
            rollback=recipe.rollback_strategy if recipe else "No changes were made.",
            verification_steps=list(recipe.verification_steps) if recipe else [],
            provider=self.name,
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
