from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from rocm_doctor.adversarial_proxy import AdversarialProxyServer
from rocm_doctor.config import load_config
from rocm_doctor.failure_injection import inject_failure
from rocm_doctor.monitor import run_check
from rocm_doctor.operations import self_heal_config
from rocm_doctor.transport import RetryPolicy, request_json


pytestmark = pytest.mark.skipif(
    os.environ.get("ROCM_DOCTOR_RUN_REAL_QWEN") != "1",
    reason="set ROCM_DOCTOR_RUN_REAL_QWEN=1 to run local Ollama/Qwen adversarial integration tests",
)

OLLAMA_BASE_URL = os.environ.get("ROCM_DOCTOR_QWEN_BASE_URL", "http://127.0.0.1:11434/v1")
QWEN_MODEL_ID = os.environ.get("ROCM_DOCTOR_QWEN_MODEL", "qwen3:0.6b")


def test_real_qwen_baseline_and_streaming_success(tmp_path: Path) -> None:
    _require_real_qwen()
    with AdversarialProxyServer(upstream_base_url=OLLAMA_BASE_URL, model_id=QWEN_MODEL_ID) as proxy:
        config_path = _write_qwen_config(tmp_path, proxy.base_url)
        health, evidence = run_check(config_path)
        assert health.healthy, health.summary
        assert evidence.endpoint["chat"]["response"]["model"] == QWEN_MODEL_ID

        stream_config_path = _write_qwen_config(tmp_path / "stream", proxy.base_url, stream=True)
        stream_health, stream_evidence = run_check(stream_config_path)
        assert stream_health.healthy, stream_health.summary
        assert stream_evidence.endpoint["chat"]["response"]["choices"][0]["message"]["content"].strip()

        assert proxy.upstream_request_count >= 4


@pytest.mark.parametrize(
    ("failure_mode", "expected_error", "stream"),
    [
        ("models_500", "HTTP 500", False),
        ("chat_500", "HTTP 500", False),
        ("chat_invalid_json", "invalid JSON response", False),
        ("empty_response", "invalid JSON response", False),
        ("partial_response", "invalid JSON response", False),
        ("rate_limit", "HTTP 429", False),
        ("slow_response", "timed out", False),
        ("drop_connection", "Remote end closed connection", False),
        ("stream_interrupt", "invalid streaming JSON chunk", True),
        ("hallucinated_tool_call", "hallucinated tool call", False),
        ("repetitive_output", "repetitive output loop detected", False),
    ],
)
def test_real_qwen_proxy_adversarial_failures_are_detected(
    tmp_path: Path, failure_mode: str, expected_error: str, stream: bool
) -> None:
    _require_real_qwen()
    with AdversarialProxyServer(
        upstream_base_url=OLLAMA_BASE_URL,
        model_id=QWEN_MODEL_ID,
        failure_mode=failure_mode,
        slow_response_seconds=0.4,
        forward_before_failure=failure_mode in {"hallucinated_tool_call", "repetitive_output"},
    ) as proxy:
        config_path = _write_qwen_config(
            tmp_path,
            proxy.base_url,
            timeout_seconds=0.1 if failure_mode == "slow_response" else 30.0,
            retry_attempts=2,
            stream=stream,
        )

        health, evidence = run_check(config_path)

        assert not health.healthy
        observed = health.summary + str(evidence.endpoint)
        assert expected_error in observed


def test_real_qwen_rate_limit_once_recovers_through_retry(tmp_path: Path) -> None:
    _require_real_qwen()
    with AdversarialProxyServer(
        upstream_base_url=OLLAMA_BASE_URL,
        model_id=QWEN_MODEL_ID,
        failure_mode="rate_limit_once",
    ) as proxy:
        config_path = _write_qwen_config(tmp_path, proxy.base_url, retry_attempts=2)

        health, evidence = run_check(config_path)

        assert health.healthy, health.summary
        assert evidence.endpoint["models"]["attempts"] == 2
        assert evidence.endpoint["chat"]["attempts"] == 2


def test_real_qwen_self_heal_repairs_bad_endpoint_and_rechecks_model(tmp_path: Path) -> None:
    _require_real_qwen()
    with AdversarialProxyServer(upstream_base_url=OLLAMA_BASE_URL, model_id=QWEN_MODEL_ID) as proxy:
        config_path = _write_qwen_config(tmp_path, proxy.base_url)
        inject_failure(config_path, "wrong_endpoint_port")

        result = self_heal_config(config_path, provider_name="rules")

        assert result.healthy
        assert result.recovered
        assert result.attempts == 1
        assert result.repairs[0].changed_paths == [
            "model_providers.ollama-qwen3-0-6b.model.endpoint.base_url"
        ]
        assert proxy.upstream_request_count >= 2


