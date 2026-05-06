from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import get_active_profile
from .recipes import RECIPE_REGISTRY
from .schemas import DiagnosisResult, EvidenceBundle, RepairPlan
from .state import learned_recipe_ids


@dataclass(frozen=True)
class FailureTaxonomyEntry:
    failure_class: str
    description: str
    candidate_recipe_ids: tuple[str, ...]


_FAILURES_PATH = Path(__file__).resolve().parent / "failures.yaml"


@lru_cache(maxsize=1)
def _load_taxonomy() -> dict[str, FailureTaxonomyEntry]:
    raw = yaml.safe_load(_FAILURES_PATH.read_text(encoding="utf-8")) or {}
    out: dict[str, FailureTaxonomyEntry] = {}
    for entry in raw.get("failures", []) or []:
        fc = str(entry["failure_class"])
        out[fc] = FailureTaxonomyEntry(
            failure_class=fc,
            description=str(entry.get("description", "")),
            candidate_recipe_ids=tuple(str(r) for r in entry.get("candidate_recipe_ids", []) or []),
        )
    return out


FAILURE_TAXONOMY: dict[str, FailureTaxonomyEntry] = _load_taxonomy()


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
    if diagnosis.failure_class == "rocm_oom_inference":
        ordered.extend(["lower_gpu_memory_utilization", "fallback_model_provider"])
    if diagnosis.failure_class == "max_model_len_mismatch":
        ordered.extend(["align_max_tokens_with_served", "lower_max_model_len"])
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
