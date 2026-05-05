from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .config import active_provider_path


ChangeBuilder = Callable[[dict[str, Any]], dict[str, Any]]
PathBuilder = Callable[[dict[str, Any]], tuple[str, ...]]


@dataclass(frozen=True)
class RepairRecipe:
    id: str
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


def registry() -> dict[str, RepairRecipe]:
    return {
        recipe.id: recipe
        for recipe in (
            RepairRecipe(
                id="noop",
                supported_failure_classes=("no_failure",),
                supported_profile_capabilities=(),
                preconditions=("System is already healthy or provider is unavailable.",),
                config_path_templates=(),
                risk_level="none",
                rollback_strategy="No change was made.",
                verification_steps=("No verification required.",),
                build_changes=lambda config: {},
            ),
            RepairRecipe(
                id="update_endpoint_url",
                supported_failure_classes=("endpoint_unreachable", "wrong_endpoint_port"),
                supported_profile_capabilities=("models",),
                preconditions=("active model provider expected_base_url is configured.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.model.endpoint.base_url",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous active model provider endpoint URL.",
                verification_steps=("GET /v1/models", "POST /v1/chat/completions"),
                build_changes=lambda config: {
                    active_provider_path(config, "model.endpoint.base_url"): _active_provider_value(
                        config, "model.endpoint.expected_base_url"
                    ),
                },
            ),
            RepairRecipe(
                id="lower_max_model_len",
                supported_failure_classes=("context_length_too_large",),
                supported_profile_capabilities=("context_length",),
                preconditions=("active model provider safe context limit is configured.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.model.context.max_tokens",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous active model provider max context limit.",
                verification_steps=("config validation", "POST /v1/chat/completions"),
                build_changes=lambda config: {
                    active_provider_path(config, "model.context.max_tokens"): _active_provider_value(
                        config, "model.context.safe_max_tokens"
                    ),
                },
            ),
            RepairRecipe(
                id="set_tool_parser",
                supported_failure_classes=("tool_parser_mismatch",),
                supported_profile_capabilities=("tool_calls",),
                preconditions=("active model provider expected tool parser is configured.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.model.tool_calling.parser",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous active model provider tool parser.",
                verification_steps=("deterministic tool-call check",),
                build_changes=lambda config: {
                    active_provider_path(config, "model.tool_calling.parser"): _active_provider_value(
                        config, "model.tool_calling.expected_parser"
                    ),
                },
            ),
            RepairRecipe(
                id="set_rocm_device_flags",
                supported_failure_classes=("missing_rocm_device_flags",),
                supported_profile_capabilities=("rocm_device_flags",),
                preconditions=("launch.required_device_flags is configured.",),
                config_path_templates=("launch.device_flags",),
                risk_level="low",
                rollback_strategy="Restore the previous launch.device_flags list.",
                verification_steps=("config validation", "ROCm device flag check"),
                build_changes=_rocm_flag_changes,
            ),
            RepairRecipe(
                id="restart_known_service",
                supported_failure_classes=("endpoint_unreachable", "wrong_endpoint_port", "unknown_failure"),
                supported_profile_capabilities=("restart",),
                preconditions=("service.name is configured.", "service.restart_mode is dry-run or fake-service."),
                config_path_templates=("service.restart_count", "service.last_restart_dry_run"),
                risk_level="medium",
                rollback_strategy="No process restart is performed in dry-run mode; decrement restart_count if needed.",
                verification_steps=("GET /v1/models", "POST /v1/chat/completions"),
                build_changes=lambda config: {
                    "service.restart_count": int(config.get("service", {}).get("restart_count", 0)) + 1,
                    "service.last_restart_dry_run": True,
                },
            ),
        )
    }


def _rocm_flag_changes(config: dict[str, Any]) -> dict[str, Any]:
    current = [str(item) for item in config["launch"].get("device_flags", [])]
    required = [str(item) for item in config["launch"].get("required_device_flags", [])]
    merged = current[:]
    for flag in required:
        if flag not in merged:
            merged.append(flag)
    return {"launch.device_flags": merged}


def _active_provider_value(config: dict[str, Any], suffix: str) -> Any:
    cursor: Any = config["model_providers"][str(config["active_model_provider"])]
    for part in suffix.split("."):
        cursor = cursor[part]
    return cursor


RECIPE_REGISTRY = registry()
