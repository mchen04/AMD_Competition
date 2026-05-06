from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import (
    contains_sensitive_key,
    get_active_profile,
    get_dotted,
    is_relative_to,
    load_config,
    redact_config,
    resolve_workspace,
    save_config,
    set_dotted,
)
from .recipes import RECIPE_REGISTRY, RepairRecipe, global_allowlisted_paths
from .schemas import RepairPlan, RepairResult


class SafetyError(RuntimeError):
    pass


def execute_plan(config_path: str | Path, plan: RepairPlan) -> RepairResult:
    path = Path(config_path)
    sequence = list(plan.recipe_id_sequence) if plan.recipe_id_sequence else [plan.recipe_id]
    if len(sequence) > 1:
        return _execute_sequence(path, plan, sequence)
    return _execute_single(path, plan, sequence[0])


def _execute_single(path: Path, plan: RepairPlan, recipe_id: str) -> RepairResult:
    config = load_config(path)
    before = redact_config(config)
    recipe = RECIPE_REGISTRY.get(recipe_id)
    if recipe is None:
        return _rejected(recipe_id, before, f"unknown recipe id: {recipe_id}")

    if recipe_id == "synthesize_patch":
        return _execute_synthesis(path, config, before, plan, recipe)

    try:
        changes = recipe.build_changes(config)
        _validate_safety(path, config, plan, recipe, changes)
    except (KeyError, TypeError, ValueError) as exc:
        return _rejected(recipe_id, before, f"recipe precondition failed: {exc}")
    except SafetyError as exc:
        return _rejected(recipe_id, before, str(exc))

    if not changes:
        return RepairResult(
            applied=False,
            recipe_id=recipe_id,
            changed_paths=[],
            rejected=False,
            reason="no deterministic changes required",
            before=before,
            after=before,
            rollback=recipe.rollback_strategy,
            failure_class=plan.failure_class,
        )

    changed_paths = _apply_changes(config, changes)
    if changed_paths:
        save_config(path, config)
    after = redact_config(config)
    return RepairResult(
        applied=bool(changed_paths),
        recipe_id=recipe_id,
        changed_paths=changed_paths,
        rejected=False,
        reason="applied deterministic recipe" if changed_paths else "config already matched recipe output",
        before=before,
        after=after,
        rollback=recipe.rollback_strategy,
        failure_class=plan.failure_class,
    )


def _execute_sequence(path: Path, plan: RepairPlan, sequence: list[str]) -> RepairResult:
    snapshot = deepcopy(load_config(path))
    before = redact_config(snapshot)

    profile = get_active_profile(snapshot)
    safe = set(profile.safe_repair_recipes)
    for recipe_id in sequence:
        if recipe_id not in RECIPE_REGISTRY:
            return _rejected(plan.recipe_id, before, f"unknown recipe id in sequence: {recipe_id}")
        if recipe_id not in safe:
            return _rejected(
                plan.recipe_id,
                before,
                f"recipe {recipe_id} in sequence is not allowed for profile {profile.id}",
            )

    accumulated_paths: list[str] = []
    applied_recipe_ids: list[str] = []
    for recipe_id in sequence:
        step_plan = _step_plan(plan, recipe_id)
        step_result = _execute_single(path, step_plan, recipe_id)
        if step_result.rejected:
            save_config(path, snapshot)
            return RepairResult(
                applied=False,
                recipe_id=plan.recipe_id,
                applied_recipe_ids=applied_recipe_ids,
                changed_paths=accumulated_paths,
                rejected=True,
                reason=f"sequence step {recipe_id} rejected: {step_result.reason}",
                before=before,
                after=redact_config(snapshot),
                rollback="Restored the pre-sequence config snapshot.",
                rolled_back=bool(applied_recipe_ids),
                failure_class=plan.failure_class,
            )
        applied_recipe_ids.append(recipe_id)
        for changed in step_result.changed_paths:
            if changed not in accumulated_paths:
                accumulated_paths.append(changed)

    after = redact_config(load_config(path))
    return RepairResult(
        applied=bool(accumulated_paths),
        recipe_id=plan.recipe_id,
        applied_recipe_ids=applied_recipe_ids,
        changed_paths=accumulated_paths,
        rejected=False,
        reason=f"applied recipe sequence: {', '.join(applied_recipe_ids)}",
        before=before,
        after=after,
        rollback="Restore each step's pre-edit value, in reverse order.",
        failure_class=plan.failure_class,
    )


