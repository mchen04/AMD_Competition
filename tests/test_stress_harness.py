from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rocm_doctor.config import load_config
from rocm_doctor.failure_injection import inject_failure
from rocm_doctor.fake_endpoint import FakeOpenAIServer
from rocm_doctor.monitor import run_check
from rocm_doctor.operations import diagnose_config, heal_config, self_heal_config, verify_config


TINY_MODELS = [
    ("qwen3:0.6b", "qwen3"),
    ("smollm2:135m", ""),
    ("tinyllama:1.1b", ""),
]


@pytest.mark.parametrize(("model_id", "tool_parser"), TINY_MODELS)
def test_check_heal_verify_loop_for_qwen_and_two_small_models(tmp_path: Path, model_id: str, tool_parser: str) -> None:
    with FakeOpenAIServer(model_id=model_id, expected_tool_parser=tool_parser or "qwen3") as server:
        config_path = _write_runtime_config(
            tmp_path,
            model_id=model_id,
            base_url=server.base_url,
            tool_parser=tool_parser or "qwen3",
            tool_calls=True,
        )

        health, evidence = run_check(config_path)
        assert health.healthy, evidence.endpoint

        inject_failure(config_path, "wrong_endpoint_port")
        diagnosis = diagnose_config(config_path, provider_name="rules")
        assert diagnosis.failure_class == "wrong_endpoint_port"

        repair = heal_config(config_path, provider_name="rules")
        assert repair.applied
        assert not repair.rejected

        verification = verify_config(config_path)
        assert verification.healthy


@pytest.mark.parametrize(
    "failure_mode, expected_errors",
    [
        ("chat_invalid_json", ("invalid JSON response",)),
        ("empty_response", ("invalid JSON response",)),
        ("partial_response", ("invalid JSON response", "Connection reset")),
        ("chat_500", ("HTTP 500",)),
        ("rate_limit", ("HTTP 429",)),
        ("slow_response", ("timed out",)),
        ("tool_wrong_name", ("unexpected tool call name",)),
        ("hallucinated_tool_call", ("hallucinated tool call",)),
        ("repetitive_output", ("repetitive output loop detected",)),
    ],
)
def test_adversarial_endpoint_failures_are_detected(
    tmp_path: Path, failure_mode: str, expected_errors: tuple[str, ...]
) -> None:
    with FakeOpenAIServer(
        failure_mode=failure_mode,
        expected_tool_parser="qwen3",
        slow_response_seconds=0.4,
    ) as server:
        config_path = _write_runtime_config(
            tmp_path,
            model_id="qwen3:0.6b",
            base_url=server.base_url,
            tool_parser="qwen3",
            tool_calls=True,
            timeout_seconds=0.1 if failure_mode == "slow_response" else 1.0,
            retry_attempts=2,
        )

        health, evidence = run_check(config_path)

        assert not health.healthy
        observed = health.summary + str(evidence.endpoint)
        assert any(expected in observed for expected in expected_errors)


def test_rate_limit_once_recovers_with_shared_retry_logic(tmp_path: Path) -> None:
    with FakeOpenAIServer(failure_mode="rate_limit_once") as server:
        config_path = _write_runtime_config(
            tmp_path,
            model_id="qwen3:0.6b",
            base_url=server.base_url,
            retry_attempts=2,
        )

        health, evidence = run_check(config_path)

        assert health.healthy
        assert evidence.endpoint["models"]["attempts"] == 2


def test_streaming_interrupt_is_reported_when_streaming_is_enabled(tmp_path: Path) -> None:
    with FakeOpenAIServer(failure_mode="stream_interrupt") as server:
        config_path = _write_runtime_config(
            tmp_path,
            model_id="qwen3:0.6b",
            base_url=server.base_url,
            stream=True,
            retry_attempts=1,
        )

        health, evidence = run_check(config_path)

        assert not health.healthy
        assert "invalid JSON response" in evidence.endpoint["chat"]["error"]


