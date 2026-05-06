from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
                supported_failure_classes=("no_failure", "unknown_failure"),
                supported_profile_capabilities=(),
                preconditions=("System is already healthy or provider is unavailable.",),
                config_path_templates=(),
                risk_level="none",
                rollback_strategy="No change was made.",
                verification_steps=("No verification required.",),
                build_changes=lambda config: {},
            ),
            RepairRecipe(
                id="retry_without_config_change",
                supported_failure_classes=("one_time_rate_limit",),
                supported_profile_capabilities=(),
                preconditions=("Failure may be transient and a retry has not yet been observed.",),
                config_path_templates=(),
                risk_level="none",
                rollback_strategy="No change was made.",
                verification_steps=("rerun health check once",),
                build_changes=lambda config: {},
            ),
            RepairRecipe(
                id="update_endpoint_url",
                supported_failure_classes=("endpoint_broken", "endpoint_unreachable", "wrong_endpoint_port"),
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
                id="increase_health_max_tokens",
                supported_failure_classes=("empty_qwen_output",),
                supported_profile_capabilities=("chat_completions",),
                preconditions=("validation.health_max_tokens is configured.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.validation.health_max_tokens",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous health_max_tokens value.",
                verification_steps=("POST /v1/chat/completions health check",),
                build_changes=_increase_health_max_tokens,
            ),
            RepairRecipe(
                id="lower_health_max_tokens",
                supported_failure_classes=("timeout", "repetitive_loop"),
                supported_profile_capabilities=("chat_completions",),
                preconditions=("validation.health_max_tokens is configured above the minimum.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.validation.health_max_tokens",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous health_max_tokens value.",
                verification_steps=("POST /v1/chat/completions health check",),
                build_changes=_lower_health_max_tokens,
            ),
            RepairRecipe(
                id="increase_timeout",
                supported_failure_classes=("timeout",),
                supported_profile_capabilities=("chat_completions",),
                preconditions=("request.timeout_seconds is configured.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.request.timeout_seconds",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous request timeout.",
                verification_steps=("POST /v1/chat/completions health check",),
                build_changes=_increase_timeout,
            ),
            RepairRecipe(
                id="increase_retry_backoff",
                supported_failure_classes=("repeated_rate_limit", "timeout"),
                supported_profile_capabilities=(),
                preconditions=("request.retry settings are configured.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.request.retry.backoff_seconds",
                    "model_providers.{active_model_provider}.request.retry.max_attempts",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous retry backoff and attempt count.",
                verification_steps=("rerun health check with updated retry policy",),
                build_changes=_increase_retry_backoff,
            ),
            RepairRecipe(
                id="disable_streaming",
                supported_failure_classes=("broken_streaming", "timeout"),
                supported_profile_capabilities=("chat_completions",),
                preconditions=("request.stream is enabled.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.request.stream",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous streaming setting.",
                verification_steps=("POST /v1/chat/completions without stream=true",),
                build_changes=lambda config: {active_provider_path(config, "request.stream"): False},
            ),
            RepairRecipe(
                id="switch_prompt_template",
                supported_failure_classes=(
                    "bad_template",
                    "empty_qwen_output",
                    "instruction_drift",
                    "repetitive_loop",
                ),
                supported_profile_capabilities=("chat_completions",),
                preconditions=("a fallback health_chat template is configured or bundled.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.templates.health_chat",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous health_chat template.",
                verification_steps=("render fallback template", "POST /v1/chat/completions health check"),
                build_changes=_switch_prompt_template,
            ),
            RepairRecipe(
                id="fallback_model_provider",
                supported_failure_classes=(
                    "permanent_500",
                    "repeated_rate_limit",
                    "endpoint_broken",
                    "endpoint_unreachable",
                    "timeout",
                ),
                supported_profile_capabilities=(),
                preconditions=("self_healing.fallback_model_provider names a configured provider.",),
                config_path_templates=("active_model_provider",),
                risk_level="medium",
                rollback_strategy="Restore the previous active_model_provider.",
                verification_steps=("run health checks against fallback provider",),
                build_changes=_fallback_model_provider,
            ),
            RepairRecipe(
                id="restore_last_known_good_config",
                supported_failure_classes=("config_invalid", "invalid_config"),
                supported_profile_capabilities=(),
                preconditions=("state contains last_known_good_config.",),
                config_path_templates=(),
                risk_level="low",
                rollback_strategy="Restore the config that existed before the last-known-good restore.",
                verification_steps=("reload config", "run health checks"),
                build_changes=lambda config: {},
            ),
            RepairRecipe(
                id="tighten_expected_health_response",
                supported_failure_classes=("instruction_drift",),
                supported_profile_capabilities=("chat_completions",),
                preconditions=("validation.expected_health_response is configured.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.validation.health_response_match",
                    "model_providers.{active_model_provider}.validation.max_health_response_chars",
                ),
                risk_level="low",
                rollback_strategy="Restore the previous health response validation settings.",
                verification_steps=("POST /v1/chat/completions health check",),
                build_changes=_tighten_expected_health_response,
            ),
            RepairRecipe(
                id="disable_tool_probe_for_weak_model",
                supported_failure_classes=("tool_parser_mismatch",),
                supported_profile_capabilities=("tool_calls",),
                preconditions=("model tool-call probe is enabled for a weak/local model profile.",),
                config_path_templates=(
                    "model_providers.{active_model_provider}.model.tool_calling.enabled",
                ),
                risk_level="medium",
                rollback_strategy="Restore the previous tool-call probe setting.",
                verification_steps=("run health check with tool-call probe skipped",),
                build_changes=lambda config: {
                    active_provider_path(config, "model.tool_calling.enabled"): False
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
                id="synthesize_patch",
                supported_failure_classes=tuple(),
                supported_profile_capabilities=(),
                preconditions=(
                    "diagnosis brain proposes a config_patch.changes map of dotted YAML paths; "
                    "every path must already be in the union of allowlisted paths from the "
                    "registry, every value must match the existing value's type, and no path "
                    "may match the credential redaction filter.",
                ),
                config_path_templates=(),
                risk_level="medium",
                rollback_strategy="Restore the pre-patch values for every dotted YAML path the brain edited.",
                verification_steps=(
                    "rerun health check after the synthesized patch is applied",
                ),
                build_changes=lambda config: {},
            ),
            RepairRecipe(
                id="restart_known_service",
                supported_failure_classes=(
                    "endpoint_broken",
                    "endpoint_unreachable",
                    "wrong_endpoint_port",
                    "permanent_500",
                    "unknown_failure",
                ),
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


def _increase_health_max_tokens(config: dict[str, Any]) -> dict[str, Any]:
    current = int(_active_provider_value(config, "validation.health_max_tokens"))
    updated = 512 if current < 512 else min(current * 2, 2048)
    return {active_provider_path(config, "validation.health_max_tokens"): updated}


def _lower_health_max_tokens(config: dict[str, Any]) -> dict[str, Any]:
    current = int(_active_provider_value(config, "validation.health_max_tokens"))
    updated = max(16, current // 2)
    if updated == current and current > 16:
        updated = current - 1
    return {active_provider_path(config, "validation.health_max_tokens"): updated}


def _increase_timeout(config: dict[str, Any]) -> dict[str, Any]:
    current = float(_active_provider_value(config, "request.timeout_seconds"))
    updated = min(max(current * 4, current + 10.0), 120.0)
    return {active_provider_path(config, "request.timeout_seconds"): round(updated, 3)}


def _increase_retry_backoff(config: dict[str, Any]) -> dict[str, Any]:
    current_backoff = float(_active_provider_value(config, "request.retry.backoff_seconds"))
    current_attempts = int(_active_provider_value(config, "request.retry.max_attempts"))
    return {
        active_provider_path(config, "request.retry.backoff_seconds"): round(
            min(max(current_backoff * 2, 0.25), 10.0), 3
        ),
        active_provider_path(config, "request.retry.max_attempts"): min(max(current_attempts + 1, 3), 6),
    }


def _switch_prompt_template(config: dict[str, Any]) -> dict[str, Any]:
    provider = config["model_providers"][str(config["active_model_provider"])]
    templates = provider["templates"]
    current = str(templates["health_chat"])
    fallbacks = [str(item) for item in templates.get("health_chat_fallbacks", [])]
    bundled = _bundled_health_template_fallbacks(current)
    existing_configured = [
        item for item in fallbacks if Path(item).is_absolute() and Path(item).exists()
    ]
    candidates = fallbacks + [item for item in bundled if item not in fallbacks]
    if current not in fallbacks:
        preferred = existing_configured or bundled
        candidates = preferred + [item for item in fallbacks + bundled if item not in preferred]
    if not candidates:
        raise ValueError("no fallback health_chat template is configured")

    if current in candidates:
        index = candidates.index(current)
        if index + 1 >= len(candidates):
            raise ValueError("health_chat template is already on the last fallback")
        next_template = candidates[index + 1]
    else:
        next_template = candidates[0]
    return {active_provider_path(config, "templates.health_chat"): next_template}


def _bundled_health_template_fallbacks(current: str) -> list[str]:
    current_path = Path(current)
    candidates: list[Path] = []
    if str(current_path.parent) not in {"", "."}:
        candidates.extend(
            current_path.parent / name
            for name in (
                "health_chat.qwen_strict.j2",
                "health_chat.no_reasoning.j2",
                "health_chat.minimal.j2",
            )
        )
    bundled = Path(__file__).resolve().parent.parent / "templates"
    candidates.extend(
        bundled / name
        for name in (
            "health_chat.qwen_strict.j2",
            "health_chat.no_reasoning.j2",
            "health_chat.minimal.j2",
        )
    )
    seen: set[str] = set()
    existing: list[str] = []
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved not in seen and candidate.exists():
            seen.add(resolved)
            existing.append(resolved)
    return existing


def _fallback_model_provider(config: dict[str, Any]) -> dict[str, Any]:
    current = str(config["active_model_provider"])
    fallback = str(config.get("self_healing", {}).get("fallback_model_provider", "")).strip()
    if not fallback:
        provider = config["model_providers"][current]
        fallback = str(provider.get("repair", {}).get("fallback_model_provider", "")).strip()
    if not fallback:
        raise ValueError("no fallback model provider is configured")
    if fallback == current:
        raise ValueError("fallback model provider is already active")
    if fallback not in config["model_providers"]:
        raise ValueError(f"fallback model provider is not configured: {fallback}")
    return {"active_model_provider": fallback}


def _tighten_expected_health_response(config: dict[str, Any]) -> dict[str, Any]:
    expected = str(_active_provider_value(config, "validation.expected_health_response")).strip()
    if not expected:
        raise ValueError("validation.expected_health_response is empty")
    return {
        active_provider_path(config, "validation.health_response_match"): "exact",
        active_provider_path(config, "validation.max_health_response_chars"): len(expected),
    }


def _active_provider_value(config: dict[str, Any], suffix: str) -> Any:
    cursor: Any = config["model_providers"][str(config["active_model_provider"])]
    for part in suffix.split("."):
        cursor = cursor[part]
    return cursor


RECIPE_REGISTRY = registry()


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
