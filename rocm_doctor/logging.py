"""Centralized logging setup — one dictConfig at process start."""

from __future__ import annotations

import logging
import logging.config
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_CONFIG_PATH = Path(__file__).resolve().parent / "logging.yaml"


@lru_cache(maxsize=1)
def _load_dict_config() -> dict[str, Any]:
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise RuntimeError(f"{_CONFIG_PATH} must be a YAML object")
    return raw


_CONFIGURED = False


def configure_logging() -> None:
    """Apply the dictConfig once. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.config.dictConfig(_load_dict_config())
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
