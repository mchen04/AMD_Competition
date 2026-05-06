from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .schemas import RetryPolicy, RuntimeProfile


SENSITIVE_KEY_PARTS = ("api_key", "apikey", "token", "secret", "password", "credential")
DEFAULT_DIAGNOSIS_PROVIDER = "rules"


class ConfigError(RuntimeError):
    pass


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"config file does not exist: {config_path}")
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"could not read config file: {exc}") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"config file is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be a YAML object")
    return normalize_config(data)


def save_config(path: str | Path, config: dict[str, Any]) -> None:
    config_path = Path(path)
    payload = _strip_normalized_only_keys(deepcopy(config))
    if config_path.suffix.lower() == ".json":
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    else:
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    config_path.write_text(text, encoding="utf-8")


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(config)
    data.setdefault("version", 1)
    data.setdefault("workspace", ".")
    data.setdefault("reports_dir", "reports")
    data.setdefault("state_file", ".rocm-doctor-state.json")
    data.setdefault("hardware", {})
    data["hardware"] = _normalize_hardware(data["hardware"])
    data.setdefault("launch", {})
    data["launch"].setdefault("device_flags", [])
    data["launch"].setdefault("required_device_flags", [])
    data.setdefault("service", {})
    data["service"].setdefault("restart_count", 0)
    data["service"].setdefault("restart_mode", "dry-run")
    data.setdefault("self_healing", {})
    data["self_healing"].setdefault("max_attempts", 3)
    data["self_healing"].setdefault("fallback_model_provider", "")
    data["self_healing"].setdefault("developer_repair_mode", False)
    data.setdefault("stress_tests", {})
    data["stress_tests"].setdefault("target_model_providers", [])
    data["stress_tests"].setdefault("timeout_seconds", 2.0)

    if "model_providers" not in data or not isinstance(data["model_providers"], dict):
        raise ConfigError("config must define model_providers")
    if "active_model_provider" not in data:
        raise ConfigError("config must define active_model_provider")
    active_model_provider = str(data["active_model_provider"])
    providers = data["model_providers"]
    if active_model_provider not in providers:
        raise ConfigError(f"active model provider is not configured: {active_model_provider}")
    data["model_providers"] = {
        str(provider_id): _normalize_model_provider(str(provider_id), provider)
        for provider_id, provider in providers.items()
    }

    data.setdefault("diagnosis", {})
    data["diagnosis"] = _normalize_diagnosis(data["diagnosis"])
    _validate_config(data)
    return data


def get_active_profile(config: dict[str, Any]) -> RuntimeProfile:
    data = normalize_config(config)
    provider_id = str(data["active_model_provider"])
    provider = data["model_providers"][provider_id]
    model = provider["model"]
    endpoint = model["endpoint"]
    context = model["context"]
    tool_calling = model["tool_calling"]
    request = provider["request"]
    retry = request["retry"]
    health = provider["health"]
    repair = provider["repair"]
    validation = provider.get("validation", {})
    return RuntimeProfile(
        id=provider_id,
        adapter=str(provider["adapter"]),
        runtime_type=str(provider["runtime_type"]),
        endpoint_protocol=str(provider["endpoint_protocol"]),
        model_name=str(model["id"]),
        base_url=str(endpoint["base_url"]),
        expected_base_url=str(endpoint["expected_base_url"]),
        wrong_base_url=str(endpoint["wrong_base_url"]),
        capabilities={str(key): bool(value) for key, value in provider["capabilities"].items()},
        max_model_len=_int_or_error(context["max_tokens"], f"{provider_id}.model.context.max_tokens"),
        safe_max_model_len=_int_or_error(
            context["safe_max_tokens"], f"{provider_id}.model.context.safe_max_tokens"
        ),
        request_timeout_seconds=_float_or_error(
            request["timeout_seconds"], f"{provider_id}.request.timeout_seconds"
        ),
        retry=RetryPolicy(
            max_attempts=_int_or_error(retry["max_attempts"], f"{provider_id}.request.retry.max_attempts"),
            backoff_seconds=_float_or_error(
                retry["backoff_seconds"], f"{provider_id}.request.retry.backoff_seconds"
            ),
            retry_status_codes=[
                _int_or_error(item, f"{provider_id}.request.retry.retry_status_codes")
                for item in retry["retry_status_codes"]
            ],
            retry_on_timeout=bool(retry["retry_on_timeout"]),
            retry_on_invalid_json=bool(retry["retry_on_invalid_json"]),
        ),
        stream=bool(request["stream"]),
        templates={str(key): deepcopy(value) for key, value in provider["templates"].items()},
        tool_parser=str(tool_calling["parser"]),
        expected_tool_parser=str(tool_calling["expected_parser"]),
        tool_parser_header=str(tool_calling["parser_header"]),
        tool_check_enabled=bool(tool_calling["enabled"]),
        health_probes=[str(item) for item in health["probes"]],
        known_failure_signatures={
            str(key): [str(item) for item in value]
            for key, value in repair["known_failure_signatures"].items()
        },
        safe_repair_recipes=[str(item) for item in repair["safe_recipes"]],
        skip_reasons={str(key): str(value) for key, value in health["skip_reasons"].items()},
        validation=deepcopy(validation),
    )


