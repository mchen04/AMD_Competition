from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .schemas import RuntimeProfile


SENSITIVE_KEY_PARTS = ("api_key", "apikey", "token", "secret", "password", "credential")
DEFAULT_PROFILE_ID = "fake-openai"


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
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config file is not valid JSON/YAML-compatible JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be an object")
    return normalize_config(data)


def save_config(path: str | Path, config: dict[str, Any]) -> None:
    config_path = Path(path)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(config)
    data.setdefault("workspace", ".")
    data.setdefault("reports_dir", "reports")
    data.setdefault("state_file", ".rocm-doctor-state.json")
    data.setdefault("active_profile", data.get("profile_id", DEFAULT_PROFILE_ID))
    data.setdefault("model", {})
    data.setdefault("launch", {})
    data.setdefault("service", {})
    data.setdefault("provider", {})
    model = data["model"]
    model.setdefault("name", "fake-qwen3")
    model.setdefault("base_url", "http://127.0.0.1:8000/v1")
    model.setdefault("expected_base_url", model["base_url"])
    model.setdefault("wrong_base_url", "http://127.0.0.1:8001/v1")
    model.setdefault("max_model_len", 2048)
    model.setdefault("safe_max_model_len", 4096)
    model.setdefault("tool_parser", "qwen3")
    model.setdefault("expected_tool_parser", "qwen3")
    model.setdefault("tool_check_enabled", True)
    launch = data["launch"]
    launch.setdefault("device_flags", ["/dev/kfd", "/dev/dri"])
    launch.setdefault("required_device_flags", ["/dev/kfd", "/dev/dri"])
    service = data["service"]
    service.setdefault("name", "fake-vllm")
    service.setdefault("restart_count", 0)
    service.setdefault("restart_mode", "dry-run")
    data["provider"].setdefault("fake", {"mode": "normal"})
    data["profiles"] = _normalize_profiles(data)
    return data


def get_active_profile(config: dict[str, Any]) -> RuntimeProfile:
    data = normalize_config(config)
    profile_id = str(data.get("active_profile", DEFAULT_PROFILE_ID))
    profile = data["profiles"].get(profile_id)
    if not isinstance(profile, dict):
        raise ConfigError(f"active profile is not configured: {profile_id}")

    model = data["model"]
    context = profile.get("context", {})
    tool_calling = profile.get("tool_calling", {})
    capabilities = {
        str(key): bool(value) for key, value in dict(profile.get("capabilities", {})).items()
    }
    signatures = {
        str(key): [str(item) for item in value]
        for key, value in dict(profile.get("known_failure_signatures", {})).items()
        if isinstance(value, list)
    }
    return RuntimeProfile(
        id=profile_id,
        runtime_type=str(profile.get("runtime_type", "fake")),
        endpoint_protocol=str(profile.get("endpoint_protocol", "openai-compatible")),
        model_name=str(model.get("name", profile.get("model_name", "fake-qwen3"))),
        base_url=str(model.get("base_url", "http://127.0.0.1:8000/v1")),
        expected_base_url=str(model.get("expected_base_url", model.get("base_url", ""))),
        wrong_base_url=str(model.get("wrong_base_url", "http://127.0.0.1:8001/v1")),
        capabilities=capabilities,
        max_model_len=_int_or_default(model.get("max_model_len"), 2048),
        safe_max_model_len=_int_or_default(
            model.get("safe_max_model_len", context.get("safe_max_model_len", 4096)), 4096
        ),
        request_timeout_seconds=_float_or_default(profile.get("request_timeout_seconds"), 1.5),
        tool_parser=str(model.get("tool_parser", tool_calling.get("configured_parser", ""))),
        expected_tool_parser=str(
            model.get("expected_tool_parser", tool_calling.get("expected_parser", ""))
        ),
        tool_check_enabled=bool(model.get("tool_check_enabled", capabilities.get("tool_calls", False))),
        health_probes=[str(item) for item in profile.get("health_probes", [])],
        known_failure_signatures=signatures,
        safe_repair_recipes=[str(item) for item in profile.get("safe_repair_recipes", [])],
        skip_reasons={
            str(key): str(value) for key, value in dict(profile.get("skip_reasons", {})).items()
        },
    )


