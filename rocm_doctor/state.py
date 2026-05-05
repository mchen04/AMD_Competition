from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .config import load_config, redact_config, resolve_state_path
from .schemas import to_jsonable
from .timeutil import utc_now


def load_state(config_path: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    state_path = resolve_state_path(config_path, config)
    if not state_path.exists():
        return {}
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def load_state_lenient(config_path: str | Path) -> dict[str, Any]:
    candidates = [resolve_state_path_lenient(config_path), Path(config_path).resolve().parent / ".state.json"]
    seen: set[Path] = set()
    for state_path in candidates:
        state_path = state_path.resolve()
        if state_path in seen:
            continue
        seen.add(state_path)
        if not state_path.exists():
            continue
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def record_stage(config_path: str | Path, key: str, value: Any) -> None:
    config = load_config(config_path)
    state_path = resolve_state_path(config_path, config)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(config_path)
    state[key] = to_jsonable(value)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_last_known_good_config(config_path: str | Path, config: dict[str, Any]) -> None:
    _mutate_state(
        config_path,
        {
            "last_known_good_config": to_jsonable(deepcopy(config)),
            "last_known_good_config_redacted": redact_config(config),
            "last_known_good_at": utc_now(),
        },
    )


def record_successful_fix(
    config_path: str | Path,
    provider_id: str,
    failure_class: str,
    signature: str,
    recipe_id: str,
    changed_paths: list[str],
    values: dict[str, Any],
) -> None:
    state = load_state(config_path)
    learned = state.setdefault("learned_fixes", {})
    provider = learned.setdefault(provider_id, {})
    fixes = provider.setdefault(failure_class, [])
    entry = {
        "failure": failure_class,
        "successful_fix": recipe_id,
        "provider": provider_id,
        "signature": signature,
        "changed_paths": list(changed_paths),
        "values": to_jsonable(values),
        "last_used_at": utc_now(),
    }
    retained = [
        item
        for item in fixes
        if not (
            isinstance(item, dict)
            and item.get("signature") == signature
            and item.get("successful_fix") == recipe_id
        )
    ]
    retained.insert(0, entry)
    provider[failure_class] = retained[:10]
    _write_state(config_path, state)


def learned_recipe_ids(
    state: dict[str, Any], provider_id: str, failure_class: str, signature: str
) -> list[str]:
    fixes = (
        state.get("learned_fixes", {})
        .get(provider_id, {})
        .get(failure_class, [])
    )
    recipes: list[str] = []
    for item in fixes:
        if not isinstance(item, dict):
            continue
        if item.get("signature") not in {signature, "*"}:
            continue
        recipe_id = str(item.get("successful_fix", ""))
        if recipe_id and recipe_id not in recipes:
            recipes.append(recipe_id)
    return recipes


def restore_last_known_good_config(config_path: str | Path) -> dict[str, Any] | None:
    state = load_state_lenient(config_path)
    snapshot = state.get("last_known_good_config")
    if not isinstance(snapshot, dict):
        return None
    config_path = Path(config_path)
    config_path.write_text(yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return snapshot


def _mutate_state(config_path: str | Path, updates: dict[str, Any]) -> None:
    state = load_state(config_path)
    state.update(to_jsonable(updates))
    _write_state(config_path, state)


def _write_state(config_path: str | Path, state: dict[str, Any]) -> None:
    config = load_config(config_path)
    state_path = resolve_state_path(config_path, config)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_state_path_lenient(config_path: str | Path) -> Path:
    path = Path(config_path)
    raw: dict[str, Any] = {}
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            raw = parsed
    except (OSError, yaml.YAMLError):
        raw = {}
    workspace = Path(str(raw.get("workspace", ".")))
    if not workspace.is_absolute():
        workspace = path.resolve().parent / workspace
    state_file = Path(str(raw.get("state_file", ".rocm-doctor-state.json")))
    if not state_file.is_absolute():
        state_file = workspace / state_file
    return state_file.resolve()
