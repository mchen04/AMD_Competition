from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import get_active_profile, load_config, redact_config
from .model_providers import ProbeResult, get_model_provider_adapter
from .schemas import EvidenceBundle, HealthCheckResult, RuntimeProfile, to_jsonable
from .timeutil import utc_now


DEFAULT_TIMEOUT_SECONDS = 1.5


def run_check(
    config_path: str | Path, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> tuple[HealthCheckResult, EvidenceBundle]:
    config = load_config(config_path)
    if timeout != DEFAULT_TIMEOUT_SECONDS:
        active = str(config["active_model_provider"])
        config["model_providers"][active]["request"]["timeout_seconds"] = timeout
    profile = get_active_profile(config)
    adapter = get_model_provider_adapter(config_path, config)
    launch = config["launch"]
    endpoint: dict[str, Any] = {
        "configured_base_url": profile.base_url.rstrip("/"),
        "expected_base_url": profile.expected_base_url,
        "profile": to_jsonable(profile),
        "models": {},
        "chat": {},
        "tool_call": {},
        "skipped_checks": {},
    }
    checks: dict[str, bool] = {}
    errors: list[str] = []

    if _probe_enabled(profile, "endpoint_models", "models"):
        models = adapter.models()
        _record_probe(endpoint, "models", models)
        checks["endpoint_models"] = models.ok
        if models.error:
            errors.append(f"GET /v1/models failed: {models.error}")
    else:
        models = ProbeResult(ok=True)
        _skip_check(endpoint, checks, "endpoint_models", _skip_reason(profile, "models"))

    if _probe_enabled(profile, "chat_completion", "chat_completions"):
        if models.ok:
            chat = adapter.chat_completion()
            _record_probe(endpoint, "chat", chat)
            checks["chat_completion"] = chat.ok
            if chat.error:
                errors.append(f"POST /v1/chat/completions failed: {chat.error}")
        else:
            chat = ProbeResult(ok=False, error="skipped because models check failed")
            _record_probe(endpoint, "chat", chat)
            checks["chat_completion"] = False
    else:
        chat = ProbeResult(ok=True)
        _skip_check(endpoint, checks, "chat_completion", _skip_reason(profile, "chat_completions"))

    if _probe_enabled(profile, "context_length", "context_length"):
        context_ok = profile.max_model_len <= profile.safe_max_model_len
        checks["context_length"] = context_ok
        if not context_ok:
            errors.append(
                f"max_model_len {profile.max_model_len} exceeds safe_max_model_len {profile.safe_max_model_len}"
            )
    else:
        _skip_check(endpoint, checks, "context_length", _skip_reason(profile, "context_length"))

    if _probe_enabled(profile, "rocm_device_flags", "rocm_device_flags"):
        required_flags = set(map(str, launch.get("required_device_flags", [])))
        present_flags = set(map(str, launch.get("device_flags", [])))
        missing_flags = sorted(required_flags - present_flags)
        flags_ok = not missing_flags
        checks["rocm_device_flags"] = flags_ok
        endpoint["missing_rocm_device_flags"] = missing_flags
        if missing_flags:
            errors.append(f"missing ROCm device flags: {', '.join(missing_flags)}")
    else:
        endpoint["missing_rocm_device_flags"] = []
        _skip_check(endpoint, checks, "rocm_device_flags", _skip_reason(profile, "rocm_device_flags"))

    if not profile.tool_check_enabled:
        _skip_check(endpoint, checks, "tool_call_parser", "tool calling is disabled for this model provider")
    elif _probe_enabled(profile, "tool_call_parser", "tool_calls"):
        if chat.ok:
            tool_call = adapter.tool_call()
            _record_probe(endpoint, "tool_call", tool_call)
            checks["tool_call_parser"] = tool_call.ok
            if tool_call.error:
                errors.append(f"tool-call verification failed: {tool_call.error}")
        else:
            tool_call = ProbeResult(ok=False, error="skipped because chat check failed")
            _record_probe(endpoint, "tool_call", tool_call)
            checks["tool_call_parser"] = False
    else:
        _skip_check(endpoint, checks, "tool_call_parser", _skip_reason(profile, "tool_calls"))

    healthy = all(checks.values())
    summary = "healthy" if healthy else "unhealthy: " + "; ".join(errors)
    health = HealthCheckResult(healthy=healthy, checks=checks, errors=errors, summary=summary)
    evidence = EvidenceBundle(
        collected_at=utc_now(),
        config_path=str(Path(config_path)),
        config_snapshot=redact_config(config),
        endpoint=endpoint,
        runtime={
            "model_provider_id": profile.id,
            "model_provider_adapter": profile.adapter,
            "runtime_type": profile.runtime_type,
            "endpoint_protocol": profile.endpoint_protocol,
            "capabilities": profile.capabilities,
            "skipped_checks": endpoint["skipped_checks"],
            "hardware": config.get("hardware", {}),
            "service": config.get("service", {}),
            "diagnosis_providers": sorted(config.get("diagnosis", {}).get("providers", {}).keys()),
        },
        logs=[],
        health=health,
    )
    return health, evidence


def _probe_enabled(profile: RuntimeProfile, probe_name: str, capability: str) -> bool:
    return probe_name in profile.health_probes and bool(profile.capabilities.get(capability, False))


def _skip_reason(profile: RuntimeProfile, capability: str) -> str:
    return profile.skip_reasons.get(capability, f"profile {profile.id} does not enable {capability}")


def _skip_check(endpoint: dict[str, Any], checks: dict[str, bool], check_name: str, reason: str) -> None:
    checks[check_name] = True
    endpoint["skipped_checks"][check_name] = reason


def _record_probe(endpoint: dict[str, Any], key: str, probe: ProbeResult) -> None:
    endpoint[key] = {
        "ok": probe.ok,
        "error": probe.error,
        "attempts": probe.attempts,
        "status_code": probe.status_code,
        "response": _compact(probe.payload),
    }


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value[:3]]
    if isinstance(value, str) and len(value) > 300:
        return value[:300] + "..."
    return value
