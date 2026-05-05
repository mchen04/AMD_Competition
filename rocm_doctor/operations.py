from __future__ import annotations

from pathlib import Path

from .config import load_config, redact_config
from .executor import execute_plan
from .monitor import run_check
from .providers import ProviderError, diagnose_with_provider, plan_with_provider
from .schemas import DiagnosisResult, RepairResult, VerificationResult, provider_output_invalid
from .state import record_stage


def check_config(config_path: str | Path) -> tuple[object, object]:
    health, evidence = run_check(config_path)
    record_stage(config_path, "last_check", health)
    if not health.healthy:
        record_stage(config_path, "before_evidence", evidence)
    return health, evidence


def diagnose_config(config_path: str | Path, provider_name: str = "rules") -> DiagnosisResult:
    config = load_config(config_path)
    health, evidence = run_check(config_path)
    diagnosis = diagnose_with_provider(provider_name, evidence, config)
    record_stage(config_path, "last_check", health)
    record_stage(config_path, "before_evidence", evidence)
    record_stage(config_path, "diagnosis", diagnosis)
    return diagnosis


def heal_config(config_path: str | Path, provider_name: str = "rules") -> RepairResult:
    config = load_config(config_path)
    _health, evidence = run_check(config_path)
    diagnosis = diagnose_with_provider(provider_name, evidence, config)
    record_stage(config_path, "before_evidence", evidence)
    record_stage(config_path, "diagnosis", diagnosis)
    if diagnosis.failure_class in {"provider_output_invalid", "provider_skipped"}:
        result = RepairResult(
            applied=False,
            recipe_id="",
            rejected=True,
            reason=diagnosis.suspected_cause + " " + " ".join(diagnosis.evidence),
            before=redact_config(config),
            after=redact_config(config),
            rollback="No changes were made.",
        )
        record_stage(config_path, "repair", result)
        return result
    try:
        plan = plan_with_provider(provider_name, diagnosis, evidence, config)
    except ProviderError as exc:
        diagnosis = provider_output_invalid(str(exc), provider_name)
        result = RepairResult(
            applied=False,
            recipe_id="",
            rejected=True,
            reason=str(exc),
            before=redact_config(config),
            after=redact_config(config),
            rollback="No changes were made.",
        )
        record_stage(config_path, "diagnosis", diagnosis)
        record_stage(config_path, "repair", result)
        return result
    record_stage(config_path, "repair_plan", plan)
    result = execute_plan(config_path, plan)
    record_stage(config_path, "repair", result)
    return result


def verify_config(config_path: str | Path) -> VerificationResult:
    health, evidence = run_check(config_path)
    result = VerificationResult(
        healthy=health.healthy,
        checks=health.checks,
        evidence=evidence,
        message="verification passed" if health.healthy else health.summary,
    )
    record_stage(config_path, "verification", result)
    record_stage(config_path, "after_evidence", evidence)
    return result
