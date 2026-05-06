from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Mapping, Protocol

from ..config import get_active_profile
from ..schemas import (
    DIAGNOSIS_JSON_SCHEMA,
    INTENT_CLASSIFIER_JSON_SCHEMA,
    REPAIR_PLAN_JSON_SCHEMA,
    DiagnosisResult,
    EvidenceBundle,
    IntentClassification,
    RepairPlan,
    RetryPolicy,
    to_jsonable,
)
from ..state import load_state
from ..templates import TemplateRenderError, render_template
from ..transport import HTTPResult, request_json


class ProviderError(RuntimeError):
    pass


class OptionalProviderUnavailable(ProviderError):
    pass


class Provider(Protocol):
    name: str

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult | Mapping[str, Any]: ...

    def plan(
        self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]
    ) -> RepairPlan | Mapping[str, Any]: ...

    def classify_intent(
        self,
        diagnosis: DiagnosisResult,
        evidence: EvidenceBundle,
        config: dict[str, Any],
        baseline_diff: dict[str, Any],
        activity_log: list[dict[str, Any]],
        baseline_kind: str,
    ) -> IntentClassification | Mapping[str, Any]: ...


class LLMDiagnosisProvider(ABC):
    """Shared invoke loop for all HTTP-backed diagnosis brains.

    Subclasses provide three small hooks:
      - _build_body(template_text, schema_name, schema, payload) -> dict
      - _build_headers() -> dict[str, str]
      - _extract_text(response_payload, schema_name) -> str
    The ABC handles render → request_json → unwrap → JSON parse → object
    validation, including OptionalProviderUnavailable when an API key env
    var is empty.
    """

    label: str = "llm"

    def __init__(self, name: str, spec: dict[str, Any]) -> None:
        self.name = name
        self.spec = spec
        env_name = self._api_key_env()
        self.api_key = os.environ.get(env_name) if env_name else None
        model_env = os.environ.get(str(spec.get("model_env", "")))
        self.model = model_env or str(spec.get("model") or self._default_model())
        if env_name and self._require_api_key() and not self.api_key:
            raise OptionalProviderUnavailable(f"{env_name} is absent")

    def _api_key_env(self) -> str:
        return str(self.spec.get("api_key_env") or "")

    def _require_api_key(self) -> bool:
        return bool(self.spec.get("require_api_key", True))

    def _default_model(self) -> str:
        return ""

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
        from ..recipes import RECIPE_REGISTRY

        payload = self._invoke(
            evidence,
            "rocm_doctor_diagnosis",
            DIAGNOSIS_JSON_SCHEMA,
            self.spec["templates"]["diagnosis_system"],
            {"evidence": to_jsonable(evidence), "known_recipes": sorted(RECIPE_REGISTRY)},
        )
        payload["provider"] = self.name
        return DiagnosisResult.from_mapping(payload, provider=self.name)

    def plan(self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]) -> RepairPlan:
        from ..recipes import RECIPE_REGISTRY

        payload = self._invoke(
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

    def classify_intent(
        self,
        diagnosis: DiagnosisResult,
        evidence: EvidenceBundle,
        config: dict[str, Any],
        baseline_diff: dict[str, Any],
        activity_log: list[dict[str, Any]],
        baseline_kind: str,
    ) -> IntentClassification:
        template_ref = (
            self.spec.get("templates", {}).get("intent_classifier")
            or "../templates/intent_classifier_system.j2"
        )
        payload = self._invoke(
            evidence,
            "rocm_doctor_intent",
            INTENT_CLASSIFIER_JSON_SCHEMA,
            template_ref,
            {
                "diagnosis": to_jsonable(diagnosis),
                "evidence": to_jsonable(evidence),
                "baseline_diff": to_jsonable(baseline_diff),
                "baseline_kind": baseline_kind,
                "activity_log": to_jsonable(activity_log),
            },
        )
        payload.setdefault("provider", self.name)
        payload.setdefault("baseline_kind", baseline_kind)
        payload.setdefault(
            "diff_path_count",
            int(len((baseline_diff or {}).get("changed", []) or [])),
        )
        return IntentClassification.from_mapping(payload, provider=self.name)

    def _invoke(
        self,
        evidence: EvidenceBundle,
        schema_name: str,
        schema: dict[str, Any],
        template_ref: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            instructions = render_template(
                evidence.config_path,
                template_ref,
                {"provider_name": self.name, "schema_name": schema_name, "data": data},
            )
        except TemplateRenderError as exc:
            raise ProviderError(str(exc)) from exc

        body = self._build_body(instructions, schema_name, schema, data)
        url = self._endpoint_url()
        headers = self._build_headers()
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
            raise ProviderError.from_http_result(result, self.label)

        text = self._extract_text(result.payload, schema_name)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.label} returned non-JSON content: {exc}") from exc
        if not isinstance(value, dict):
            raise ProviderError(f"{self.label} returned non-object JSON")
        return value

    @abstractmethod
    def _endpoint_url(self) -> str: ...

    @abstractmethod
    def _build_body(
        self,
        instructions: str,
        schema_name: str,
        schema: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]: ...

    @abstractmethod
    def _build_headers(self) -> dict[str, str]: ...

    @abstractmethod
    def _extract_text(self, payload: Any, schema_name: str) -> str: ...


def _retry_from_spec(spec: dict[str, Any]) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=int(spec["max_attempts"]),
        backoff_seconds=float(spec["backoff_seconds"]),
        retry_status_codes=[int(item) for item in spec["retry_status_codes"]],
        retry_on_timeout=bool(spec["retry_on_timeout"]),
        retry_on_invalid_json=bool(spec["retry_on_invalid_json"]),
    )


def _from_http_result(result: HTTPResult, label: str) -> ProviderError:
    return ProviderError(f"{label} request failed: {result.error}: {result.raw or result.payload}")


# Attach as classmethod so subclasses can use ProviderError.from_http_result(...).
ProviderError.from_http_result = classmethod(  # type: ignore[attr-defined]
    lambda cls, result, label: _from_http_result(result, label)
)
