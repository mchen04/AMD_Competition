"""Continuous supervisor — the CI/CD loop wrapped around ``self_heal_config``.

Single responsibility: run ``check → (if unhealthy) classify_intent → heal →
verify`` on a fixed cadence, forever, until told to stop. The heal logic is
unchanged — every interval calls into ``self_heal_config`` so all the
recipe / executor / state / intent plumbing already works without forks.

Cooldowns:
  - ``cooldown_seconds_after_heal`` keeps the supervisor from immediately
    re-firing after a successful repair while verification stabilizes.
  - ``cooldown_seconds_after_intent_skip`` keeps the supervisor from spamming
    the same intentional-change conclusion every interval — record once, wait.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import load_config
from .operations import self_heal_config
from .schemas import to_jsonable
from .state import load_state, record_stage
from .timeutil import utc_now


EventEmitter = Callable[[str, dict[str, Any]], None]

DEFAULT_CYCLE_HISTORY_LIMIT = 50


@dataclass
class SupervisionConfig:
    interval_seconds: float
    until_pass: bool
    cooldown_after_heal: float
    cooldown_after_intent_skip: float
    max_iterations: int  # 0 = unbounded
    cycle_history_limit: int

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        interval_seconds: float | None = None,
        until_pass: bool | None = None,
        max_iterations: int | None = None,
    ) -> "SupervisionConfig":
        block = (config.get("supervision") or {}) if isinstance(config, dict) else {}
        return cls(
            interval_seconds=float(
                interval_seconds
                if interval_seconds is not None
                else block.get("interval_seconds", 30)
            ),
            until_pass=bool(
                until_pass if until_pass is not None else block.get("until_pass", False)
            ),
            cooldown_after_heal=float(block.get("cooldown_seconds_after_heal", 60)),
            cooldown_after_intent_skip=float(
                block.get("cooldown_seconds_after_intent_skip", 300)
            ),
            max_iterations=int(0 if max_iterations is None else max_iterations),
            cycle_history_limit=int(
                block.get("cycle_history_limit", DEFAULT_CYCLE_HISTORY_LIMIT)
            ),
        )


def supervise_config(
    config_path: str | Path,
    *,
    provider_name: str = "rules",
    interval_seconds: float | None = None,
    until_pass: bool | None = None,
    on_event: EventEmitter | None = None,
    stop_event: threading.Event | None = None,
    max_iterations: int = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run the continuous CI/CD loop until ``stop_event`` is set.

    Returns a summary dict (iterations, last result, stop reason).
    """
    config = load_config(config_path)
    settings = SupervisionConfig.from_config(
        config,
        interval_seconds=interval_seconds,
        until_pass=until_pass,
        max_iterations=max_iterations,
    )
    stop = stop_event or threading.Event()
    emit: EventEmitter = on_event or (lambda _name, _data: None)

    iterations = 0
    last_status: dict[str, Any] = {}
    stop_reason = "stop_requested"
    record_stage(config_path, "supervisor_started_at", utc_now())
    emit("supervisor.started", {
        "interval_seconds": settings.interval_seconds,
        "until_pass": settings.until_pass,
        "provider": provider_name,
    })

    try:
        while not stop.is_set():
            iterations += 1
            cycle_start = time.time()
            cycle_started_at = utc_now()
            emit("cycle.started", {"iteration": iterations, "ts": cycle_started_at})
            try:
                result = self_heal_config(
                    config_path,
                    provider_name=provider_name,
                    max_attempts_override=10**6 if settings.until_pass else None,
                )
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc)
                emit("cycle.error", {
                    "iteration": iterations,
                    "error": error_msg,
                    "traceback": traceback.format_exc(limit=4),
                })
                last_status = {"healthy": False, "error": error_msg}
                error_elapsed = time.time() - cycle_start
                _record_cycle(
                    config_path,
                    settings,
                    iteration=iterations,
                    ts=cycle_started_at,
                    outcome="error",
                    recovered=False,
                    reason=error_msg,
                    elapsed_seconds=error_elapsed,
                    diagnosis=None,
                )
                _wait(stop, settings.interval_seconds, sleep)
                if settings.max_iterations and iterations >= settings.max_iterations:
                    stop_reason = "max_iterations"
                    break
                continue

            payload = to_jsonable(result)
            last_status = payload
            healthy = bool(getattr(result, "healthy", False))
            recovered = bool(getattr(result, "recovered", False))
            unrecoverable = bool(getattr(result, "unrecoverable", False))
            reason = getattr(result, "reason", "")

            persisted = load_state(config_path)
            intent_dict = persisted.get("intent") if isinstance(persisted, dict) else None
            diagnosis_dict = persisted.get("diagnosis") if isinstance(persisted, dict) else None
            diagnosis_summary = _summarize_diagnosis(diagnosis_dict)

            if healthy:
                outcome = "healthy"
                emit("cycle.healthy", {
                    "iteration": iterations,
                    "recovered": recovered,
                    "intent": intent_dict,
                    "diagnosis": diagnosis_summary,
                    "result": payload,
                })
                cooldown = settings.cooldown_after_heal if recovered else settings.interval_seconds
            elif unrecoverable and not recovered:
                # Intent classifier said record_only / ask_human, or heal exhausted.
                outcome = "skipped"
                emit("cycle.skipped", {
                    "iteration": iterations,
                    "reason": reason,
                    "intent": intent_dict,
                    "diagnosis": diagnosis_summary,
                    "result": payload,
                })
                cooldown = settings.cooldown_after_intent_skip
            else:
                outcome = "unhealthy"
                emit("cycle.unhealthy", {
                    "iteration": iterations,
                    "reason": reason,
                    "intent": intent_dict,
                    "diagnosis": diagnosis_summary,
                    "result": payload,
                })
                cooldown = settings.interval_seconds

            elapsed = time.time() - cycle_start
            wait_for = max(0.0, cooldown - elapsed)
            emit("cycle.completed", {
                "iteration": iterations,
                "next_check_in_seconds": wait_for,
                "elapsed_seconds": elapsed,
            })

            _record_cycle(
                config_path,
                settings,
                iteration=iterations,
                ts=cycle_started_at,
                outcome=outcome,
                recovered=recovered,
                reason=reason,
                elapsed_seconds=elapsed,
                diagnosis=diagnosis_summary,
                intent=intent_dict,
            )

            if settings.max_iterations and iterations >= settings.max_iterations:
                stop_reason = "max_iterations"
                break

            _wait(stop, wait_for, sleep)
    finally:
        record_stage(config_path, "supervisor_stopped_at", utc_now())
        emit("supervisor.stopped", {
            "iterations": iterations,
            "stop_reason": stop_reason,
            "last_status": last_status,
        })

    return {
        "iterations": iterations,
        "stop_reason": stop_reason,
        "last_status": last_status,
    }


