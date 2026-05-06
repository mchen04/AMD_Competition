#!/usr/bin/env python3
"""Supervisor stability soak.

Loops `cycles` rounds (default 100). Each cycle:
  - Randomly injects one of the 4 real failure scenarios on a fresh working copy
    that shares a single workspace (so learned-fix state accumulates across cycles).
  - Calls `self_heal_config` directly.
  - Calls `verify_config`.
  - Records time-to-heal, attempts, and whether the fix came from the
    learned-fix path or the deterministic taxonomy.

Writes a JSON summary at `chaos-supervisor-<date>.json` and prints a one-line
verdict.

Pass criteria (default thresholds):
  * 100% of injected scenarios heal.
  * Mean attempts <= 1.5 once the second half of the run is reached
    (proves learned fixes are saving cycles).

Run directly:
  scripts/chaos_supervisor.py --cycles 100 --seed 0
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from rocm_doctor.config import load_config
from rocm_doctor.failure_injection import inject_failure
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.operations import self_heal_config, verify_config
from rocm_doctor.state import load_state


REAL_SCENARIOS = (
    "wrong_endpoint_port",
    "context_length_too_large",
    "tool_parser_mismatch",
    "missing_rocm_device_flags",
)

EXPECTED_RECIPES = {
    "wrong_endpoint_port": "update_endpoint_url",
    "context_length_too_large": "lower_max_model_len",
    "tool_parser_mismatch": "set_tool_parser",
    "missing_rocm_device_flags": "set_rocm_device_flags",
}


def _build_config(workspace: Path, base_url: str) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    source = yaml.safe_load((REPO_ROOT / "demo/rocm-doctor.yaml").read_text(encoding="utf-8"))
    provider = source["model_providers"]["fake-openai"]
    provider["runtime_type"] = "harness-test"
    provider["model"]["id"] = "qwen3:0.6b"
    provider["model"]["endpoint"]["base_url"] = base_url
    provider["model"]["endpoint"]["expected_base_url"] = base_url
    provider["model"]["endpoint"]["wrong_base_url"] = "http://127.0.0.1:9/v1"
    provider["model"]["context"]["max_tokens"] = 128
    provider["model"]["context"]["safe_max_tokens"] = 256
    provider["model"]["tool_calling"]["enabled"] = True
    provider["model"]["tool_calling"]["parser"] = "qwen3"
    provider["model"]["tool_calling"]["expected_parser"] = "qwen3"
    provider["capabilities"]["tool_calls"] = True
    provider["request"]["timeout_seconds"] = 1.0
    provider["request"]["stream"] = False
    provider["request"]["retry"]["max_attempts"] = 1
    provider["templates"]["health_chat"] = str((REPO_ROOT / "templates/health_chat.j2").resolve())
    provider["templates"]["tool_call"] = str((REPO_ROOT / "templates/tool_call_prompt.j2").resolve())
    source["workspace"] = str(workspace)
    source["reports_dir"] = str(workspace / "reports")
    source["state_file"] = str(workspace / ".state.json")
    config_path = workspace / "config.yaml"
    config_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    assert load_config(config_path)
    return config_path


def _was_learned_fix(state_before: dict, scenario: str, recipe_id: str) -> bool:
    fixes = (
        state_before.get("learned_fixes", {})
        .get("fake-openai", {})
        .get(_failure_class_for_scenario(scenario), [])
    )
    for entry in fixes:
        if isinstance(entry, dict) and entry.get("successful_fix") == recipe_id:
            return True
    return False


def _failure_class_for_scenario(scenario: str) -> str:
    # Scenario name == failure_class for the four real scenarios.
    return scenario


def _baseline_config(config_path: Path) -> dict:
    return deepcopy(load_config(config_path))


def _restore(config_path: Path, baseline: dict) -> None:
    config_path.write_text(yaml.safe_dump(baseline, sort_keys=False), encoding="utf-8")


def run(cycles: int, seed: int, output_path: Path) -> dict:
    rng = random.Random(seed)
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        workspace = (output_path.parent / f"chaos-supervisor-workspace-{int(time.time())}").resolve()
        config_path = _build_config(workspace, server.base_url)
        baseline = _baseline_config(config_path)
        rounds: list[dict] = []
        try:
            rounds = _run_rounds(rng, cycles, config_path, baseline)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    summary = _summarize(rounds, cycles, started_at, seed)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _run_rounds(rng: random.Random, cycles: int, config_path: Path, baseline: dict) -> list[dict]:
    rounds: list[dict] = []
    for round_idx in range(cycles):
        scenario = rng.choice(REAL_SCENARIOS)
        _restore(config_path, baseline)
        inject_failure(config_path, scenario)
        state_before = load_state(config_path)

        start = time.perf_counter()
        heal = self_heal_config(config_path, provider_name="rules")
        heal_ms = int((time.perf_counter() - start) * 1000)

        verify = verify_config(config_path)

        recipe = heal.repairs[-1].recipe_id if heal.repairs else ""
        learned = _was_learned_fix(state_before, scenario, recipe)
        expected = EXPECTED_RECIPES[scenario]
        healed_ok = bool(heal.healthy and verify.healthy and recipe == expected)

        rounds.append(
            {
                "round": round_idx,
                "scenario": scenario,
                "recipe": recipe,
                "expected_recipe": expected,
                "attempts": int(heal.attempts),
                "healed": healed_ok,
                "learned_fix_replay": learned,
                "duration_ms": heal_ms,
                "verify_healthy": bool(verify.healthy),
            }
        )
    return rounds


def _summarize(rounds: list[dict], cycles: int, started_at: str, seed: int) -> dict:
    healed = [r for r in rounds if r["healed"]]
    second_half = rounds[len(rounds) // 2 :]
    second_half_attempts = [r["attempts"] for r in second_half] or [0]
    learned_replays = sum(1 for r in rounds if r["learned_fix_replay"])
    heal_rate = len(healed) / max(1, len(rounds))
    mean_attempts_second_half = statistics.fmean(second_half_attempts)
    mean_duration_ms = statistics.fmean([r["duration_ms"] for r in rounds]) if rounds else 0.0

    pass_heal_rate = heal_rate >= 1.0
    pass_attempts = mean_attempts_second_half <= 1.5

    return {
        "started_at": started_at,
        "cycles": cycles,
        "seed": seed,
        "heal_rate": heal_rate,
        "mean_attempts_second_half": mean_attempts_second_half,
        "mean_duration_ms": mean_duration_ms,
        "learned_fix_replays": learned_replays,
        "pass": pass_heal_rate and pass_attempts,
        "pass_heal_rate": pass_heal_rate,
        "pass_attempts": pass_attempts,
        "rounds": rounds,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output path (defaults to chaos-supervisor-<UTC>.json under cwd)",
    )
    args = parser.parse_args(argv)

    if args.output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.output = Path.cwd() / f"chaos-supervisor-{stamp}.json"

    summary = run(args.cycles, args.seed, args.output)
    verdict = "PASS" if summary["pass"] else "FAIL"
    print(
        f"chaos_supervisor: {verdict} "
        f"heal_rate={summary['heal_rate']:.2%} "
        f"mean_attempts_2h={summary['mean_attempts_second_half']:.2f} "
        f"learned_replays={summary['learned_fix_replays']} "
        f"output={args.output}"
    )
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
