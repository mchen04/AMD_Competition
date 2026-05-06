from __future__ import annotations

from pathlib import Path

import yaml

from rocm_doctor.config import load_config
from rocm_doctor.failure_injection import inject_failure
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.operations import self_heal_config
from rocm_doctor.state import load_state


def test_sequential_failures_heal_with_correct_recipes(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, base_url=server.base_url)

        inject_failure(config_path, "wrong_endpoint_port")
        first = self_heal_config(config_path, provider_name="rules")
        assert first.healthy, first.reason
        assert first.repairs[-1].recipe_id == "update_endpoint_url"

        inject_failure(config_path, "context_length_too_large")
        second = self_heal_config(config_path, provider_name="rules")
        assert second.healthy, second.reason
        assert second.repairs[-1].recipe_id == "lower_max_model_len", (
            f"second heal landed on {second.repairs[-1].recipe_id!r} instead of lower_max_model_len"
        )

        inject_failure(config_path, "wrong_endpoint_port")
        third = self_heal_config(config_path, provider_name="rules")
        assert third.healthy, third.reason
        assert third.repairs[-1].recipe_id == "update_endpoint_url"

        state = load_state(config_path)
        learned = state.get("learned_fixes", {}).get("fake-openai", {})
        assert "wrong_endpoint_port" in learned
        assert "context_length_too_large" in learned
        assert any(
            entry.get("successful_fix") == "update_endpoint_url"
            for entry in learned["wrong_endpoint_port"]
        )
        assert any(
            entry.get("successful_fix") == "lower_max_model_len"
            for entry in learned["context_length_too_large"]
        )


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
