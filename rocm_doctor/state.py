from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import load_config, resolve_state_path
from .schemas import to_jsonable


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


def record_stage(config_path: str | Path, key: str, value: Any) -> None:
    config = load_config(config_path)
    state_path = resolve_state_path(config_path, config)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(config_path)
    state[key] = to_jsonable(value)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