def _step_plan(plan: RepairPlan, recipe_id: str) -> RepairPlan:
    return RepairPlan(
        recipe_id=recipe_id,
        rationale=plan.rationale or f"sequence step {recipe_id}",
        config_patch={"path": plan.config_patch.get("path", "")} if plan.config_patch else {},
        template_patch={},
        state_patch={},
        command_preview=[],
        risk_level=plan.risk_level,
        rollback=plan.rollback,
        verification_steps=plan.verification_steps,
        provider=plan.provider,
        failure_class=plan.failure_class,
        repairable=plan.repairable,
        expected_success_signal=plan.expected_success_signal,
        unrecoverable_reason=plan.unrecoverable_reason,
    )


def _execute_synthesis(
    path: Path,
    config: dict[str, Any],
    before: dict[str, Any],
    plan: RepairPlan,
    recipe: RepairRecipe,
) -> RepairResult:
    try:
        _validate_synthesis_envelope(path, config, plan)
        proposed = _validate_synthesis_changes(config, plan)
    except SafetyError as exc:
        return _rejected("synthesize_patch", before, str(exc))

    if not proposed:
        return RepairResult(
            applied=False,
            recipe_id="synthesize_patch",
            changed_paths=[],
            rejected=False,
            reason="synthesize_patch produced no changes",
            before=before,
            after=before,
            rollback=recipe.rollback_strategy,
            failure_class=plan.failure_class,
        )

    changed_paths = _apply_changes(config, proposed)
    if changed_paths:
        save_config(path, config)
    after = redact_config(config)
    return RepairResult(
        applied=bool(changed_paths),
        recipe_id="synthesize_patch",
        applied_recipe_ids=["synthesize_patch"],
        changed_paths=changed_paths,
        rejected=False,
        reason=(
            "applied bounded synthesized patch"
            if changed_paths
            else "config already matched synthesized patch"
        ),
        before=before,
        after=after,
        rollback=recipe.rollback_strategy,
        failure_class=plan.failure_class,
    )


def _validate_synthesis_envelope(path: Path, config: dict[str, Any], plan: RepairPlan) -> None:
    if plan.command_preview:
        raise SafetyError("provider plan included free-form command_preview; executor will not run it")

    profile = get_active_profile(config)
    if "synthesize_patch" not in profile.safe_repair_recipes:
        raise SafetyError(
            f"recipe synthesize_patch is not allowed for profile {profile.id}"
        )

    workspace = resolve_workspace(path, config)
    active_config = path.resolve()
    if not is_relative_to(active_config, workspace):
        raise SafetyError("active config is outside the configured demo workspace")

    patch = plan.config_patch or {}
    patch_path = patch.get("path")
    if patch_path:
        target_path = Path(str(patch_path))
        if not target_path.is_absolute():
            target_path = workspace / target_path
        target_path = target_path.resolve()
        if not is_relative_to(target_path, workspace):
            raise SafetyError("provider patch path escapes the configured demo workspace")
        if target_path != active_config:
            raise SafetyError("provider patch path does not match the active config file")


def _validate_synthesis_changes(config: dict[str, Any], plan: RepairPlan) -> dict[str, Any]:
    patch = plan.config_patch or {}
    raw_changes = patch.get("changes")
    if raw_changes is None and patch and not {"path", "changes"} & set(patch):
        raw_changes = patch
    if raw_changes is None:
        raw_changes = {}
    if not isinstance(raw_changes, dict):
        raise SafetyError("synthesize_patch config_patch.changes must be an object")

    allowlist = global_allowlisted_paths(config)
    proposed: dict[str, Any] = {}
    for dotted_key, value in raw_changes.items():
        key = str(dotted_key)
        if contains_sensitive_key(key):
            raise SafetyError(f"credential or secret modification rejected: {key}")
        if key not in allowlist:
            raise SafetyError(
                f"synthesize_patch path is not in the global allowlist: {key}"
            )
        try:
            existing = get_dotted(config, key)
        except KeyError as exc:
            raise SafetyError(
                f"synthesize_patch path does not exist in config: {key}"
            ) from exc
        if not _value_type_compatible(existing, value):
            raise SafetyError(
                f"synthesize_patch value type mismatch for {key}: "
                f"existing {type(existing).__name__}, proposed {type(value).__name__}"
            )
        proposed[key] = value
    return proposed


