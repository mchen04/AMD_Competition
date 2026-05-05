from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import load_config, resolve_reports_dir
from .schemas import IncidentReport
from .state import load_state, record_stage
from .timeutil import utc_now


def generate_report(config_path: str | Path) -> tuple[IncidentReport, Path]:
    config = load_config(config_path)
    state = _report_state(load_state(config_path))
    created_at = utc_now()
    incident_id = created_at.replace(":", "").replace("-", "").replace("Z", "Z")
    reports_dir = resolve_reports_dir(config_path, config)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"incident-{incident_id}.md"
    json_path = reports_dir / f"incident-{incident_id}.json"

    markdown = _markdown(incident_id, created_at, config_path, state)
    path.write_text(markdown, encoding="utf-8")
    json_payload = {
        "incident_id": incident_id,
        "created_at": created_at,
        "config_path": str(config_path),
        "state": state,
        "report_path": str(path),
    }
    json_path.write_text(json.dumps(json_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = IncidentReport(
        incident_id=incident_id,
        created_at=created_at,
        config_path=str(config_path),
        diagnosis=state.get("diagnosis"),
        repair=state.get("repair"),
        verification=state.get("verification"),
        before_evidence=state.get("before_evidence"),
        after_evidence=state.get("after_evidence"),
        report_path=str(path),
    )
    record_stage(config_path, "last_report", {"markdown": str(path), "json": str(json_path)})
    return report, path


def _report_state(state: dict[str, Any]) -> dict[str, Any]:
    report_state = dict(state)
    self_heal = report_state.get("self_heal")
    if not isinstance(self_heal, dict):
        return report_state

    repairs = self_heal.get("repairs")
    if not report_state.get("repair") and isinstance(repairs, list) and repairs:
        last_repair = repairs[-1]
        if isinstance(last_repair, dict):
            report_state["repair"] = last_repair

    final_verification = self_heal.get("final_verification")
    if not report_state.get("verification") and isinstance(final_verification, dict):
        report_state["verification"] = final_verification

    verification = report_state.get("verification")
    if not report_state.get("after_evidence") and isinstance(verification, dict):
        evidence = verification.get("evidence")
        if isinstance(evidence, dict):
            report_state["after_evidence"] = evidence

    return report_state


def _markdown(incident_id: str, created_at: str, config_path: str | Path, state: dict[str, Any]) -> str:
    diagnosis = state.get("diagnosis") or {}
    repair = state.get("repair") or {}
    verification = state.get("verification") or {}
    before = state.get("before_evidence") or {}
    after = state.get("after_evidence") or {}
    runtime = after.get("runtime") or before.get("runtime") or {}
    skipped = runtime.get("skipped_checks") or {}
    lines = [
        "# ROCm Doctor Incident Report",
        "",
        f"- Incident ID: `{incident_id}`",
        f"- Created: `{created_at}`",
        f"- Config: `{config_path}`",
        f"- Model provider: `{runtime.get('model_provider_id', 'unknown')}`",
        f"- Provider adapter: `{runtime.get('model_provider_adapter', 'unknown')}`",
        f"- Runtime type: `{runtime.get('runtime_type', 'unknown')}`",
        f"- Skipped checks: `{', '.join(sorted(skipped)) if skipped else 'none'}`",
        f"- Failure class: `{diagnosis.get('failure_class', 'unknown')}`",
        f"- Provider: `{diagnosis.get('provider', 'unknown')}`",
        f"- Suspected cause: {diagnosis.get('suspected_cause', 'unknown')}",
        f"- Repair recipe: `{repair.get('recipe_id', '')}`",
        f"- Repair applied: `{repair.get('applied', False)}`",
        f"- Repair rejected: `{repair.get('rejected', False)}`",
        f"- Verification healthy: `{verification.get('healthy', False)}`",
        "",
        "## Evidence",
        "",
        "### Before",
        "",
        "```json",
        json.dumps(_stable_evidence(before), indent=2, sort_keys=True),
        "```",
        "",
        "### After",
        "",
        "```json",
        json.dumps(_stable_evidence(after), indent=2, sort_keys=True),
        "```",
        "",
        "## Repair Details",
        "",
        "```json",
        json.dumps(repair, indent=2, sort_keys=True),
        "```",
        "",
    ]
    return "\n".join(lines)


def _stable_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    if not evidence:
        return {}
    return {
        "health": evidence.get("health", {}),
        "endpoint": evidence.get("endpoint", {}),
        "runtime": evidence.get("runtime", {}),
    }
