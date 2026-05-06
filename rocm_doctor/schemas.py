from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping


FAILURE_CLASSES = {
    "no_failure",
    "endpoint_broken",
    "endpoint_unreachable",
    "wrong_endpoint_port",
    "one_time_rate_limit",
    "repeated_rate_limit",
    "timeout",
    "empty_qwen_output",
    "instruction_drift",
    "repetitive_loop",
    "broken_streaming",
    "bad_template",
    "permanent_500",
    "context_length_too_large",
    "tool_parser_mismatch",
    "missing_rocm_device_flags",
    "provider_output_invalid",
    "provider_skipped",
    "invalid_config",
    "config_invalid",
    "unknown_failure",
}

RISK_LEVELS = {"none", "low", "medium", "high"}


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0
    retry_status_codes: list[int] = field(
        default_factory=lambda: [408, 409, 429, 500, 502, 503, 504]
    )
    retry_on_timeout: bool = True
    retry_on_invalid_json: bool = True


@dataclass
class RuntimeProfile:
    id: str
    adapter: str
    runtime_type: str
    endpoint_protocol: str
    model_name: str
    base_url: str
    expected_base_url: str
    wrong_base_url: str
    capabilities: dict[str, bool]
    max_model_len: int
    safe_max_model_len: int
    request_timeout_seconds: float
    retry: RetryPolicy
    stream: bool
    templates: dict[str, Any]
    tool_parser: str
    expected_tool_parser: str
    tool_parser_header: str
    tool_check_enabled: bool
    health_probes: list[str] = field(default_factory=list)
    known_failure_signatures: dict[str, list[str]] = field(default_factory=dict)
    safe_repair_recipes: list[str] = field(default_factory=list)
    skip_reasons: dict[str, str] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    healthy: bool
    checks: dict[str, bool]
    errors: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class EvidenceBundle:
    collected_at: str
    config_path: str
    config_snapshot: dict[str, Any]
    endpoint: dict[str, Any]
    runtime: dict[str, Any]
    logs: list[str]
    health: HealthCheckResult


@dataclass
class DiagnosisResult:
    failure_class: str
    confidence: float
    evidence: list[str]
    suspected_cause: str
    missing_evidence: list[str] = field(default_factory=list)
    recommended_recipe_ids: list[str] = field(default_factory=list)
    provider: str = "rules"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], provider: str = "unknown") -> "DiagnosisResult":
        required = ["failure_class", "confidence", "evidence", "suspected_cause"]
        _require_keys(value, required, "DiagnosisResult")
        failure_class = _string(value["failure_class"], "failure_class")
        if failure_class not in FAILURE_CLASSES:
            raise SchemaError(f"unknown failure_class: {failure_class}")
        confidence = float(value["confidence"])
        if confidence < 0 or confidence > 1:
            raise SchemaError("confidence must be between 0 and 1")
        return cls(
            failure_class=failure_class,
            confidence=confidence,
            evidence=_string_list(value["evidence"], "evidence"),
            suspected_cause=_string(value["suspected_cause"], "suspected_cause"),
            missing_evidence=_string_list(value.get("missing_evidence", []), "missing_evidence"),
            recommended_recipe_ids=_string_list(
                value.get("recommended_recipe_ids", []), "recommended_recipe_ids"
            ),
            provider=_string(value.get("provider", provider), "provider"),
        )


@dataclass
class RepairPlan:
    recipe_id: str
    rationale: str
    config_patch: dict[str, Any] = field(default_factory=dict)
    template_patch: dict[str, Any] = field(default_factory=dict)
    state_patch: dict[str, Any] = field(default_factory=dict)
    command_preview: list[str] = field(default_factory=list)
    risk_level: str = "low"
    rollback: str = ""
    verification_steps: list[str] = field(default_factory=list)
    provider: str = "rules"
    failure_class: str = ""
    repairable: bool = True
    expected_success_signal: str = ""
    unrecoverable_reason: str = ""
    recipe_id_sequence: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], provider: str = "unknown") -> "RepairPlan":
        required = ["recipe_id", "rationale", "risk_level", "rollback", "verification_steps"]
        _require_keys(value, required, "RepairPlan")
        risk_level = _string(value["risk_level"], "risk_level")
        if risk_level not in RISK_LEVELS:
            raise SchemaError(f"unknown risk_level: {risk_level}")
        patch = value.get("config_patch", {})
        if not isinstance(patch, dict):
            raise SchemaError("config_patch must be an object")
        template_patch = value.get("template_patch", {})
        if not isinstance(template_patch, dict):
            raise SchemaError("template_patch must be an object")
        state_patch = value.get("state_patch", {})
        if not isinstance(state_patch, dict):
            raise SchemaError("state_patch must be an object")
        return cls(
            recipe_id=_string(value["recipe_id"], "recipe_id"),
            rationale=_string(value["rationale"], "rationale"),
            config_patch=dict(patch),
            template_patch=dict(template_patch),
            state_patch=dict(state_patch),
            command_preview=_string_list(value.get("command_preview", []), "command_preview"),
            risk_level=risk_level,
            rollback=_string(value["rollback"], "rollback"),
            verification_steps=_string_list(value["verification_steps"], "verification_steps"),
            provider=_string(value.get("provider", provider), "provider"),
            failure_class=_string(value.get("failure_class", ""), "failure_class"),
            repairable=bool(value.get("repairable", True)),
            expected_success_signal=_string(value.get("expected_success_signal", ""), "expected_success_signal"),
            unrecoverable_reason=_string(value.get("unrecoverable_reason", ""), "unrecoverable_reason"),
            recipe_id_sequence=_string_list(
                value.get("recipe_id_sequence", []), "recipe_id_sequence"
            ),
        )


