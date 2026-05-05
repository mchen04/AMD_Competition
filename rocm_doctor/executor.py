from __future__ import annotations

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
from .recipes import RECIPE_REGISTRY, RepairRecipe
from .schemas import RepairPlan, RepairResult


class SafetyError(RuntimeError):
    pass


def execute_plan(config_path: str | Path, plan: RepairPlan) -> RepairResult:
    path = Path(config_path)
    config = load_config(path)
    before = redact_config(config)
    recipe = RECIPE_REGISTRY.get(plan.recipe_id)
    if recipe is None:
        return _rejected(plan.recipe_id, before, f"unknown recipe id: {plan.recipe_id}")

    try:
        changes = recipe.build_changes(config)
        _validate_safety(path, config, plan, recipe, changes)
    except (KeyError, TypeError, ValueError) as exc:
        return _rejected(plan.recipe_id, before, f"recipe precondition failed: {exc}")
    except SafetyError as exc:
        return _rejected(plan.recipe_id, before, str(exc))

    if not changes:
        return RepairResult(
            applied=False,
            recipe_id=plan.recipe_id,
            changed_paths=[],
            rejected=False,
            reason="no deterministic changes required",
            before=before,
            after=before,
            rollback=recipe.rollback_strategy,
        )

    changed_paths: list[str] = []
    for dotted_key, value in changes.items():
        old_value = get_dotted(config, dotted_key)
        if old_value != value:
            set_dotted(config, dotted_key, value)
            changed_paths.append(dotted_key)
    if changed_paths:
        save_config(path, config)
    after = redact_config(config)
    return RepairResult(
        applied=bool(changed_paths),
        recipe_id=plan.recipe_id,
        changed_paths=changed_paths,
        rejected=False,
        reason="applied deterministic recipe" if changed_paths else "config already matched recipe output",
        before=before,
        after=after,
        rollback=recipe.rollback_strategy,
    )


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
    if not isinstance(provider_changes, dict):
        raise SafetyError("provider config_patch.changes must be an object")

    for dotted_key in list(provider_changes.keys()) + list(deterministic_changes.keys()):
        if contains_sensitive_key(str(dotted_key)):
            raise SafetyError(f"credential or secret modification rejected: {dotted_key}")

    for dotted_key, provider_value in provider_changes.items():
        if dotted_key not in recipe.config_paths:
            raise SafetyError(f"provider attempted to edit path outside recipe scope: {dotted_key}")
        if dotted_key not in deterministic_changes:
            raise SafetyError(f"provider attempted a non-deterministic edit: {dotted_key}")
        if provider_value != deterministic_changes[dotted_key]:
            raise SafetyError(f"provider value for {dotted_key} did not match deterministic recipe output")

    for dotted_key in deterministic_changes:
        if dotted_key not in recipe.config_paths:
            raise SafetyError(f"recipe attempted to edit undeclared path: {dotted_key}")
    if "model.base_url" in deterministic_changes:
        expected = config["model"].get("expected_base_url")
        if deterministic_changes["model.base_url"] != expected:
            raise SafetyError("network endpoint change is only allowed to model.expected_base_url")


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
