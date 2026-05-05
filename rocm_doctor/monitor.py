from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import get_active_profile, load_config, redact_config
from .schemas import EvidenceBundle, HealthCheckResult, RuntimeProfile, to_jsonable
from .timeutil import utc_now


DEFAULT_TIMEOUT_SECONDS = 1.5


def run_check(
    config_path: str | Path, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> tuple[HealthCheckResult, EvidenceBundle]:
    config = load_config(config_path)
    profile = get_active_profile(config)
    if timeout == DEFAULT_TIMEOUT_SECONDS:
        timeout = profile.request_timeout_seconds
    model = config["model"]
    launch = config["launch"]
    base_url = profile.base_url.rstrip("/")
    endpoint: dict[str, Any] = {
        "configured_base_url": base_url,
        "expected_base_url": profile.expected_base_url,
        "profile": to_jsonable(profile),
        "models": {},
        "chat": {},
        "tool_call": {},
        "skipped_checks": {},
    }
    checks: dict[str, bool] = {}
    errors: list[str] = []

    if _supports(profile, "models") and profile.endpoint_protocol == "openai-compatible":
        models_ok, models_payload, models_error = _http_json("GET", f"{base_url}/models", timeout=timeout)
        endpoint["models"] = {"ok": models_ok, "error": models_error, "response": _compact(models_payload)}
        checks["endpoint_models"] = models_ok
        if models_error:
            errors.append(f"GET /v1/models failed: {models_error}")
    else:
        models_ok = True
        _skip_check(endpoint, checks, "endpoint_models", _skip_reason(profile, "models"))

    chat_ok = False
    if not _supports(profile, "chat_completions"):
        chat_ok = True
        _skip_check(endpoint, checks, "chat_completion", _skip_reason(profile, "chat_completions"))
    elif profile.endpoint_protocol != "openai-compatible":
        chat_ok = True
        _skip_check(endpoint, checks, "chat_completion", f"{profile.endpoint_protocol} chat probe is not implemented")
    elif models_ok:
        chat_ok, chat_payload, chat_error = _chat(base_url, model, timeout=timeout)
        endpoint["chat"] = {"ok": chat_ok, "error": chat_error, "response": _compact(chat_payload)}
        if chat_error:
            errors.append(f"POST /v1/chat/completions failed: {chat_error}")
    else:
        endpoint["chat"] = {"ok": False, "error": "skipped because models check failed"}
        checks["chat_completion"] = chat_ok
    if "chat_completion" not in checks:
        checks["chat_completion"] = chat_ok

    if _supports(profile, "context_length"):
        max_model_len, max_len_error = _int_value(model.get("max_model_len"), "max_model_len")
        safe_max_model_len, safe_len_error = _int_value(
            model.get("safe_max_model_len", profile.safe_max_model_len), "safe_max_model_len"
        )
        context_ok = not max_len_error and not safe_len_error and max_model_len <= safe_max_model_len
        checks["context_length"] = context_ok
        if not context_ok:
            if max_len_error or safe_len_error:
                errors.append("; ".join(error for error in [max_len_error, safe_len_error] if error))
            else:
                errors.append(
                    f"max_model_len {model.get('max_model_len')} exceeds safe_max_model_len "
                    f"{model.get('safe_max_model_len', profile.safe_max_model_len)}"
                )
    else:
        _skip_check(endpoint, checks, "context_length", _skip_reason(profile, "context_length"))

    if _supports(profile, "rocm_device_flags"):
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

    tool_ok = True
    if not bool(model.get("tool_check_enabled", profile.tool_check_enabled)):
        _skip_check(endpoint, checks, "tool_call_parser", "model.tool_check_enabled is false")
    elif not _supports(profile, "tool_calls"):
        _skip_check(endpoint, checks, "tool_call_parser", _skip_reason(profile, "tool_calls"))
    else:
        if chat_ok:
            tool_ok, tool_payload, tool_error = _tool_call(base_url, model, timeout=timeout)
            endpoint["tool_call"] = {
                "ok": tool_ok,
                "error": tool_error,
                "response": _compact(tool_payload),
            }
            if tool_error:
                errors.append(f"tool-call verification failed: {tool_error}")
        else:
            tool_ok = False
            endpoint["tool_call"] = {"ok": False, "error": "skipped because chat check failed"}
            checks["tool_call_parser"] = tool_ok
    if "tool_call_parser" not in checks:
        checks["tool_call_parser"] = tool_ok

    healthy = all(checks.values())
    summary = "healthy" if healthy else "unhealthy: " + "; ".join(errors)
    health = HealthCheckResult(healthy=healthy, checks=checks, errors=errors, summary=summary)
    evidence = EvidenceBundle(
        collected_at=utc_now(),
        config_path=str(Path(config_path)),
        config_snapshot=redact_config(config),
        endpoint=endpoint,
        runtime={
            "profile_id": profile.id,
            "runtime_type": profile.runtime_type,
            "endpoint_protocol": profile.endpoint_protocol,
            "capabilities": profile.capabilities,
            "skipped_checks": endpoint["skipped_checks"],
            "service": config.get("service", {}),
            "provider": {"configured": sorted(config.get("provider", {}).keys())},
        },
        logs=[],
        health=health,
    )
    return health, evidence


def _chat(base_url: str, model: dict[str, Any], timeout: float) -> tuple[bool, Any, str]:
    payload = {
        "model": model.get("name", "fake-qwen3"),
        "messages": [{"role": "user", "content": "Return a short health token."}],
        "temperature": 0,
        "max_tokens": 8,
    }
    return _http_json("POST", f"{base_url}/chat/completions", payload=payload, timeout=timeout)


def _tool_call(base_url: str, model: dict[str, Any], timeout: float) -> tuple[bool, Any, str]:
    payload = {
        "model": model.get("name", "fake-qwen3"),
        "messages": [{"role": "user", "content": "Call rocm_doctor_ping."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "rocm_doctor_ping",
                    "description": "Deterministic ROCm Doctor tool-call smoke check.",
                    "parameters": {
                        "type": "object",
                        "properties": {"status": {"type": "string"}},
                        "required": ["status"],
                    },
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "rocm_doctor_ping"},
        },
        "temperature": 0,
    }
    ok, data, error = _http_json(
        "POST",
        f"{base_url}/chat/completions",
        payload=payload,
        timeout=timeout,
        extra_headers={"X-ROCm-Doctor-Tool-Parser": str(model.get("tool_parser", ""))},
    )
    if not ok:
        return False, data, error
    try:
        message = data["choices"][0]["message"]
        calls = message.get("tool_calls", [])
        first = calls[0]
        name = first["function"]["name"]
    except (KeyError, IndexError, TypeError):
        return False, data, "response did not contain a tool call"
    if name != "rocm_doctor_ping":
        return False, data, f"unexpected tool call name: {name}"
    return True, data, ""


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 1.5,
    extra_headers: dict[str, str] | None = None,
) -> tuple[bool, Any, str]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return False, raw[:500], f"invalid JSON response: {exc}"
            if response.status >= 400:
                return False, parsed, f"HTTP {response.status}"
            return True, parsed, ""
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except OSError:
            body = ""
        return False, body[:500], f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, None, str(exc)


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value[:3]]
    if isinstance(value, str) and len(value) > 300:
        return value[:300] + "..."
    return value


def _int_value(value: Any, label: str) -> tuple[int, str]:
    try:
        return int(value), ""
    except (TypeError, ValueError):
        return 0, f"{label} must be an integer"


def _supports(profile: RuntimeProfile, capability: str) -> bool:
    return bool(profile.capabilities.get(capability, False))


def _skip_reason(profile: RuntimeProfile, capability: str) -> str:
    return profile.skip_reasons.get(capability, f"profile {profile.id} does not enable {capability}")


def _skip_check(endpoint: dict[str, Any], checks: dict[str, bool], check_name: str, reason: str) -> None:
    checks[check_name] = True
    endpoint["skipped_checks"][check_name] = reason