def test_context_tool_rocm_and_safety_failure_recovery(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(
            tmp_path,
            model_id="qwen3:0.6b",
            base_url=server.base_url,
            tool_parser="qwen3",
            tool_calls=True,
        )
        for scenario, changed_path in [
            ("context_length_too_large", "model.context.max_tokens"),
            ("tool_parser_mismatch", "model.tool_calling.parser"),
            ("missing_rocm_device_flags", "launch.device_flags"),
        ]:
            inject_failure(config_path, scenario)
            repair = heal_config(config_path, provider_name="rules")
            assert not repair.rejected, scenario
            assert any(path.endswith(changed_path) or path == changed_path for path in repair.changed_paths)
            assert verify_config(config_path).healthy


@pytest.mark.parametrize(
    "scenario, reason",
    [
        ("malformed_provider_output", "Provider returned output"),
        ("unknown_recipe", "unknown recipe id"),
        ("unsafe_command", "free-form command_preview"),
        ("path_traversal", "escapes the configured demo workspace"),
        ("credential_modification", "credential or secret modification rejected"),
    ],
)
def test_fake_diagnosis_provider_safety_modes_fail_closed(tmp_path: Path, scenario: str, reason: str) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, model_id="qwen3:0.6b", base_url=server.base_url)
        inject_failure(config_path, "tool_parser_mismatch")
        inject_failure(config_path, scenario)

        repair = heal_config(config_path, provider_name="fake")

        assert repair.rejected
        assert reason in repair.reason


def test_self_healing_recovers_and_reports_unrecoverable_failures(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, model_id="qwen3:0.6b", base_url=server.base_url)
        inject_failure(config_path, "wrong_endpoint_port")

        result = self_heal_config(config_path, provider_name="rules")

        assert result.healthy
        assert result.recovered
        assert result.attempts == 1

    with FakeOpenAIServer(failure_mode="chat_500") as broken:
        broken_config_path = _write_runtime_config(tmp_path / "broken", model_id="qwen3:0.6b", base_url=broken.base_url)

        result = self_heal_config(broken_config_path, provider_name="rules")

        assert not result.healthy
        assert result.unrecoverable
        assert "no deterministic changes required" in result.reason


def test_corrupted_state_does_not_break_self_healing(tmp_path: Path) -> None:
    with FakeOpenAIServer(expected_tool_parser="qwen3") as server:
        config_path = _write_runtime_config(tmp_path, model_id="qwen3:0.6b", base_url=server.base_url)
        (tmp_path / ".state.json").write_text("{not-json", encoding="utf-8")

        result = self_heal_config(config_path, provider_name="rules")

        assert result.healthy
        assert not result.unrecoverable


def _write_runtime_config(
    tmp_path: Path,
    model_id: str,
    base_url: str,
    tool_parser: str = "qwen3",
    tool_calls: bool = True,
    timeout_seconds: float = 1.0,
    retry_attempts: int = 1,
    stream: bool = False,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = yaml.safe_load(Path("demo/rocm-doctor.yaml").read_text(encoding="utf-8"))
    provider = source["model_providers"]["fake-openai"]
    provider["runtime_type"] = "harness-test"
    provider["model"]["id"] = model_id
    provider["model"]["endpoint"]["base_url"] = base_url
    provider["model"]["endpoint"]["expected_base_url"] = base_url
    provider["model"]["endpoint"]["wrong_base_url"] = "http://127.0.0.1:9/v1"
    provider["model"]["context"]["max_tokens"] = 128
    provider["model"]["context"]["safe_max_tokens"] = 256
    provider["model"]["tool_calling"]["enabled"] = tool_calls
    provider["model"]["tool_calling"]["parser"] = tool_parser
    provider["model"]["tool_calling"]["expected_parser"] = tool_parser
    provider["capabilities"]["tool_calls"] = tool_calls
    provider["request"]["timeout_seconds"] = timeout_seconds
    provider["request"]["stream"] = stream
    provider["request"]["retry"]["max_attempts"] = retry_attempts
    provider["templates"]["health_chat"] = str(Path("templates/health_chat.j2").resolve())
    provider["templates"]["tool_call"] = str(Path("templates/tool_call_prompt.j2").resolve())
    source["workspace"] = "."
    source["reports_dir"] = "reports"
    source["state_file"] = ".state.json"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    assert load_config(config_path)
    return config_path