def active_provider_prefix(config: dict[str, Any]) -> str:
    provider_id = str(config["active_model_provider"])
    return f"model_providers.{provider_id}"


def active_provider_path(config: dict[str, Any], suffix: str) -> str:
    return f"{active_provider_prefix(config)}.{suffix}"


def get_diagnosis_provider_config(config: dict[str, Any], provider_name: str) -> dict[str, Any]:
    data = normalize_config(config)
    providers = data["diagnosis"]["providers"]
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        raise ConfigError(f"diagnosis provider is not configured: {provider_name}")
    return provider


def _normalize_model_provider(provider_id: str, provider: Any) -> dict[str, Any]:
    if not isinstance(provider, dict):
        raise ConfigError(f"model provider {provider_id} must be an object")
    data = deepcopy(provider)
    data.setdefault("adapter", "openai-compatible")
    data.setdefault("runtime_type", "openai-compatible")
    data.setdefault("endpoint_protocol", "openai-compatible")
    data.setdefault("capabilities", {})
    for key in ("models", "chat_completions", "tool_calls", "context_length", "rocm_device_flags", "restart"):
        data["capabilities"].setdefault(key, False)

    data.setdefault("model", {})
    model = data["model"]
    model.setdefault("id", provider_id)
    model.setdefault("endpoint", {})
    endpoint = model["endpoint"]
    endpoint.setdefault("base_url", "")
    endpoint.setdefault("expected_base_url", endpoint["base_url"])
    endpoint.setdefault("wrong_base_url", _bump_default_endpoint(endpoint["base_url"]))
    model.setdefault("context", {})
    context = model["context"]
    context.setdefault("max_tokens", 2048)
    context.setdefault("safe_max_tokens", context["max_tokens"])
    model.setdefault("tool_calling", {})
    tool_calling = model["tool_calling"]
    tool_calling.setdefault("enabled", bool(data["capabilities"].get("tool_calls", False)))
    tool_calling.setdefault("parser", "")
    tool_calling.setdefault("expected_parser", tool_calling["parser"])
    tool_calling.setdefault("parser_header", "X-ROCm-Doctor-Tool-Parser")

    data.setdefault("request", {})
    request = data["request"]
    request.setdefault("timeout_seconds", 1.5)
    request.setdefault("stream", False)
    request.setdefault("retry", {})
    retry = request["retry"]
    retry.setdefault("max_attempts", 1)
    retry.setdefault("backoff_seconds", 0.0)
    retry.setdefault("retry_status_codes", [408, 409, 429, 500, 502, 503, 504])
    retry.setdefault("retry_on_timeout", True)
    retry.setdefault("retry_on_invalid_json", True)

    data.setdefault("templates", {})
    templates = data["templates"]
    templates.setdefault("health_chat", "../templates/health_chat.j2")
    templates.setdefault(
        "health_chat_fallbacks",
        [
            "../templates/health_chat.qwen_strict.j2",
            "../templates/health_chat.no_reasoning.j2",
            "../templates/health_chat.minimal.j2",
        ],
    )
    templates.setdefault("tool_call", "../templates/tool_call_prompt.j2")

    data.setdefault("health", {})
    health = data["health"]
    health.setdefault("probes", [])
    health.setdefault("skip_reasons", {})
    data.setdefault("repair", {})
    repair = data["repair"]
    repair.setdefault("safe_recipes", ["noop"])
    repair.setdefault("known_failure_signatures", {})
    data.setdefault("validation", {})
    data["validation"].setdefault("max_health_response_chars", 120)
    data["validation"].setdefault("max_repeated_token_count", 8)
    data["validation"].setdefault("health_max_tokens", 32)
    data["validation"].setdefault("expected_health_response", "ROCM_DOCTOR_OK")
    data["validation"].setdefault("health_response_match", "case_insensitive")
    return data


