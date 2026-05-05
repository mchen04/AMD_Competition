from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from .config import load_config, save_config


SCENARIOS = {
    "wrong_endpoint_port",
    "context_length_too_large",
    "tool_parser_mismatch",
    "missing_rocm_device_flags",
    "malformed_provider_output",
    "unknown_recipe",
    "unsafe_command",
    "path_traversal",
    "credential_modification",
}


def inject_failure(config_path: str | Path, scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown failure scenario: {scenario}")
    config = load_config(config_path)
    before = _snapshot_bits(config)
    provider_id = str(config["active_model_provider"])
    provider = config["model_providers"][provider_id]

    if scenario == "wrong_endpoint_port":
        endpoint = provider["model"]["endpoint"]
        endpoint["base_url"] = endpoint.get("wrong_base_url") or _bump_port(str(endpoint["base_url"]))
    elif scenario == "context_length_too_large":
        context = provider["model"]["context"]
        safe = int(context.get("safe_max_tokens", 4096))
        context["max_tokens"] = max(safe + 1, safe * 2)
    elif scenario == "tool_parser_mismatch":
        provider["model"]["tool_calling"]["parser"] = "wrong-parser"
    elif scenario == "missing_rocm_device_flags":
        required = set(map(str, config["launch"].get("required_device_flags", [])))
        config["launch"]["device_flags"] = [
            flag for flag in config["launch"].get("device_flags", []) if str(flag) not in required
        ]
    elif scenario == "malformed_provider_output":
        _set_fake_mode(config, "invalid_schema")
    elif scenario == "unknown_recipe":
        _set_fake_mode(config, "unknown_recipe")
    elif scenario == "unsafe_command":
        _set_fake_mode(config, "unsafe_command")
    elif scenario == "path_traversal":
        _set_fake_mode(config, "path_traversal")
    elif scenario == "credential_modification":
        _set_fake_mode(config, "credential_modification")

    save_config(config_path, config)
    return {"scenario": scenario, "before": before, "after": _snapshot_bits(config)}


def _set_fake_mode(config: dict[str, Any], mode: str) -> None:
    config.setdefault("diagnosis", {}).setdefault("providers", {}).setdefault("fake", {"type": "fake"})[
        "mode"
    ] = mode


def _bump_port(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = (parsed.port or 8000) + 1
    netloc = f"{host}:{port}"
    return urlunparse((parsed.scheme or "http", netloc, parsed.path or "/v1", "", "", ""))


def _snapshot_bits(config: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(config["active_model_provider"])
    provider = config["model_providers"][provider_id]
    return {
        "model_provider": provider_id,
        "base_url": provider["model"]["endpoint"].get("base_url"),
        "max_model_len": provider["model"]["context"].get("max_tokens"),
        "tool_parser": provider["model"]["tool_calling"].get("parser"),
        "device_flags": config["launch"].get("device_flags"),
        "fake_provider_mode": config.get("diagnosis", {}).get("providers", {}).get("fake", {}).get("mode"),
    }
