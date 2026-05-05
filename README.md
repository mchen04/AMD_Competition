# ROCm Doctor

ROCm Doctor is a self-healing harness for model-serving and agent runtimes. It checks an OpenAI-compatible endpoint, diagnoses failures, applies only deterministic repair recipes, verifies recovery, and writes incident evidence.

The codebase is model-agnostic and provider-agnostic: model runtime details live in YAML under `model_providers`, prompt text lives in Jinja templates, and Python code talks to providers through adapters.

## Quick Start

Install dependencies in a virtual environment:

```bash
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
```

Run the local deterministic endpoint in one terminal:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor fake-endpoint --port 8000
```

Run the harness in another terminal:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor report --config demo/rocm-doctor.yaml
```

Use a copy of the demo config when you want to mutate it repeatedly.

## Core Files

- `rocm_doctor/config.py`: YAML loading, normalization, validation, path helpers, redaction.
- `rocm_doctor/model_providers.py`: model-provider adapter boundary. The implemented adapter is `openai-compatible`.
- `rocm_doctor/transport.py`: shared JSON HTTP transport, retries, rate-limit and timeout handling.
- `rocm_doctor/templates.py`: strict Jinja template rendering.
- `rocm_doctor/providers.py`: diagnosis/planning providers: `rules`, `fake`, optional `openai-codex`.
- `rocm_doctor/recipes.py`: deterministic repair recipes and allowed config paths.
- `rocm_doctor/executor.py`: safety gate for recipe execution.
- `tests/`: integration and stress coverage for Qwen, two additional tiny-model profiles, malformed responses, retries, tool calls, config failures, and self-healing loops.

## Config Layout

- `demo/rocm-doctor.yaml`: local fake OpenAI-compatible provider with all deterministic checks enabled.
- `demo/ollama-tiny-models.yaml`: optional Ollama profiles for `qwen3:0.6b`, `smollm2:135m`, and `tinyllama:1.1b`.
- `demo/amd-vllm-template.yaml`: AMD Developer Cloud/vLLM template with MI300X hooks.
- `templates/*.j2`: health-check, tool-call, and OpenAI Responses diagnosis/planning templates.

To add a model provider, add one entry under `model_providers`, set `active_model_provider`, and choose capabilities, endpoint URLs, context limits, retry settings, templates, health probes, and safe recipes. The core monitor and executor should not change for another OpenAI-compatible runtime.

## Verification

```bash
/tmp/rocm-doctor-venv/bin/python -m compileall rocm_doctor tests
/tmp/rocm-doctor-venv/bin/python -m pytest -q
```

Optional real tiny-model checks require Ollama:

```bash
ollama pull qwen3:0.6b
ollama pull smollm2:135m
ollama pull tinyllama:1.1b
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/ollama-tiny-models.yaml
```

## AMD Readiness

AMD-specific assumptions are config, not code: `hardware`, `launch.required_device_flags`, provider endpoint URLs, context limits, safe recipes, and stress-test targets are all YAML-controlled. For MI300X/vLLM validation, add or activate a `model_providers` entry with the vLLM endpoint, ROCm device flags, benchmark profile, and context limit appropriate for that deployment.

See `docs/provider-architecture.md` and `docs/testing-and-amd-readiness.md` for maintainer details.