def _normalize_diagnosis(diagnosis: Any) -> dict[str, Any]:
    if not isinstance(diagnosis, dict):
        raise ConfigError("diagnosis must be an object")
    data = deepcopy(diagnosis)
    data.setdefault("active_provider", DEFAULT_DIAGNOSIS_PROVIDER)
    data.setdefault("providers", {})
    providers = data["providers"]
    providers.setdefault("rules", {"type": "rules"})
    providers.setdefault("fake", {"type": "fake", "mode": "normal"})
    for provider_id, provider in list(providers.items()):
        if not isinstance(provider, dict):
            raise ConfigError(f"diagnosis provider {provider_id} must be an object")
        provider.setdefault("type", str(provider_id))
        if provider["type"] == "openai-responses":
            provider.setdefault("endpoint", "https://api.openai.com/v1/responses")
            provider.setdefault("api_key_env", "OPENAI_API_KEY")
            provider.setdefault("model", "gpt-5.3-codex")
            provider.setdefault("model_env", "ROCM_DOCTOR_OPENAI_MODEL")
            provider.setdefault("timeout_seconds", 30.0)
            provider.setdefault("retry", {})
            provider["retry"].setdefault("max_attempts", 1)
            provider["retry"].setdefault("backoff_seconds", 0.0)
            provider["retry"].setdefault("retry_status_codes", [408, 409, 429, 500, 502, 503, 504])
            provider["retry"].setdefault("retry_on_timeout", True)
            provider["retry"].setdefault("retry_on_invalid_json", True)
            provider.setdefault("templates", {})
            provider["templates"].setdefault("diagnosis_system", "../templates/openai_diagnosis_system.j2")
            provider["templates"].setdefault("repair_system", "../templates/openai_repair_system.j2")
        elif provider["type"] == "anthropic-messages":
            provider.setdefault("endpoint", "https://api.anthropic.com/v1/messages")
            provider.setdefault("api_key_env", "ANTHROPIC_API_KEY")
            provider.setdefault("api_version", "2023-06-01")
            provider.setdefault("model", "claude-sonnet-4-6")
            provider.setdefault("model_env", "ROCM_DOCTOR_ANTHROPIC_MODEL")
            provider.setdefault("timeout_seconds", 30.0)
            provider.setdefault("max_tokens", 1024)
            provider.setdefault("retry", {})
            provider["retry"].setdefault("max_attempts", 1)
            provider["retry"].setdefault("backoff_seconds", 0.0)
            provider["retry"].setdefault("retry_status_codes", [408, 409, 429, 500, 502, 503, 504])
            provider["retry"].setdefault("retry_on_timeout", True)
            provider["retry"].setdefault("retry_on_invalid_json", True)
            provider.setdefault("templates", {})
            provider["templates"].setdefault("diagnosis_system", "../templates/openai_diagnosis_system.j2")
            provider["templates"].setdefault("repair_system", "../templates/openai_repair_system.j2")
        elif provider["type"] == "openai-chat-completions":
            provider.setdefault("base_url", "https://api.openai.com/v1")
            provider.setdefault("api_key_env", "OPENAI_API_KEY")
            provider.setdefault("model", "gpt-4o-mini")
            provider.setdefault("model_env", "ROCM_DOCTOR_OPENAI_COMPATIBLE_MODEL")
            provider.setdefault("timeout_seconds", 30.0)
            provider.setdefault("require_api_key", True)
            provider.setdefault("supports_json_schema", True)
            provider.setdefault("supports_json_object", True)
            provider.setdefault("retry", {})
            provider["retry"].setdefault("max_attempts", 1)
            provider["retry"].setdefault("backoff_seconds", 0.0)
            provider["retry"].setdefault("retry_status_codes", [408, 409, 429, 500, 502, 503, 504])
            provider["retry"].setdefault("retry_on_timeout", True)
            provider["retry"].setdefault("retry_on_invalid_json", True)
            provider.setdefault("templates", {})
            provider["templates"].setdefault("diagnosis_system", "../templates/openai_diagnosis_system.j2")
            provider["templates"].setdefault("repair_system", "../templates/openai_repair_system.j2")
    if data["active_provider"] not in providers:
        raise ConfigError(f"active diagnosis provider is not configured: {data['active_provider']}")
    return data


