from __future__ import annotations

import random
from pathlib import Path

import pytest
import yaml

from rocm_doctor.config import load_config
from rocm_doctor.failure_injection import SCENARIOS, inject_failure
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.operations import heal_config, self_heal_config


REAL_SCENARIOS = {
    "wrong_endpoint_port": "update_endpoint_url",
    "context_length_too_large": "lower_max_model_len",
    "tool_parser_mismatch": "set_tool_parser",
    "missing_rocm_device_flags": "set_rocm_device_flags",
}

SAFETY_SCENARIOS = {
    "malformed_provider_output",
    "unknown_recipe",
    "unsafe_command",
    "path_traversal",
    "credential_modification",
}


def test_randomized_chaos_sweep_heals_real_and_rejects_safety(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert set(REAL_SCENARIOS).issubset(SCENARIOS)
    assert SAFETY_SCENARIOS.issubset(SCENARIOS)

    rng = random.Random(0)
    rounds = 50
    healed = 0
    rejected = 0
    scenario_pool = list(REAL_SCENARIOS) + list(SAFETY_SCENARIOS)

    for round_idx in range(rounds):
        scenario = rng.choice(scenario_pool)
        round_dir = tmp_path / f"round_{round_idx:02d}_{scenario}"
        with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
            config_path = _write_runtime_config(round_dir, base_url=server.base_url)

            if scenario in REAL_SCENARIOS:
                inject_failure(config_path, scenario)
                result = self_heal_config(config_path, provider_name="rules")
                assert result.healthy, f"round {round_idx} {scenario} did not heal: {result.reason}"
                assert result.repairs, f"round {round_idx} {scenario} produced no repairs"
                expected_recipe = REAL_SCENARIOS[scenario]
                final_recipe = result.repairs[-1].recipe_id
                assert final_recipe == expected_recipe, (
                    f"round {round_idx} {scenario} ended on recipe {final_recipe!r}, "
                    f"expected {expected_recipe!r}"
                )
                healed += 1
            else:
                # Stack a real failure under the safety failure so the brain has
                # something to plan on, then watch it get rejected.
                inject_failure(config_path, "tool_parser_mismatch")
                inject_failure(config_path, scenario)
                before_text = config_path.read_text(encoding="utf-8")

                repair = heal_config(config_path, provider_name="fake")

                assert repair.rejected, (
                    f"round {round_idx} {scenario} should have been rejected; "
                    f"recipe={repair.recipe_id} reason={repair.reason}"
                )
                after_text = config_path.read_text(encoding="utf-8")
                assert before_text == after_text, (
                    f"round {round_idx} {scenario} mutated the config despite rejection"
                )
                rejected += 1

    print(f"chaos sweep summary: rounds={rounds} healed={healed} rejected={rejected}")
    captured = capsys.readouterr()
    assert "chaos sweep summary" in captured.out
    assert healed + rejected == rounds


def _write_runtime_config(tmp_path: Path, base_url: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = yaml.safe_load(Path("demo/rocm-doctor.yaml").read_text(encoding="utf-8"))
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
    provider["templates"]["health_chat"] = str(Path("templates/health_chat.j2").resolve())
    provider["templates"]["tool_call"] = str(Path("templates/tool_call_prompt.j2").resolve())
    source["workspace"] = "."
    source["reports_dir"] = "reports"
    source["state_file"] = ".state.json"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    assert load_config(config_path)
    return config_path