def _normalize_profiles(config: dict[str, Any]) -> dict[str, Any]:
    raw_profiles = config.get("profiles", {})
    profiles: dict[str, Any] = dict(raw_profiles) if isinstance(raw_profiles, dict) else {}
    active = str(config.get("active_profile", DEFAULT_PROFILE_ID))
    existing = profiles.get(active, {})
    if not isinstance(existing, dict):
        existing = {}
    profiles[active] = _merge_dicts(_profile_defaults(active, config), existing)
    return profiles


def _profile_defaults(profile_id: str, config: dict[str, Any]) -> dict[str, Any]:
    lowered = profile_id.lower()
    if "ollama" in lowered or "qwen" in lowered:
        return _ollama_qwen_profile_defaults(config)
    if "vllm" in lowered or "amd" in lowered:
        return _vllm_amd_profile_defaults(config)
    return _fake_profile_defaults(config)


def _fake_profile_defaults(config: dict[str, Any]) -> dict[str, Any]:
    model = config["model"]
    return {
        "id": "fake-openai",
        "runtime_type": "fake",
        "endpoint_protocol": "openai-compatible",
        "model_name": model.get("name", "fake-qwen3"),
        "capabilities": {
            "models": True,
            "chat_completions": True,
            "tool_calls": True,
            "context_length": True,
            "rocm_device_flags": True,
            "restart": True,
        },
        "context": {"safe_max_model_len": model.get("safe_max_model_len", 4096)},
        "request_timeout_seconds": 1.5,
        "tool_calling": {"expected_parser": model.get("expected_tool_parser", "qwen3")},
        "health_probes": [
            "endpoint_models",
            "chat_completion",
            "context_length",
            "rocm_device_flags",
            "tool_call_parser",
        ],
        "known_failure_signatures": {
            "wrong_endpoint_port": ["GET /v1/models failed", "configured URL differs from expected URL"],
            "context_length_too_large": ["max_model_len exceeds safe_max_model_len"],
            "tool_parser_mismatch": ["response did not contain a tool call"],
            "missing_rocm_device_flags": ["missing ROCm device flags"],
        },
        "safe_repair_recipes": [
            "noop",
            "update_endpoint_url",
            "lower_max_model_len",
            "set_tool_parser",
            "set_rocm_device_flags",
            "restart_known_service",
        ],
        "skip_reasons": {},
    }


def _ollama_qwen_profile_defaults(config: dict[str, Any]) -> dict[str, Any]:
    model = config["model"]
    return {
        "id": "ollama-qwen",
        "runtime_type": "ollama",
        "endpoint_protocol": "openai-compatible",
        "model_name": model.get("name", "qwen3:0.6b"),
        "capabilities": {
            "models": True,
            "chat_completions": True,
            "tool_calls": False,
            "context_length": True,
            "rocm_device_flags": False,
            "restart": False,
        },
        "context": {"safe_max_model_len": model.get("safe_max_model_len", 2048)},
        "request_timeout_seconds": 30.0,
        "tool_calling": {"expected_parser": model.get("expected_tool_parser", "")},
        "health_probes": ["endpoint_models", "chat_completion", "context_length"],
        "known_failure_signatures": {
            "wrong_endpoint_port": ["GET /v1/models failed", "configured URL differs from expected URL"],
            "context_length_too_large": ["max_model_len exceeds safe_max_model_len"],
        },
        "safe_repair_recipes": ["noop", "update_endpoint_url", "lower_max_model_len"],
        "skip_reasons": {
            "tool_calls": "ollama-qwen profile does not require native OpenAI tool-call output",
            "rocm_device_flags": "local Ollama does not use ROCm container device flags",
            "restart": "ROCm Doctor does not control the local Ollama service",
        },
    }


def _vllm_amd_profile_defaults(config: dict[str, Any]) -> dict[str, Any]:
    defaults = _fake_profile_defaults(config)
    defaults.update(
        {
            "id": "vllm-amd",
            "runtime_type": "amd-vllm",
            "model_name": config["model"].get("name", "qwen3"),
            "safe_repair_recipes": [
                "noop",
                "update_endpoint_url",
                "lower_max_model_len",
                "set_tool_parser",
                "set_rocm_device_flags",
                "restart_known_service",
            ],
        }
    )
    return defaults


def _merge_dicts(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS):
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
