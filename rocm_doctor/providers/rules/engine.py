"""Declarative rules engine for the rules-based diagnosis provider.

Reads ``rules.yaml`` next to this module and evaluates the first matching
rule against the evidence bundle. The engine handles four "dynamic"
emit shapes that need lightweight Python (rate-limit class selection,
chat-timeout recipe selection, tool-parser recipe selection) — everything
else is plain interpolated strings + recipe lists from YAML.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any

import yaml

from ...config import get_active_profile
from ...recipes import RECIPE_REGISTRY, global_allowlisted_paths
from ...schemas import DiagnosisResult, EvidenceBundle, IntentClassification, RuntimeProfile


_RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Any]:
    raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"{_RULES_PATH} must be a YAML object")
    raw.setdefault("rules", [])
    raw.setdefault("default_emit", {})
    return raw


class RulesProvider:
    def __init__(self, name: str = "rules") -> None:
        self.name = name

    def diagnose(self, evidence: EvidenceBundle, config: dict[str, Any]) -> DiagnosisResult:
        return evaluate_rules(evidence, config, self.name)

    def classify_intent(
        self,
        diagnosis: DiagnosisResult,
        evidence: EvidenceBundle,
        config: dict[str, Any],
        baseline_diff: dict[str, Any],
        activity_log: list[dict[str, Any]],
        baseline_kind: str,
    ) -> IntentClassification:
        # Deterministic fallback per the plan: when the only changes vs the
        # baseline are paths a recipe knows how to fix, the change *is* the
        # known drift — heal it. When the diff strays outside that allowlist,
        # something the operator changed by hand is involved — record only.
        changed = list((baseline_diff or {}).get("changed", []) or [])
        added = list((baseline_diff or {}).get("added", []) or [])
        removed = list((baseline_diff or {}).get("removed", []) or [])
        diff_paths = {entry.get("path", "") for entry in changed + added + removed if isinstance(entry, dict)}
        diff_paths.discard("")
        path_count = len(diff_paths)

        if path_count == 0:
            return IntentClassification(
                intent="unintentional",
                confidence=0.85,
                reasoning="No diff between current config and baseline; failure is external drift.",
                recommend_action="heal",
                baseline_kind=baseline_kind,
                diff_path_count=0,
                provider=self.name,
            )

        allowlist = _allowlist_prefixes(config)
        in_allowlist = {path for path in diff_paths if _path_in_allowlist(path, allowlist)}
        outside = diff_paths - in_allowlist

        if outside:
            return IntentClassification(
                intent="intentional",
                confidence=0.7,
                reasoning=(
                    f"Diff touches paths outside the recipe allowlist ({sorted(outside)}); "
                    "looks like a deliberate operator change — record without auto-heal."
                ),
                recommend_action="record_only",
                baseline_kind=baseline_kind,
                diff_path_count=path_count,
                provider=self.name,
            )

        return IntentClassification(
            intent="unintentional",
            confidence=0.7,
            reasoning=(
                f"Diff lives entirely inside the deterministic-repair allowlist "
                f"({sorted(in_allowlist)}); treat as drift and heal."
            ),
            recommend_action="heal",
            baseline_kind=baseline_kind,
            diff_path_count=path_count,
            provider=self.name,
        )

    def plan(
        self, diagnosis: DiagnosisResult, evidence: EvidenceBundle, config: dict[str, Any]
    ) -> "RepairPlan":
        from ...schemas import RepairPlan

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


def evaluate_rules(evidence: EvidenceBundle, config: dict[str, Any], provider_name: str) -> DiagnosisResult:
    rules = load_rules()
    profile = get_active_profile(config)
    checks = evidence.health.checks
    endpoint = evidence.endpoint

    for rule in rules["rules"]:
        if _matches(rule.get("when", {}), checks, endpoint, profile):
            return _emit(rule.get("emit", {}), endpoint, profile, provider_name)
    return _emit(rules["default_emit"], endpoint, profile, provider_name)


def _matches(when: dict[str, Any], checks: dict[str, bool], endpoint: dict[str, Any], profile: RuntimeProfile) -> bool:
    if "check" in when:
        default = bool(when.get("check_default", False))
        actual = bool(checks.get(when["check"], default))
        if "check_value" in when and actual != bool(when["check_value"]):
            return False

    probe: dict[str, Any] | None = None
    if "probe" in when:
        probe = endpoint.get(when["probe"], {})
        if not isinstance(probe, dict):
            probe = {}

    if "endpoint_mismatch" in when:
        mismatch = profile.base_url != profile.expected_base_url
        if mismatch != bool(when["endpoint_mismatch"]):
            return False

    if "missing_rocm_flags" in when:
        has_missing = bool(endpoint.get("missing_rocm_device_flags"))
        if has_missing != bool(when["missing_rocm_flags"]):
            return False

    if probe is not None:
        if "probe_status" in when:
            if _probe_status(probe) != int(when["probe_status"]):
                return False
        if "probe_status_min" in when:
            status = _probe_status(probe)
            if status is None or status < int(when["probe_status_min"]):
                return False
        if "error_is_timeout" in when:
            if _looks_like_timeout(str(probe.get("error", ""))) != bool(when["error_is_timeout"]):
                return False
        if "error_is_template_failure" in when:
            if _looks_like_template_error(str(probe.get("error", ""))) != bool(when["error_is_template_failure"]):
                return False
        if "error_contains_any" in when:
            err = str(probe.get("error", "") or "")
            needles = [str(n) for n in when["error_contains_any"]]
            if not any(n in err for n in needles):
                return False
        if "body_contains_any" in when:
            haystack = _probe_body_text(probe).casefold()
            needles = [str(n).casefold() for n in when["body_contains_any"]]
            if not any(n in haystack for n in needles):
                return False

    return True


def _probe_body_text(probe: dict[str, Any]) -> str:
    """Return a searchable string view of the probe payload + raw body.

    Lets ``body_contains_any`` rules match server-side error fragments that
    don't surface in the harness-side ``probe.error`` (which is just
    ``HTTP 500``). Stays bounded to keep matching cheap.
    """
    parts: list[str] = []
    for field in ("response", "payload", "raw"):
        value = probe.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            parts.append(value)
            continue
        try:
            import json

            parts.append(json.dumps(value, default=str))
        except (TypeError, ValueError):
            parts.append(str(value))
    return " ".join(parts)[:2048]


def _emit(emit: dict[str, Any], endpoint: dict[str, Any], profile: RuntimeProfile, provider_name: str) -> DiagnosisResult:
    probe_name = emit.get("probe")
    probe = endpoint.get(probe_name, {}) if probe_name else {}
    if not isinstance(probe, dict):
        probe = {}

    ctx = _format_context(probe, profile, endpoint)

    failure_class = emit.get("failure_class")
    dynamic_class = emit.get("failure_class_dynamic")
    if dynamic_class == "rate_limit":
        failure_class = _rate_limit_class(probe, profile.retry.max_attempts)

    recipes = list(emit.get("recommended_recipe_ids", []))
    dynamic_recipes = emit.get("recipes_dynamic")
    if dynamic_recipes == "rate_limit":
        recipes = _rate_limit_recipes(failure_class or "")
    elif dynamic_recipes == "chat_timeout":
        recipes = ["increase_timeout", "lower_health_max_tokens"]
        if profile.stream:
            recipes.append("disable_streaming")
    elif dynamic_recipes == "tool_parser":
        recipes = ["set_tool_parser"]
        if profile.runtime_type in {"ollama", "harness-test", "fake"}:
            recipes.append("disable_tool_probe_for_weak_model")

    evidence = [_render(line, ctx) for line in emit.get("evidence", [])]
    suspected = _render(str(emit.get("suspected_cause", "")), ctx)
    missing = [str(item) for item in emit.get("missing_evidence", [])]
    confidence = float(emit.get("confidence", 1.0))

    return DiagnosisResult(
        failure_class=str(failure_class or "unknown_failure"),
        confidence=confidence,
        evidence=evidence,
        suspected_cause=suspected,
        missing_evidence=missing,
        recommended_recipe_ids=recipes,
        provider=provider_name,
    )


def _format_context(probe: dict[str, Any], profile: RuntimeProfile, endpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "probe": _ProbeView(probe),
        "profile": profile,
        "missing_rocm_flags_csv": ", ".join(endpoint.get("missing_rocm_device_flags", []) or []),
    }


class _ProbeView:
    """Wraps a probe dict so {probe.error} / {probe.attempts} format strings work."""

    def __init__(self, probe: dict[str, Any]) -> None:
        self._probe = probe

    def __getattr__(self, item: str) -> Any:
        if item == "error_or_unknown":
            return self._probe.get("error") or "unknown"
        return self._probe.get(item, "")


def _render(template: str, ctx: dict[str, Any]) -> str:
    if not template:
        return ""
    try:
        return Formatter().vformat(template, (), ctx)
    except (KeyError, AttributeError, IndexError):
        return template


def _probe_status(probe: dict[str, Any]) -> int | None:
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


def _rate_limit_recipes(failure_class: str) -> list[str]:
    if failure_class == "one_time_rate_limit":
        return ["retry_without_config_change"]
    return ["increase_retry_backoff", "fallback_model_provider"]


def _looks_like_timeout(error: str) -> bool:
    lowered = error.casefold()
    return "timed out" in lowered or "timeout" in lowered


def _looks_like_template_error(error: str) -> bool:
    lowered = error.casefold()
    return "template render failed" in lowered or "template does not exist" in lowered


def _allowlist_prefixes(config: dict[str, Any]) -> set[str]:
    """Allowlist for the rules-fallback intent classifier.

    Includes every recipe's resolved dotted paths plus a few cousin keys we
    know are operator-tunable equivalents (``request.timeout`` is in the
    allowlist via ``increase_timeout``; ``self_healing.max_attempts`` is the
    sibling we expect to flex with it).
    """
    paths = set(global_allowlisted_paths(config))
    paths.update(
        {
            "self_healing.max_attempts",
            "self_healing.fallback_model_provider",
        }
    )
    return paths


def _path_in_allowlist(path: str, allowlist: set[str]) -> bool:
    if path in allowlist:
        return True
    return any(path.startswith(prefix + ".") for prefix in allowlist)