def _value_type_compatible(existing: Any, proposed: Any) -> bool:
    if isinstance(existing, bool) or isinstance(proposed, bool):
        return isinstance(existing, bool) and isinstance(proposed, bool)
    if isinstance(existing, (int, float)) and isinstance(proposed, (int, float)):
        return True
    return type(existing) is type(proposed)


def _apply_changes(config: dict[str, Any], changes: dict[str, Any]) -> list[str]:
    changed_paths: list[str] = []
    for dotted_key, value in changes.items():
        try:
            old_value = get_dotted(config, dotted_key)
        except KeyError:
            old_value = None
        if old_value != value:
            set_dotted(config, dotted_key, value)
            changed_paths.append(dotted_key)
    return changed_paths


def _validate_safety(
    config_path: Path,
    config: dict[str, Any],
    plan: RepairPlan,
    recipe: RepairRecipe,
    deterministic_changes: dict[str, Any],
) -> None:
    if plan.command_preview:
        raise SafetyError("provider plan included free-form command_preview; executor will not run it")

    profile = get_active_profile(config)
    if plan.recipe_id not in profile.safe_repair_recipes:
        raise SafetyError(f"recipe {plan.recipe_id} is not allowed for profile {profile.id}")
    for capability in recipe.supported_profile_capabilities:
        if not profile.capabilities.get(capability, False):
            raise SafetyError(
                f"recipe {plan.recipe_id} requires profile capability {capability}"
            )

    workspace = resolve_workspace(config_path, config)
    active_config = config_path.resolve()
    if not is_relative_to(active_config, workspace):
        raise SafetyError("active config is outside the configured demo workspace")

    patch = plan.config_patch or {}
    patch_path = patch.get("path")
    if patch_path:
        target_path = Path(str(patch_path))
        if not target_path.is_absolute():
            target_path = workspace / target_path
        target_path = target_path.resolve()
        if not is_relative_to(target_path, workspace):
            raise SafetyError("provider patch path escapes the configured demo workspace")
        if target_path != active_config:
            raise SafetyError("provider patch path does not match the active config file")

    provider_changes = patch.get("changes", {})
    if not provider_changes and patch and not {"path", "changes"} & set(patch):
        provider_changes = patch
    if not isinstance(provider_changes, dict):
        raise SafetyError("provider config_patch.changes must be an object")

    for dotted_key in list(provider_changes.keys()) + list(deterministic_changes.keys()):
        if contains_sensitive_key(str(dotted_key)):
            raise SafetyError(f"credential or secret modification rejected: {dotted_key}")

    allowed_paths = recipe.config_paths(config)
    for dotted_key, provider_value in provider_changes.items():
        if dotted_key not in allowed_paths:
            raise SafetyError(f"provider attempted to edit path outside recipe scope: {dotted_key}")
        if dotted_key not in deterministic_changes:
            raise SafetyError(f"provider attempted a non-deterministic edit: {dotted_key}")
        if provider_value != deterministic_changes[dotted_key]:
            raise SafetyError(f"provider value for {dotted_key} did not match deterministic recipe output")

    for dotted_key in deterministic_changes:
        if dotted_key not in allowed_paths:
            raise SafetyError(f"recipe attempted to edit undeclared path: {dotted_key}")
    endpoint_path = f"model_providers.{config['active_model_provider']}.model.endpoint.base_url"
    if endpoint_path in deterministic_changes:
        expected = config["model_providers"][config["active_model_provider"]]["model"]["endpoint"][
            "expected_base_url"
        ]
        if deterministic_changes[endpoint_path] != expected:
            raise SafetyError("network endpoint change is only allowed to the expected endpoint URL")
    if "active_model_provider" in deterministic_changes:
        fallback = str(deterministic_changes["active_model_provider"])
        if fallback not in config["model_providers"]:
            raise SafetyError(f"fallback model provider is not configured: {fallback}")


def _rejected(recipe_id: str, before: dict[str, Any], reason: str) -> RepairResult:
    return RepairResult(
        applied=False,
        recipe_id=recipe_id,
        changed_paths=[],
        rejected=True,
        reason=reason,
        before=before,
        after=before,
        rollback="No changes were made.",
    )
