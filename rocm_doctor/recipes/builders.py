"""Deterministic config-change builders for every recipe id.

Recipe metadata lives in ``registry.yaml``. This module holds the
small Python callables that compute the actual config patch for a given
loaded config — these can't go in YAML (they're functions, not data).

Adding a recipe = append a YAML entry + add a builder here keyed by id.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..config import active_provider_path


ChangeBuilder = Callable[[dict[str, Any]], dict[str, Any]]


def _active_value(config: dict[str, Any], suffix: str) -> Any:
    cursor: Any = config["model_providers"][str(config["active_model_provider"])]
    for part in suffix.split("."):
        cursor = cursor[part]
    return cursor


def _noop(config: dict[str, Any]) -> dict[str, Any]:
    return {}


def _update_endpoint_url(config: dict[str, Any]) -> dict[str, Any]:
    return {
        active_provider_path(config, "model.endpoint.base_url"):
            _active_value(config, "model.endpoint.expected_base_url"),
    }


def _disable_streaming(config: dict[str, Any]) -> dict[str, Any]:
    return {active_provider_path(config, "request.stream"): False}


def _disable_tool_probe(config: dict[str, Any]) -> dict[str, Any]:
    return {active_provider_path(config, "model.tool_calling.enabled"): False}


def _set_tool_parser(config: dict[str, Any]) -> dict[str, Any]:
    return {
        active_provider_path(config, "model.tool_calling.parser"):
            _active_value(config, "model.tool_calling.expected_parser"),
    }


def _lower_max_model_len(config: dict[str, Any]) -> dict[str, Any]:
    return {
        active_provider_path(config, "model.context.max_tokens"):
            _active_value(config, "model.context.safe_max_tokens"),
    }


def _restart_known_service(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "service.restart_count": int(config.get("service", {}).get("restart_count", 0)) + 1,
        "service.last_restart_dry_run": True,
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
    current = int(_active_value(config, "validation.health_max_tokens"))
    updated = 512 if current < 512 else min(current * 2, 2048)
    return {active_provider_path(config, "validation.health_max_tokens"): updated}


def _lower_health_max_tokens(config: dict[str, Any]) -> dict[str, Any]:
    current = int(_active_value(config, "validation.health_max_tokens"))
    updated = max(16, current // 2)
    if updated == current and current > 16:
        updated = current - 1
    return {active_provider_path(config, "validation.health_max_tokens"): updated}


def _increase_timeout(config: dict[str, Any]) -> dict[str, Any]:
    current = float(_active_value(config, "request.timeout_seconds"))
    updated = min(max(current * 4, current + 10.0), 120.0)
    return {active_provider_path(config, "request.timeout_seconds"): round(updated, 3)}


def _increase_retry_backoff(config: dict[str, Any]) -> dict[str, Any]:
    current_backoff = float(_active_value(config, "request.retry.backoff_seconds"))
    current_attempts = int(_active_value(config, "request.retry.max_attempts"))
    return {
        active_provider_path(config, "request.retry.backoff_seconds"):
            round(min(max(current_backoff * 2, 0.25), 10.0), 3),
        active_provider_path(config, "request.retry.max_attempts"):
            min(max(current_attempts + 1, 3), 6),
    }


def _switch_prompt_template(config: dict[str, Any]) -> dict[str, Any]:
    provider = config["model_providers"][str(config["active_model_provider"])]
    templates = provider["templates"]
    current = str(templates["health_chat"])
    fallbacks = [str(item) for item in templates.get("health_chat_fallbacks", [])]
    bundled = _bundled_health_template_fallbacks()
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


def _bundled_health_template_fallbacks() -> list[str]:
    bundled = Path(__file__).resolve().parent.parent.parent / "templates"
    candidates = [
        bundled / name
        for name in (
            "health_chat.qwen_strict.j2",
            "health_chat.no_reasoning.j2",
            "health_chat.minimal.j2",
        )
    ]
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
    expected = str(_active_value(config, "validation.expected_health_response")).strip()
    if not expected:
        raise ValueError("validation.expected_health_response is empty")
    return {
        active_provider_path(config, "validation.health_response_match"): "exact",
        active_provider_path(config, "validation.max_health_response_chars"): len(expected),
    }


def _lower_gpu_memory_utilization(config: dict[str, Any]) -> dict[str, Any]:
    launch = config.get("launch", {}) or {}
    vllm_args = launch.get("vllm_args", {}) or {}
    if "gpu_memory_utilization" not in vllm_args:
        raise ValueError("launch.vllm_args.gpu_memory_utilization is not configured")
    current = float(vllm_args["gpu_memory_utilization"])
    updated = max(0.3, round(current * 0.8, 3))
    if updated >= current:
        updated = max(0.3, round(current - 0.05, 3))
    if updated >= current:
        raise ValueError("gpu_memory_utilization is already at the floor")
    return {"launch.vllm_args.gpu_memory_utilization": updated}


def _align_max_tokens_with_served(config: dict[str, Any]) -> dict[str, Any]:
    current = int(_active_value(config, "model.context.max_tokens"))
    safe = int(_active_value(config, "model.context.safe_max_tokens"))
    if safe < current:
        target = safe
    else:
        target = max(1, current // 2)
    if target >= current:
        raise ValueError("max_tokens is already at or below the safe ceiling")
    return {active_provider_path(config, "model.context.max_tokens"): target}


BUILDERS: dict[str, ChangeBuilder] = {
    "noop": _noop,
    "retry_without_config_change": _noop,
    "update_endpoint_url": _update_endpoint_url,
    "increase_health_max_tokens": _increase_health_max_tokens,
    "lower_health_max_tokens": _lower_health_max_tokens,
    "increase_timeout": _increase_timeout,
    "increase_retry_backoff": _increase_retry_backoff,
    "disable_streaming": _disable_streaming,
    "switch_prompt_template": _switch_prompt_template,
    "fallback_model_provider": _fallback_model_provider,
    "restore_last_known_good_config": _noop,
    "tighten_expected_health_response": _tighten_expected_health_response,
    "disable_tool_probe_for_weak_model": _disable_tool_probe,
    "lower_max_model_len": _lower_max_model_len,
    "set_tool_parser": _set_tool_parser,
    "set_rocm_device_flags": _rocm_flag_changes,
    "lower_gpu_memory_utilization": _lower_gpu_memory_utilization,
    "align_max_tokens_with_served": _align_max_tokens_with_served,
    "synthesize_patch": _noop,
    "restart_known_service": _restart_known_service,
}