@pytest.mark.parametrize(
    ("failure_mode", "config_kwargs", "expected_recipe", "expected_config_path", "expected_value"),
    [
        (
            "empty_chat_content_once",
            {"health_max_tokens": 256},
            "increase_health_max_tokens",
            "validation.health_max_tokens",
            512,
        ),
        (
            "slow_response",
            {"timeout_seconds": 0.1},
            "increase_timeout",
            "request.timeout_seconds",
            10.1,
        ),
        (
            "stream_interrupt",
            {"stream": True},
            "disable_streaming",
            "request.stream",
            False,
        ),
    ],
)
def test_real_qwen_proxy_failures_auto_heal_and_verify_on_model(
    tmp_path: Path,
    failure_mode: str,
    config_kwargs: dict[str, object],
    expected_recipe: str,
    expected_config_path: str,
    expected_value: object,
) -> None:
    _require_real_qwen()
    with AdversarialProxyServer(
        upstream_base_url=OLLAMA_BASE_URL,
        model_id=QWEN_MODEL_ID,
        failure_mode=failure_mode,
        slow_response_seconds=0.4,
    ) as proxy:
        config_path = _write_qwen_config(tmp_path, proxy.base_url, **config_kwargs)

        result = self_heal_config(config_path, provider_name="rules")
        config = load_config(config_path)
        provider = config["model_providers"][config["active_model_provider"]]

        assert result.healthy
        assert result.recovered
        assert result.repairs[0].recipe_id == expected_recipe
        assert _get_dotted(provider, expected_config_path) == expected_value
        assert proxy.upstream_request_count >= 2


@pytest.mark.parametrize(
    ("template_text", "expected_error"),
    [
        (
            "/no_think\nReturn ROCM_DOCTOR_OK followed by the exact sentence EXTRA_TEXT_FOR_DRIFT.",
            "expected health response",
        ),
        (
            "/no_think\nOutput exactly this text and nothing else: "
            "loop loop loop loop loop loop loop loop loop loop loop loop",
            "repetitive output loop detected",
        ),
    ],
)
def test_real_qwen_prompt_level_adversarial_outputs_are_rejected(
    tmp_path: Path, template_text: str, expected_error: str
) -> None:
    _require_real_qwen()
    template_path = tmp_path / "adversarial_health.j2"
    template_path.write_text(template_text, encoding="utf-8")
    with AdversarialProxyServer(upstream_base_url=OLLAMA_BASE_URL, model_id=QWEN_MODEL_ID) as proxy:
        config_path = _write_qwen_config(
            tmp_path,
            proxy.base_url,
            health_template=template_path,
            max_response_chars=4096,
            health_max_tokens=512,
        )

        health, evidence = run_check(config_path)

        assert not health.healthy
        assert expected_error in health.summary + str(evidence.endpoint)
        assert proxy.upstream_request_count >= 2


def _require_real_qwen() -> None:
    result = request_json(
        "GET",
        f"{OLLAMA_BASE_URL.rstrip('/')}/models",
        timeout=2.0,
        retry=RetryPolicy(max_attempts=1),
    )
    if not result.ok:
        pytest.skip(f"local Qwen endpoint unavailable: {result.error}")
    model_ids = {str(item.get("id")) for item in result.payload.get("data", [])}
    if QWEN_MODEL_ID not in model_ids:
        pytest.skip(f"{QWEN_MODEL_ID} not installed in local Ollama")


def _write_qwen_config(
    tmp_path: Path,
    base_url: str,
    timeout_seconds: float = 30.0,
    retry_attempts: int = 1,
    stream: bool = False,
    health_template: Path | None = None,
    max_response_chars: int = 160,
    health_max_tokens: int = 256,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = yaml.safe_load(Path("demo/ollama-tiny-models.yaml").read_text(encoding="utf-8"))
    provider = source["model_providers"]["ollama-qwen3-0-6b"]
    provider["model"]["id"] = QWEN_MODEL_ID
    provider["model"]["endpoint"]["base_url"] = base_url
    provider["model"]["endpoint"]["expected_base_url"] = base_url
    provider["model"]["endpoint"]["wrong_base_url"] = "http://127.0.0.1:9/v1"
    provider["request"]["timeout_seconds"] = timeout_seconds
    provider["request"]["retry"]["max_attempts"] = retry_attempts
    provider["request"]["stream"] = stream
    provider["templates"]["health_chat"] = str((health_template or Path("templates/health_chat.j2")).resolve())
    provider["templates"]["tool_call"] = str(Path("templates/tool_call_prompt.j2").resolve())
    provider["validation"]["max_health_response_chars"] = max_response_chars
    provider["validation"]["health_max_tokens"] = health_max_tokens
    provider["validation"]["expected_health_response"] = "ROCM_DOCTOR_OK"
    provider["validation"]["health_response_match"] = "case_insensitive"
    source["workspace"] = "."
    source["reports_dir"] = str(tmp_path / "reports")
    source["state_file"] = str(tmp_path / ".state.json")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    return config_path


def _get_dotted(data: dict[str, object], dotted_path: str) -> object:
    cursor: object = data
    for part in dotted_path.split("."):
        assert isinstance(cursor, dict)
        cursor = cursor[part]
    return cursor
