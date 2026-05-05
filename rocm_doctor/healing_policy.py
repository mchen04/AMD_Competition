from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import get_active_profile
from .recipes import RECIPE_REGISTRY
from .schemas import DiagnosisResult, EvidenceBundle, RepairPlan
from .state import learned_recipe_ids


@dataclass(frozen=True)
class FailureTaxonomyEntry:
    failure_class: str
    description: str
    candidate_recipe_ids: tuple[str, ...]


FAILURE_TAXONOMY: dict[str, FailureTaxonomyEntry] = {
    "endpoint_broken": FailureTaxonomyEntry(
        "endpoint_broken", "endpoint URL or route is broken", ("update_endpoint_url", "fallback_model_provider")
    ),
    "wrong_endpoint_port": FailureTaxonomyEntry(
        "wrong_endpoint_port", "configured URL differs from expected URL", ("update_endpoint_url",)
    ),
    "one_time_rate_limit": FailureTaxonomyEntry(
        "one_time_rate_limit", "single observed 429", ("retry_without_config_change",)
    ),
    "repeated_rate_limit": FailureTaxonomyEntry(
        "repeated_rate_limit", "429 persisted across configured retries", ("increase_retry_backoff", "fallback_model_provider")
    ),
    "timeout": FailureTaxonomyEntry(
        "timeout", "request timed out", ("increase_timeout", "lower_health_max_tokens", "disable_streaming")
    ),
    "empty_qwen_output": FailureTaxonomyEntry(
        "empty_qwen_output", "Qwen returned no health content", ("increase_health_max_tokens", "switch_prompt_template")
    ),
    "instruction_drift": FailureTaxonomyEntry(
        "instruction_drift", "health output drifted from sentinel", ("switch_prompt_template", "tighten_expected_health_response")
    ),
    "repetitive_loop": FailureTaxonomyEntry(
        "repetitive_loop", "health output repeated in a loop", ("switch_prompt_template", "lower_health_max_tokens")
    ),
    "broken_streaming": FailureTaxonomyEntry(
        "broken_streaming", "streaming response was interrupted or malformed", ("disable_streaming",)
    ),
    "bad_template": FailureTaxonomyEntry(
        "bad_template", "configured prompt template is missing or invalid", ("switch_prompt_template",)
    ),
    "permanent_500": FailureTaxonomyEntry(
        "permanent_500", "provider returned HTTP 5xx after retries", ("fallback_model_provider", "restart_known_service")
    ),
    "invalid_config": FailureTaxonomyEntry(
        "invalid_config", "config cannot be loaded or validated", ("restore_last_known_good_config",)
    ),
    "config_invalid": FailureTaxonomyEntry(
        "config_invalid", "config cannot be loaded or validated", ("restore_last_known_good_config",)
    ),
}


def candidate_recipe_ids(
    diagnosis: DiagnosisResult,
    evidence: EvidenceBundle,
    config: dict[str, Any],
    state: dict[str, Any],
) -> list[str]:
    profile = get_active_profile(config)
    signature = failure_signature(diagnosis, evidence)
    ordered: list[str] = []
    ordered.extend(learned_recipe_ids(state, profile.id, diagnosis.failure_class, signature))
    ordered.extend(diagnosis.recommended_recipe_ids)
    taxonomy = FAILURE_TAXONOMY.get(diagnosis.failure_class)
    if taxonomy:
        ordered.extend(taxonomy.candidate_recipe_ids)
    if diagnosis.failure_class == "tool_parser_mismatch":
        ordered.extend(["set_tool_parser", "disable_tool_probe_for_weak_model"])
    if diagnosis.failure_class == "context_length_too_large":
        ordered.append("lower_max_model_len")
    if diagnosis.failure_class == "missing_rocm_device_flags":
        ordered.append("set_rocm_device_flags")
    if diagnosis.failure_class in {"endpoint_unreachable", "unknown_failure"}:
        ordered.extend(["fallback_model_provider", "restart_known_service", "noop"])

    safe = set(profile.safe_repair_recipes)
    candidates: list[str] = []
    for recipe_id in ordered:
        if recipe_id in candidates:
            continue
        if recipe_id not in RECIPE_REGISTRY:
            continue
        if recipe_id not in safe:
            continue
        candidates.append(recipe_id)
    return candidates


def repair_plan_for_recipe(
    recipe_id: str,
    diagnosis: DiagnosisResult,
    evidence: EvidenceBundle,
    config: dict[str, Any],
    provider_name: str,
) -> RepairPlan:
    recipe = RECIPE_REGISTRY[recipe_id]
    try:
        changes = recipe.build_changes(config)
    except (KeyError, TypeError, ValueError):
        changes = {}
    return RepairPlan(
        recipe_id=recipe_id,
        failure_class=diagnosis.failure_class,
        repairable=recipe_id != "noop",
        rationale=diagnosis.suspected_cause,
        config_patch={"path": Path(evidence.config_path).name, "changes": changes},
        template_patch={},
        state_patch={},
        command_preview=[],
        risk_level=recipe.risk_level,
        rollback=recipe.rollback_strategy,
        verification_steps=list(recipe.verification_steps),
        provider=provider_name,
        expected_success_signal="verification health is healthy",
        unrecoverable_reason="",
    )


def failure_signature(diagnosis: DiagnosisResult, evidence: EvidenceBundle) -> str:
    endpoint = evidence.endpoint
    for probe_name in ("models", "chat", "tool_call"):
        probe = endpoint.get(probe_name, {})
        if isinstance(probe, dict) and probe.get("error"):
            return _compact_signature(str(probe["error"]))
    if diagnosis.evidence:
        return _compact_signature(diagnosis.evidence[0])
    return diagnosis.failure_class


def applied_values(config: dict[str, Any], changed_paths: list[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for dotted_path in changed_paths:
        cursor: Any = config
        try:
            for part in dotted_path.split("."):
                cursor = cursor[part]
        except (KeyError, TypeError):
            continue
        values[dotted_path] = cursor
    return values


def _compact_signature(value: str) -> str:
    return " ".join(value.strip().split())[:240]