def _normalize_hardware(hardware: Any) -> dict[str, Any]:
    if not isinstance(hardware, dict):
        raise ConfigError("hardware must be an object")
    data = deepcopy(hardware)
    data.setdefault("backend", "local")
    data.setdefault("accelerator", "none")
    data.setdefault("runtime", "fake")
    data.setdefault("deployment_target", "developer-laptop")
    data.setdefault("amd", {})
    data["amd"].setdefault("rocm_required", False)
    data["amd"].setdefault("device_flags", ["/dev/kfd", "/dev/dri"])
    data["amd"].setdefault("benchmark_profile", "local")
    return data


def _validate_config(config: dict[str, Any]) -> None:
    for provider_id in config["model_providers"]:
        if "." in provider_id:
            raise ConfigError("model provider ids may not contain dots because repair paths are dotted")
    active = str(config["active_model_provider"])
    provider = config["model_providers"][active]
    if provider["adapter"] != "openai-compatible":
        raise ConfigError(f"unsupported model provider adapter: {provider['adapter']}")
    endpoint = provider["model"]["endpoint"]
    if provider["capabilities"].get("models") and not endpoint["base_url"]:
        raise ConfigError(f"model provider {active} must configure model.endpoint.base_url")
    context = provider["model"]["context"]
    max_tokens = _int_or_error(context["max_tokens"], f"{active}.model.context.max_tokens")
    safe_tokens = _int_or_error(context["safe_max_tokens"], f"{active}.model.context.safe_max_tokens")
    if max_tokens <= 0 or safe_tokens <= 0:
        raise ConfigError("context token limits must be positive")
    request = provider["request"]
    attempts = _int_or_error(request["retry"]["max_attempts"], f"{active}.request.retry.max_attempts")
    if attempts <= 0:
        raise ConfigError("retry.max_attempts must be positive")
    timeout = _float_or_error(request["timeout_seconds"], f"{active}.request.timeout_seconds")
    if timeout <= 0:
        raise ConfigError("request.timeout_seconds must be positive")


def _int_or_error(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be an integer") from exc


def _float_or_error(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be a number") from exc


def _bump_default_endpoint(url: str) -> str:
    if not url:
        return ""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(str(url))
    host = parsed.hostname or "127.0.0.1"
    port = (parsed.port or 8000) + 1
    return urlunparse((parsed.scheme or "http", f"{host}:{port}", parsed.path or "/v1", "", "", ""))


def _strip_normalized_only_keys(config: dict[str, Any]) -> dict[str, Any]:
    return config


def resolve_workspace(config_path: str | Path, config: dict[str, Any]) -> Path:
    base = Path(config_path).resolve().parent
    workspace = Path(str(config.get("workspace", ".")))
    if not workspace.is_absolute():
        workspace = base / workspace
    return workspace.resolve()


def resolve_reports_dir(config_path: str | Path, config: dict[str, Any]) -> Path:
    reports_dir = Path(str(config.get("reports_dir", "reports")))
    if not reports_dir.is_absolute():
        reports_dir = resolve_workspace(config_path, config) / reports_dir
    return reports_dir.resolve()


def resolve_state_path(config_path: str | Path, config: dict[str, Any]) -> Path:
    state_file = Path(str(config.get("state_file", ".rocm-doctor-state.json")))
    if not state_file.is_absolute():
        state_file = resolve_workspace(config_path, config) / state_file
    return state_file.resolve()


def get_dotted(data: dict[str, Any], dotted_key: str) -> Any:
    cursor: Any = data
    for part in dotted_key.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise KeyError(dotted_key)
        cursor = cursor[part]
    return cursor


def set_dotted(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    cursor: Any = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        if not isinstance(cursor, dict):
            raise KeyError(dotted_key)
        cursor = cursor.setdefault(part, {})
    if not isinstance(cursor, dict):
        raise KeyError(dotted_key)
    cursor[parts[-1]] = value


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    return _redact(deepcopy(config))


def contains_sensitive_key(dotted_key: str) -> bool:
    lowered = dotted_key.lower()
    phrase_matches = ("api_key", "apikey", "access_token", "auth_token", "bearer_token")
    if any(phrase in lowered for phrase in phrase_matches):
        return True
    parts = re.split(r"[.\-/]", lowered)
    return any(part in {"token", "secret", "password", "credential", "credentials"} for part in parts)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if contains_sensitive_key(str(key)):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True
