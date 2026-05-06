from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rocm_doctor.config import load_config
from rocm_doctor.executor import execute_plan
from rocm_doctor.failure_injection import inject_failure
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.operations import verify_config
from rocm_doctor.recipes import RECIPE_REGISTRY, global_allowlisted_paths
from rocm_doctor.schemas import RepairPlan


def _write_runtime_config(
    tmp_path: Path,
    base_url: str,
    *,
    timeout_seconds: float = 1.0,
    stream: bool = False,
    health_max_tokens: int = 32,
    retry_attempts: int = 1,
) -> Path:
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
    provider["request"]["timeout_seconds"] = timeout_seconds
    provider["request"]["stream"] = stream
    provider["request"]["retry"]["max_attempts"] = retry_attempts
    provider["validation"]["health_max_tokens"] = health_max_tokens
    provider["templates"]["health_chat"] = str(Path("templates/health_chat.j2").resolve())
    provider["templates"]["tool_call"] = str(Path("templates/tool_call_prompt.j2").resolve())
    source["workspace"] = "."
    source["reports_dir"] = "reports"
    source["state_file"] = ".state.json"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    assert load_config(config_path)
    return config_path


def _plan(recipe_id: str, *, sequence: list[str] | None = None, changes: dict | None = None) -> RepairPlan:
    return RepairPlan(
        recipe_id=recipe_id,
        rationale="test plan",
        config_patch={"changes": changes or {}},
        risk_level="low",
        rollback="restore previous values",
        verification_steps=["rerun health check"],
        provider="test",
        recipe_id_sequence=list(sequence or []),
    )


def test_synthesize_patch_is_in_registry_and_global_allowlist_excludes_credentials() -> None:
    assert "synthesize_patch" in RECIPE_REGISTRY
    sample_config = yaml.safe_load(Path("demo/rocm-doctor.yaml").read_text(encoding="utf-8"))
    paths = global_allowlisted_paths(sample_config)
    assert paths, "expected a non-empty global allowlist"
    for path in paths:
        lowered = path.lower()
        assert "api_key" not in lowered
        assert "secret" not in lowered
        assert "credential" not in lowered


def test_recipe_sequence_applies_multiple_steps_and_accumulates_changed_paths(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(
            tmp_path,
            server.base_url,
            timeout_seconds=2.0,
            stream=True,
            health_max_tokens=64,
        )
        plan = _plan(
            "increase_timeout",
            sequence=["increase_timeout", "disable_streaming", "lower_health_max_tokens"],
        )

        result = execute_plan(config_path, plan)

        assert not result.rejected, result.reason
        assert result.applied
        assert result.applied_recipe_ids == [
            "increase_timeout",
            "disable_streaming",
            "lower_health_max_tokens",
        ]
        config = load_config(config_path)
        provider = config["model_providers"][config["active_model_provider"]]
        assert provider["request"]["stream"] is False
        assert provider["request"]["timeout_seconds"] > 2.0
        assert provider["validation"]["health_max_tokens"] < 64
        provider_prefix = f"model_providers.{config['active_model_provider']}"
        assert f"{provider_prefix}.request.stream" in result.changed_paths
        assert f"{provider_prefix}.request.timeout_seconds" in result.changed_paths
        assert f"{provider_prefix}.validation.health_max_tokens" in result.changed_paths


def test_recipe_sequence_rolls_back_when_a_step_is_unsafe(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, server.base_url, stream=True)
        before_config = load_config(config_path)
        before_stream = before_config["model_providers"]["fake-openai"]["request"]["stream"]

        plan = _plan(
            "disable_streaming",
            sequence=["disable_streaming", "definitely_not_a_real_recipe"],
        )

        result = execute_plan(config_path, plan)

        assert result.rejected, "sequence with unknown step should be rejected"
        assert "definitely_not_a_real_recipe" in result.reason
        # Sequence pre-check rejects before any step runs, so config must be unchanged.
        after_config = load_config(config_path)
        assert (
            after_config["model_providers"]["fake-openai"]["request"]["stream"] == before_stream
        )


def test_recipe_sequence_restores_snapshot_when_a_mid_sequence_step_fails(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, server.base_url, stream=True)
        before_config = load_config(config_path)
        before_provider = before_config["model_providers"]["fake-openai"]
        before_stream = before_provider["request"]["stream"]
        before_active = before_config["active_model_provider"]

        plan = _plan(
            "disable_streaming",
            sequence=["disable_streaming", "fallback_model_provider"],
        )

        result = execute_plan(config_path, plan)

        assert result.rejected, result.reason
        assert "fallback_model_provider" in result.reason
        # Snapshot rollback: streaming change from step 1 must be reverted.
        after_config = load_config(config_path)
        after_provider = after_config["model_providers"]["fake-openai"]
        assert after_provider["request"]["stream"] == before_stream
        assert after_config["active_model_provider"] == before_active
        assert result.rolled_back


def test_synthesize_patch_applies_brain_authored_value(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, server.base_url, health_max_tokens=64)
        plan = _plan(
            "synthesize_patch",
            changes={
                "model_providers.fake-openai.validation.health_max_tokens": 384,
                "model_providers.fake-openai.request.timeout_seconds": 12.5,
            },
        )

        result = execute_plan(config_path, plan)

        assert not result.rejected, result.reason
        assert result.applied
        config = load_config(config_path)
        provider = config["model_providers"]["fake-openai"]
        assert provider["validation"]["health_max_tokens"] == 384
        assert abs(provider["request"]["timeout_seconds"] - 12.5) < 1e-9


def test_synthesize_patch_rejects_path_outside_global_allowlist(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, server.base_url)
        plan = _plan(
            "synthesize_patch",
            changes={"model_providers.fake-openai.model.id": "smollm2:135m"},
        )

        result = execute_plan(config_path, plan)

        assert result.rejected
        assert "global allowlist" in result.reason


def test_synthesize_patch_rejects_type_mismatch(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, server.base_url)
        plan = _plan(
            "synthesize_patch",
            changes={"model_providers.fake-openai.request.stream": "no"},
        )

        result = execute_plan(config_path, plan)

        assert result.rejected
        assert "type mismatch" in result.reason


def test_synthesize_patch_rejects_credential_path(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, server.base_url)
        plan = _plan(
            "synthesize_patch",
            changes={"credentials.openai_api_key": "leaked"},
        )

        result = execute_plan(config_path, plan)

        assert result.rejected
        assert "credential or secret modification rejected" in result.reason


def test_synthesize_patch_heals_streaming_failure_end_to_end(tmp_path: Path) -> None:
    with FakeOpenAIServer(failure_mode="stream_interrupt") as server:
        config_path = _write_runtime_config(tmp_path, server.base_url, stream=True)

        plan = _plan(
            "synthesize_patch",
            changes={"model_providers.fake-openai.request.stream": False},
        )
        result = execute_plan(config_path, plan)

        assert not result.rejected, result.reason
        assert result.applied
        verification = verify_config(config_path)
        assert verification.healthy


def test_recipe_sequence_heals_injected_endpoint_failure(tmp_path: Path) -> None:
    with FakeOpenAIServer() as server:
        config_path = _write_runtime_config(tmp_path, server.base_url)
        inject_failure(config_path, "wrong_endpoint_port")

        plan = _plan(
            "update_endpoint_url",
            sequence=["update_endpoint_url", "retry_without_config_change"],
        )
        result = execute_plan(config_path, plan)

        assert not result.rejected, result.reason
        assert result.applied_recipe_ids == [
            "update_endpoint_url",
            "retry_without_config_change",
        ]
        verification = verify_config(config_path)
        assert verification.healthy


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
