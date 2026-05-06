from __future__ import annotations

from pathlib import Path

import yaml

from rocm_doctor.config import load_config
from rocm_doctor.executor import execute_plan
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.operations import verify_config
from rocm_doctor.schemas import RepairPlan


def test_streaming_slow_response_is_healed_by_recipe_sequence(tmp_path: Path) -> None:
    """A scenario that single-recipe heal can't cleanly fix: streaming is enabled but
    the upstream is also slow. Disabling streaming alone leaves the timeout too tight;
    raising the timeout alone leaves the broken streaming framing in place. A two-step
    recipe sequence (increase_timeout + disable_streaming) heals both at once."""
    with FakeOpenAIServer(failure_mode="slow_response", slow_response_seconds=0.4) as server:
        config_path = _write_runtime_config(
            tmp_path,
            base_url=server.base_url,
            timeout_seconds=0.1,
            stream=True,
        )

        plan = _plan(
            "increase_timeout",
            sequence=["increase_timeout", "disable_streaming"],
        )

        result = execute_plan(config_path, plan)

        assert not result.rejected, result.reason
        assert result.applied
        assert result.applied_recipe_ids == ["increase_timeout", "disable_streaming"]

        config = load_config(config_path)
        provider = config["model_providers"][config["active_model_provider"]]
        assert provider["request"]["timeout_seconds"] > 0.4
        assert provider["request"]["stream"] is False

        provider_prefix = f"model_providers.{config['active_model_provider']}"
        assert f"{provider_prefix}.request.timeout_seconds" in result.changed_paths
        assert f"{provider_prefix}.request.stream" in result.changed_paths

        verification = verify_config(config_path)
        assert verification.healthy, verification.message


def _plan(recipe_id: str, *, sequence: list[str]) -> RepairPlan:
    return RepairPlan(
        recipe_id=recipe_id,
        rationale="chaos sequence test",
        config_patch={"changes": {}},
        risk_level="low",
        rollback="restore previous values",
        verification_steps=["rerun health check"],
        provider="test",
        recipe_id_sequence=list(sequence),
    )


def _write_runtime_config(
    tmp_path: Path,
    base_url: str,
    *,
    timeout_seconds: float = 1.0,
    stream: bool = False,
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
