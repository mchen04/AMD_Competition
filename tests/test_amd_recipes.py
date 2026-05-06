"""End-to-end tests for the AMD-specific failure classes.

Two new failure modes ship together:
  * ``rocm_oom_inference``     — HIP/ROCm OOM at inference time, healed by
                                  ``lower_gpu_memory_utilization``.
  * ``max_model_len_mismatch`` — vLLM-served context length is below the
                                  configured ``model.context.max_tokens``,
                                  healed by ``align_max_tokens_with_served``.

The fake endpoint exposes ``*_once`` failure modes that fail the first chat
probe and return healthy after, so ``self_heal_config`` can drive the full
diagnose → repair → verify cycle without real ROCm hardware.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rocm_doctor.config import load_config
from rocm_doctor.failure_injection import inject_failure
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.operations import self_heal_config
from rocm_doctor.recipes.builders import (
    _align_max_tokens_with_served,
    _lower_gpu_memory_utilization,
)
from rocm_doctor.state import load_state


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


def test_rocm_oom_inference_heals_with_lower_gpu_memory_utilization(tmp_path: Path) -> None:
    with FakeOpenAIServer(
        expected_tool_parser="qwen3", failure_mode="hip_oom_once"
    ) as server:
        config_path = _write_runtime_config(tmp_path, base_url=server.base_url)
        # Push utilization to the brink so the recipe has somewhere to go.
        cfg = load_config(config_path)
        cfg["launch"]["vllm_args"]["gpu_memory_utilization"] = 0.99
        config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

        result = self_heal_config(config_path, provider_name="rules")

        assert result.healthy, result.reason
        applied = [r.recipe_id for r in result.repairs]
        assert applied[-1] == "lower_gpu_memory_utilization", applied

        after = float(
            load_config(config_path)["launch"]["vllm_args"]["gpu_memory_utilization"]
        )
        assert 0.3 <= after < 0.99

        learned = (
            load_state(config_path)
            .get("learned_fixes", {})
            .get("fake-openai", {})
            .get("rocm_oom_inference", [])
        )
        assert any(
            entry.get("successful_fix") == "lower_gpu_memory_utilization"
            for entry in learned
        ), learned


def test_max_model_len_mismatch_heals_with_align_recipe(tmp_path: Path) -> None:
    with FakeOpenAIServer(
        expected_tool_parser="qwen3", failure_mode="max_model_len_exceeded_once"
    ) as server:
        config_path = _write_runtime_config(tmp_path, base_url=server.base_url)
        cfg = load_config(config_path)
        cfg["model_providers"]["fake-openai"]["model"]["context"]["max_tokens"] = 200
        cfg["model_providers"]["fake-openai"]["model"]["context"]["safe_max_tokens"] = 200
        config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

        result = self_heal_config(config_path, provider_name="rules")

        assert result.healthy, result.reason
        applied = [r.recipe_id for r in result.repairs]
        assert applied[-1] in {"align_max_tokens_with_served", "lower_max_model_len"}, applied

        final = int(
            load_config(config_path)["model_providers"]["fake-openai"]["model"][
                "context"
            ]["max_tokens"]
        )
        assert final < 200

        learned = (
            load_state(config_path)
            .get("learned_fixes", {})
            .get("fake-openai", {})
            .get("max_model_len_mismatch", [])
        )
        assert any(
            entry.get("successful_fix")
            in {"align_max_tokens_with_served", "lower_max_model_len"}
            for entry in learned
        ), learned


def test_lower_gpu_memory_utilization_builder_drops_value() -> None:
    cfg = {"launch": {"vllm_args": {"gpu_memory_utilization": 0.95}}}
    changes = _lower_gpu_memory_utilization(cfg)
    assert "launch.vllm_args.gpu_memory_utilization" in changes
    new_value = changes["launch.vllm_args.gpu_memory_utilization"]
    assert isinstance(new_value, float)
    assert 0.3 <= new_value < 0.95


def test_align_max_tokens_uses_safe_ceiling_when_below_current() -> None:
    cfg = {
        "active_model_provider": "p",
        "model_providers": {
            "p": {"model": {"context": {"max_tokens": 8192, "safe_max_tokens": 4096}}}
        },
    }
    changes = _align_max_tokens_with_served(cfg)
    assert changes["model_providers.p.model.context.max_tokens"] == 4096


def test_inject_failure_records_oom_scenario(tmp_path: Path) -> None:
    """The dashboard 'Inject' button mutates the YAML in a deterministic way."""
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, base_url=server.base_url)
        snapshot = inject_failure(config_path, "rocm_oom_inference")
        assert snapshot["after"]["gpu_memory_utilization"] == 0.99
        assert snapshot["after"]["fake_provider_mode"] == "hip_oom"

        snapshot = inject_failure(config_path, "max_model_len_mismatch")
        assert snapshot["after"]["max_model_len"] > snapshot["before"]["max_model_len"]
        assert snapshot["after"]["fake_provider_mode"] == "max_model_len_exceeded"
