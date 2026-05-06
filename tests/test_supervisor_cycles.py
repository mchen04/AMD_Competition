"""Supervisor cycle history persistence.

Verifies that ``supervise_config`` accumulates a bounded ``supervisor_cycles``
list in state.json across iterations, capturing outcome (healthy / unhealthy /
skipped / error), intent, and diagnosis summary so the Incidents timeline can
narrate what the supervisor did, cycle by cycle.
"""

from __future__ import annotations

import threading
from pathlib import Path

import yaml

from rocm_doctor.config import load_config
from rocm_doctor.failure_injection import inject_failure
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.state import load_state
from rocm_doctor.supervisor import supervise_config


def _write_runtime_config(tmp_path: Path, base_url: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = yaml.safe_load(Path("demo/rocm-doctor.yaml").read_text(encoding="utf-8"))
    provider = source["model_providers"]["fake-openai"]
    provider["runtime_type"] = "harness-test"
    provider["model"]["id"] = "qwen3:0.6b"
    provider["model"]["endpoint"]["base_url"] = base_url
    provider["model"]["endpoint"]["expected_base_url"] = base_url
    provider["model"]["endpoint"]["wrong_base_url"] = "http://127.0.0.1:9/v1"
    provider["request"]["timeout_seconds"] = 1.0
    provider["request"]["stream"] = False
    provider["request"]["retry"]["max_attempts"] = 1
    provider["templates"]["health_chat"] = str(Path("templates/health_chat.j2").resolve())
    provider["templates"]["tool_call"] = str(Path("templates/tool_call_prompt.j2").resolve())
    source["workspace"] = "."
    source["reports_dir"] = "reports"
    source["state_file"] = ".state.json"
    source["supervision"] = {
        "enabled": True,
        "interval_seconds": 0,
        "until_pass": False,
        "cooldown_seconds_after_heal": 0,
        "cooldown_seconds_after_intent_skip": 0,
        "cycle_history_limit": 5,
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    assert load_config(config_path)
    return config_path


def test_supervisor_persists_cycle_history(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, base_url=server.base_url)

        # Cycle 1 starts unhealthy, supervisor heals it.
        inject_failure(config_path, "wrong_endpoint_port")
        stop_event = threading.Event()
        summary = supervise_config(
            config_path,
            provider_name="rules",
            interval_seconds=0,
            until_pass=False,
            stop_event=stop_event,
            max_iterations=3,
            sleep=lambda _s: None,
        )
        assert summary["iterations"] == 3, summary

        state = load_state(config_path)
        cycles = state.get("supervisor_cycles") or []
        assert len(cycles) == 3, cycles
        # First cycle observed the drift and healed it.
        first = cycles[0]
        assert first["iteration"] == 1
        assert first["outcome"] == "healthy"
        assert first["recovered"] is True
        assert first.get("diagnosis", {}).get("failure_class") in {
            "wrong_endpoint_port",
            "endpoint_unreachable",
        }
        # Subsequent cycles stay healthy and never re-fire a recovery.
        for entry in cycles[1:]:
            assert entry["outcome"] == "healthy"
            assert entry["recovered"] is False


def test_supervisor_cycle_history_is_bounded(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, base_url=server.base_url)

        stop_event = threading.Event()
        summary = supervise_config(
            config_path,
            provider_name="rules",
            interval_seconds=0,
            stop_event=stop_event,
            max_iterations=8,
            sleep=lambda _s: None,
        )
        assert summary["iterations"] == 8
        cycles = load_state(config_path).get("supervisor_cycles") or []
        # cycle_history_limit=5 in the test fixture, so we keep the tail.
        assert len(cycles) == 5
        iterations = [entry["iteration"] for entry in cycles]
        assert iterations == [4, 5, 6, 7, 8]
