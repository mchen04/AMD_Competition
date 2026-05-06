"""Intent classification step.

Sits between diagnosis and planning in ``self_heal_config``. Given the
current config, the pinned baseline (or last-known-good fallback), and the
recent activity log, decide whether the failure looks operator-driven
(record-only) or accidental (heal). The classifier is advisory: a missing
LLM key or transport hiccup must never block the heal — the rules engine
provides a deterministic fallback.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import load_config, redact_config
from .providers import classify_intent_with_provider
from .schemas import DiagnosisResult, EvidenceBundle, IntentClassification, to_jsonable
from .state import load_pinned_baseline, load_state, record_stage


def _walk(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            sub = f"{prefix}.{key}" if prefix else str(key)
            out.update(_walk(inner, sub))
        return out
    return {prefix: value}


def diff_configs(current: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    """Compare two configs as dotted-path leaf maps. Credentials are redacted first."""
    cur_red = redact_config(deepcopy(current)) if current else {}
    base_red = redact_config(deepcopy(baseline)) if baseline else {}
    cur_leaves = _walk(cur_red)
    base_leaves = _walk(base_red)
    cur_keys = set(cur_leaves)
    base_keys = set(base_leaves)
    changed = []
    for key in sorted(cur_keys & base_keys):
        if cur_leaves[key] != base_leaves[key]:
            changed.append({"path": key, "before": base_leaves[key], "after": cur_leaves[key]})
    added = [{"path": key, "after": cur_leaves[key]} for key in sorted(cur_keys - base_keys)]
    removed = [{"path": key, "before": base_leaves[key]} for key in sorted(base_keys - cur_keys)]
    return {"changed": changed, "added": added, "removed": removed}


def baseline_for_intent(config_path: str | Path) -> tuple[dict[str, Any] | None, str]:
    """Return (baseline_dict, kind) — prefer pinned, fall back to last-known-good."""
    pinned = load_pinned_baseline(config_path)
    if pinned is not None:
        return pinned, "pinned"
    state = load_state(config_path)
    lkg = state.get("last_known_good_config")
    if isinstance(lkg, dict):
        return lkg, "last_known_good"
    return None, "none"


def classify_and_record(
    config_path: str | Path,
    diagnosis: DiagnosisResult,
    evidence: EvidenceBundle,
    config: dict[str, Any],
    provider_name: str,
) -> IntentClassification:
    baseline, kind = baseline_for_intent(config_path)
    diff = diff_configs(config, baseline) if baseline is not None else {"changed": [], "added": [], "removed": []}
    state = load_state(config_path)
    activity_log = state.get("self_heal_attempts", [])
    if not isinstance(activity_log, list):
        activity_log = []
    classification = classify_intent_with_provider(
        provider_name,
        diagnosis,
        evidence,
        config,
        diff,
        activity_log,
        kind,
    )
    record_stage(
        config_path,
        "intent",
        {
            **to_jsonable(classification),
            "baseline_diff": diff,
        },
    )
    return classification


__all__ = ["classify_and_record", "diff_configs", "baseline_for_intent"]
