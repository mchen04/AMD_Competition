from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rocm_doctor.config import ConfigError, get_active_profile, load_config
from rocm_doctor.providers import diagnose_with_provider
from rocm_doctor.schemas import HealthCheckResult, EvidenceBundle


def test_yaml_config_loads_model_provider_profile() -> None:
    config = load_config("demo/rocm-doctor.yaml")
    profile = get_active_profile(config)

    assert profile.id == "fake-openai"
    assert profile.adapter == "openai-compatible"
    assert profile.model_name == "fake-qwen3"
    assert profile.templates["health_chat"].endswith("health_chat.j2")
    assert "model" not in config


def test_tiny_model_config_contains_qwen_and_two_small_models() -> None:
    config = load_config("demo/ollama-tiny-models.yaml")
    providers = config["model_providers"]

    assert {"ollama-qwen3-0-6b", "ollama-smollm2-135m", "ollama-tinyllama-1-1b"} <= set(providers)
    assert config["stress_tests"]["target_model_providers"] == [
        "ollama-qwen3-0-6b",
        "ollama-smollm2-135m",
        "ollama-tinyllama-1-1b",
    ]


def test_invalid_config_rejects_missing_active_model_provider(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("model_providers: {}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="active_model_provider"):
        load_config(config_path)


def test_model_provider_ids_cannot_contain_dots(tmp_path: Path) -> None:
    config = yaml.safe_load(Path("demo/rocm-doctor.yaml").read_text(encoding="utf-8"))
    provider = config["model_providers"].pop("fake-openai")
    config["active_model_provider"] = "bad.provider"
    config["model_providers"]["bad.provider"] = provider
    config_path = tmp_path / "bad-provider.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfigError, match="may not contain dots"):
        load_config(config_path)


def test_openai_responses_provider_skips_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = load_config("demo/rocm-doctor.yaml")
    evidence = EvidenceBundle(
        collected_at="2026-05-05T00:00:00Z",
        config_path="demo/rocm-doctor.yaml",
        config_snapshot={},
        endpoint={"models": {}, "chat": {}, "tool_call": {}},
        runtime={},
        logs=[],
        health=HealthCheckResult(healthy=True, checks={"endpoint_models": True}),
    )

    diagnosis = diagnose_with_provider("openai-codex", evidence, config)

    assert diagnosis.failure_class == "provider_skipped"
    assert "OPENAI_API_KEY is absent" in diagnosis.evidence[0]


def test_bad_template_rendering_is_reported(tmp_path: Path) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "bad.j2").write_text("{{ missing.value }}", encoding="utf-8")
    config_path = _write_config(tmp_path, base_url="http://127.0.0.1:1/v1")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    provider = config["model_providers"]["fake-openai"]
    provider["templates"]["health_chat"] = "templates/bad.j2"
    provider["capabilities"]["models"] = False
    provider["health"]["probes"] = ["chat_completion"]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    from rocm_doctor.monitor import run_check

    health, evidence = run_check(config_path)

    assert not health.healthy
    assert "template render failed" in evidence.endpoint["chat"]["error"]


def _write_config(tmp_path: Path, base_url: str) -> Path:
    source = yaml.safe_load(Path("demo/rocm-doctor.yaml").read_text(encoding="utf-8"))
    source["workspace"] = "."
    source["reports_dir"] = "reports"
    source["state_file"] = ".state.json"
    source["model_providers"]["fake-openai"]["model"]["endpoint"]["base_url"] = base_url
    source["model_providers"]["fake-openai"]["model"]["endpoint"]["expected_base_url"] = base_url
    source["model_providers"]["fake-openai"]["model"]["endpoint"]["wrong_base_url"] = "http://127.0.0.1:9/v1"
    source["model_providers"]["fake-openai"]["templates"]["health_chat"] = str(
        Path("templates/health_chat.j2").resolve()
    )
    source["model_providers"]["fake-openai"]["templates"]["tool_call"] = str(
        Path("templates/tool_call_prompt.j2").resolve()
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    return config_path
