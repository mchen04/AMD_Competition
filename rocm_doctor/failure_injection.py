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
    "rocm_oom_inference",
    "max_model_len_mismatch",
    "malformed_provider_output",
    "unknown_recipe",
    "unsafe_command",
    "path_traversal",
    "credential_modification",
}


# Categorises every injectable scenario:
#   "heal"   — mutates the active model provider's YAML so a real probe fails;
#              expected outcome is `update_endpoint_url`/`lower_max_model_len`/etc.
#              firing and verifying healthy.
#   "safety" — leaves the endpoint healthy but switches the FakeProvider into a
#              malicious-output mode; expected outcome is the executor's safety
#              gate rejecting the fake brain's recipe (use `provider_name=fake`).
#   Failure classes from failures.yaml that have no entry here are taxonomy-only:
#   the diagnosis can emit them when fed real evidence (e.g. via the adversarial
#   proxy) but the dashboard's Inject button can't trigger them directly.
SCENARIO_KINDS: dict[str, str] = {
    "wrong_endpoint_port": "heal",
    "context_length_too_large": "heal",
    "tool_parser_mismatch": "heal",
    "missing_rocm_device_flags": "heal",
    "rocm_oom_inference": "heal",
    "max_model_len_mismatch": "heal",
    "malformed_provider_output": "safety",
    "unknown_recipe": "safety",
    "unsafe_command": "safety",
    "path_traversal": "safety",
    "credential_modification": "safety",
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
    elif scenario == "rocm_oom_inference":
        launch = config.setdefault("launch", {})
        vllm_args = launch.setdefault("vllm_args", {})
        vllm_args["gpu_memory_utilization"] = 0.99
        _set_fake_mode(config, "hip_oom")
    elif scenario == "max_model_len_mismatch":
        # Server reports a max_model_len lower than what the harness has configured.
        context = provider["model"]["context"]
        safe = int(context.get("safe_max_tokens", 4096))
        context["max_tokens"] = max(safe + 1, safe * 2)
        _set_fake_mode(config, "max_model_len_exceeded")
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
    launch = config.get("launch", {}) or {}
    vllm_args = launch.get("vllm_args", {}) or {}
    return {
        "model_provider": provider_id,
        "base_url": provider["model"]["endpoint"].get("base_url"),
        "max_model_len": provider["model"]["context"].get("max_tokens"),
        "tool_parser": provider["model"]["tool_calling"].get("parser"),
        "device_flags": launch.get("device_flags"),
        "gpu_memory_utilization": vllm_args.get("gpu_memory_utilization"),
        "fake_provider_mode": config.get("diagnosis", {}).get("providers", {}).get("fake", {}).get("mode"),
    }