def _wait(stop: threading.Event, seconds: float, sleep: Callable[[float], None]) -> None:
    if seconds <= 0:
        return
    if stop.wait(timeout=seconds):
        return
    # Fallback for stop_event surrogates that don't honour wait()
    sleep(0)


def _summarize_diagnosis(diagnosis: Any) -> dict[str, Any] | None:
    if not isinstance(diagnosis, dict):
        return None
    return {
        "failure_class": diagnosis.get("failure_class", ""),
        "suspected_cause": diagnosis.get("suspected_cause", ""),
    }


def _record_cycle(
    config_path: str | Path,
    settings: SupervisionConfig,
    *,
    iteration: int,
    ts: str,
    outcome: str,
    recovered: bool,
    reason: str,
    elapsed_seconds: float,
    diagnosis: dict[str, Any] | None,
    intent: Any = None,
) -> None:
    state = load_state(config_path)
    history = state.get("supervisor_cycles", [])
    if not isinstance(history, list):
        history = []
    entry: dict[str, Any] = {
        "iteration": int(iteration),
        "ts": ts,
        "outcome": outcome,
        "recovered": bool(recovered),
        "reason": reason or "",
        "elapsed_seconds": round(float(elapsed_seconds), 4),
    }
    if diagnosis:
        entry["diagnosis"] = diagnosis
    if isinstance(intent, dict):
        entry["intent"] = intent
    limit = max(1, int(settings.cycle_history_limit or DEFAULT_CYCLE_HISTORY_LIMIT))
    trimmed = (history + [entry])[-limit:]
    record_stage(config_path, "supervisor_cycles", trimmed)


__all__ = ["supervise_config", "SupervisionConfig"]