@dataclass
class RepairResult:
    applied: bool
    recipe_id: str
    changed_paths: list[str] = field(default_factory=list)
    rejected: bool = False
    reason: str = ""
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    rollback: str = ""
    rolled_back: bool = False
    failure_class: str = ""
    verification_message: str = ""
    learned: bool = False
    applied_recipe_ids: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    healthy: bool
    checks: dict[str, bool]
    evidence: EvidenceBundle
    message: str = ""


@dataclass
class SelfHealResult:
    healthy: bool
    recovered: bool
    attempts: int
    unrecoverable: bool = False
    reason: str = ""
    repairs: list[RepairResult] = field(default_factory=list)
    final_verification: VerificationResult | None = None


@dataclass
class IncidentReport:
    incident_id: str
    created_at: str
    config_path: str
    diagnosis: DiagnosisResult | dict[str, Any] | None
    repair: RepairResult | dict[str, Any] | None
    verification: VerificationResult | dict[str, Any] | None
    before_evidence: EvidenceBundle | dict[str, Any] | None
    after_evidence: EvidenceBundle | dict[str, Any] | None
    report_path: str = ""


class SchemaError(ValueError):
    pass


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def provider_output_invalid(reason: str, provider: str) -> DiagnosisResult:
    return DiagnosisResult(
        failure_class="provider_output_invalid",
        confidence=1.0,
        evidence=[reason],
        suspected_cause="Provider returned output that failed schema or safety validation.",
        missing_evidence=[],
        recommended_recipe_ids=[],
        provider=provider,
    )


def provider_skipped(reason: str, provider: str) -> DiagnosisResult:
    return DiagnosisResult(
        failure_class="provider_skipped",
        confidence=1.0,
        evidence=[reason],
        suspected_cause="Optional provider is unavailable in this environment.",
        missing_evidence=[],
        recommended_recipe_ids=[],
        provider=provider,
    )


def _require_keys(value: Mapping[str, Any], keys: list[str], label: str) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        raise SchemaError(f"{label} missing required keys: {', '.join(missing)}")


def _string(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{key} must be a string")
    return value


def _string_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaError(f"{key} must be a list of strings")
    return list(value)


DIAGNOSIS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "failure_class": {"type": "string", "enum": sorted(FAILURE_CLASSES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "suspected_cause": {"type": "string"},
        "missing_evidence": {"type": "array", "items": {"type": "string"}},
        "recommended_recipe_ids": {"type": "array", "items": {"type": "string"}},
        "provider": {"type": "string"},
    },
    "required": [
        "failure_class",
        "confidence",
        "evidence",
        "suspected_cause",
        "missing_evidence",
        "recommended_recipe_ids",
        "provider",
    ],
}


REPAIR_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recipe_id": {"type": "string"},
        "recipe_id_sequence": {"type": "array", "items": {"type": "string"}},
        "failure_class": {"type": "string"},
        "repairable": {"type": "boolean"},
        "rationale": {"type": "string"},
        "config_patch": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "path": {"type": "string"},
                "changes": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {},
                    "required": [],
                },
            },
        },
        "template_patch": {"type": "object", "additionalProperties": True},
        "state_patch": {"type": "object", "additionalProperties": True},
        "command_preview": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": sorted(RISK_LEVELS)},
        "rollback": {"type": "string"},
        "verification_steps": {"type": "array", "items": {"type": "string"}},
        "expected_success_signal": {"type": "string"},
        "unrecoverable_reason": {"type": "string"},
        "provider": {"type": "string"},
    },
    "required": [
        "recipe_id",
        "recipe_id_sequence",
        "failure_class",
        "repairable",
        "rationale",
        "config_patch",
        "template_patch",
        "state_patch",
        "command_preview",
        "risk_level",
        "rollback",
        "verification_steps",
        "expected_success_signal",
        "unrecoverable_reason",
        "provider",
    ],
}
