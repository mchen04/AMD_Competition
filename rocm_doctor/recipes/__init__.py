"""Recipe registry — loaded from ``registry.yaml`` + Python builders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


ChangeBuilder = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RepairRecipe:
    id: str
    description: str
    human_label: str
    tags: tuple[str, ...]
    supported_failure_classes: tuple[str, ...]
    supported_profile_capabilities: tuple[str, ...]
    preconditions: tuple[str, ...]
    config_path_templates: tuple[str, ...]
    risk_level: str
    rollback_strategy: str
    verification_steps: tuple[str, ...]
    build_changes: ChangeBuilder

    def config_paths(self, config: dict[str, Any]) -> tuple[str, ...]:
        active_provider = str(config["active_model_provider"])
        return tuple(path.format(active_model_provider=active_provider) for path in self.config_path_templates)


_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.yaml"


def _load_registry() -> dict[str, RepairRecipe]:
    from .builders import BUILDERS

    raw = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    entries = raw.get("recipes") or []
    out: dict[str, RepairRecipe] = {}
    for entry in entries:
        recipe_id = str(entry["id"])
        builder = BUILDERS.get(recipe_id)
        if builder is None:
            raise RuntimeError(f"recipe {recipe_id} has no change-builder in BUILDERS")
        out[recipe_id] = RepairRecipe(
            id=recipe_id,
            description=str(entry.get("description", "")),
            human_label=str(entry.get("human_label", recipe_id)),
            tags=tuple(str(t) for t in entry.get("tags", []) or []),
            supported_failure_classes=tuple(str(t) for t in entry.get("supported_failure_classes", []) or []),
            supported_profile_capabilities=tuple(str(t) for t in entry.get("supported_profile_capabilities", []) or []),
            preconditions=tuple(str(t).strip() for t in entry.get("preconditions", []) or []),
            config_path_templates=tuple(str(t) for t in entry.get("config_path_templates", []) or []),
            risk_level=str(entry.get("risk_level", "low")),
            rollback_strategy=str(entry.get("rollback_strategy", "")),
            verification_steps=tuple(str(t) for t in entry.get("verification_steps", []) or []),
            build_changes=builder,
        )
    return out


RECIPE_REGISTRY: dict[str, RepairRecipe] = _load_registry()


def registry() -> dict[str, RepairRecipe]:
    """Return the registry (kept for backwards compatibility)."""
    return RECIPE_REGISTRY


def global_allowlisted_paths(config: dict[str, Any]) -> set[str]:
    """Union of every recipe's resolved dotted config paths for this active provider.

    The synthesize_patch executor uses this set as the bounded action surface
    available to the diagnosis brain when no single recipe applies.
    """
    paths: set[str] = set()
    for recipe in RECIPE_REGISTRY.values():
        if recipe.id == "synthesize_patch":
            continue
        for path in recipe.config_paths(config):
            paths.add(path)
    return paths


__all__ = [
    "ChangeBuilder",
    "RepairRecipe",
    "RECIPE_REGISTRY",
    "registry",
    "global_allowlisted_paths",
]
