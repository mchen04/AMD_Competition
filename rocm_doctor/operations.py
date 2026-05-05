from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .config import ConfigError, load_config, redact_config, save_config
from .executor import execute_plan
from .healing_policy import applied_values, candidate_recipe_ids, failure_signature, repair_plan_for_recipe
from .monitor import run_check
from .providers import ProviderError, diagnose_with_provider, plan_with_provider
from .schemas import DiagnosisResult, RepairResult, SelfHealResult, VerificationResult, provider_output_invalid
from .state import (
    load_state,
    record_last_known_good_config,
    record_stage,
    record_successful_fix,
    restore_last_known_good_config,
)


def check_config(config_path: str | Path) -> tuple[object, object]:
    health, evidence = run_check(config_path)
    record_stage(config_path, "last_check", health)
    if health.healthy:
        record_last_known_good_config(config_path, load_config(config_path))
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
    if health.healthy:
        record_last_known_good_config(config_path, load_config(config_path))
    return result


def self_heal_config(config_path: str | Path, provider_name: str = "rules") -> SelfHealResult:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        return _restore_invalid_config(config_path, str(exc))
    max_attempts = int(config.get("self_healing", {}).get("max_attempts", 3))
    repairs: list[RepairResult] = []
    last_verification: VerificationResult | None = None
    last_reason = ""
    completed_attempts = 0

    for attempt in range(1, max_attempts + 1):
        completed_attempts = attempt
        health, evidence = run_check(config_path)
        record_stage(config_path, "last_check", health)
        record_stage(config_path, "before_evidence", evidence)
        if health.healthy:
            record_last_known_good_config(config_path, load_config(config_path))
            result = SelfHealResult(
                healthy=True,
                recovered=bool(repairs),
                attempts=attempt - 1,
                repairs=repairs,
                final_verification=VerificationResult(
                    healthy=True,
                    checks=health.checks,
                    evidence=evidence,
                    message="already healthy" if not repairs else "recovered",
                ),
            )
            record_stage(config_path, "self_heal", result)
            return result

        config = load_config(config_path)
        failed_provider_id = str(config["active_model_provider"])
        diagnosis = diagnose_with_provider(provider_name, evidence, config)
        record_stage(config_path, "diagnosis", diagnosis)
        if diagnosis.failure_class in {"provider_output_invalid", "provider_skipped"}:
            result = SelfHealResult(
                healthy=False,
                recovered=False,
                attempts=attempt,
                unrecoverable=True,
                reason=diagnosis.suspected_cause + " " + " ".join(diagnosis.evidence),
                repairs=repairs,
            )
            record_stage(config_path, "self_heal", result)
            return result

        state = load_state(config_path)
        candidates = candidate_recipe_ids(diagnosis, evidence, config, state)
        attempt_record = {
            "failure_class": diagnosis.failure_class,
            "candidate_recipe_ids": candidates,
            "signature": failure_signature(diagnosis, evidence),
        }
        previous_attempts = state.get("self_heal_attempts", [])
        if not isinstance(previous_attempts, list):
            previous_attempts = []
        record_stage(config_path, "self_heal_attempts", (previous_attempts + [attempt_record])[-20:])
        record_stage(
            config_path,
            f"self_heal_attempt_{attempt}",
            attempt_record,
        )
        if not candidates:
            last_reason = f"no safe deterministic repair exists for {diagnosis.failure_class}"
            break

        for recipe_id in candidates:
            snapshot = deepcopy(load_config(config_path))
            record_stage(config_path, "repair_snapshot", redact_config(snapshot))
            plan = repair_plan_for_recipe(recipe_id, diagnosis, evidence, snapshot, provider_name)
            record_stage(config_path, "repair_plan", plan)
            repair = execute_plan(config_path, plan)
            repair.failure_class = diagnosis.failure_class
            repairs.append(repair)
            last_reason = repair.reason
            if repair.rejected:
                continue

            last_verification = verify_config(config_path)
            repair.verification_message = last_verification.message
            if last_verification.healthy:
                final_config = load_config(config_path)
                changed_values = applied_values(final_config, repair.changed_paths)
                signature = failure_signature(diagnosis, evidence)
                record_successful_fix(
                    config_path,
                    failed_provider_id,
                    diagnosis.failure_class,
                    signature,
                    recipe_id,
                    repair.changed_paths,
                    changed_values,
                )
                repair.learned = True
                result = SelfHealResult(
                    healthy=True,
                    recovered=True,
                    attempts=attempt,
                    repairs=repairs,
                    final_verification=last_verification,
                )
                record_stage(config_path, "self_heal", result)
                return result

            if repair.applied:
                save_config(config_path, snapshot)
                repair.rolled_back = True
                repair.after = redact_config(load_config(config_path))
                repair.rollback = repair.rollback or "Restored the pre-repair config snapshot."
            last_reason = last_verification.message or repair.reason

    result = SelfHealResult(
        healthy=False,
        recovered=False,
        attempts=completed_attempts,
        unrecoverable=True,
        reason=f"self-healing retry exhaustion after {completed_attempts} attempts: {last_reason}",
        repairs=repairs,
        final_verification=last_verification,
    )
    record_stage(config_path, "self_heal", result)
    return result


def _restore_invalid_config(config_path: str | Path, reason: str) -> SelfHealResult:
    before = {}
    restored = restore_last_known_good_config(config_path)
    repair = RepairResult(
        applied=restored is not None,
        recipe_id="restore_last_known_good_config",
        changed_paths=[str(config_path)] if restored is not None else [],
        rejected=restored is None,
        reason="restored last known good config" if restored is not None else "no last known good config snapshot",
        before=before,
        after=redact_config(restored or {}),
        rollback="Restore the invalid config from external backup if needed.",
        failure_class="invalid_config",
    )
    if restored is None:
        return SelfHealResult(
            healthy=False,
            recovered=False,
            attempts=1,
            unrecoverable=True,
            reason=f"{reason}; no last known good config snapshot is available",
            repairs=[repair],
        )
    verification = verify_config(config_path)
    result = SelfHealResult(
        healthy=verification.healthy,
        recovered=verification.healthy,
        attempts=1,
        unrecoverable=not verification.healthy,
        reason="" if verification.healthy else verification.message,
        repairs=[repair],
        final_verification=verification,
    )
    record_stage(config_path, "self_heal", result)
    return result
