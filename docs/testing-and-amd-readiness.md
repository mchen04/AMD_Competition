# Testing And AMD Readiness

## Test Coverage

Run:

```bash
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
/tmp/rocm-doctor-venv/bin/python -m compileall rocm_doctor tests
/tmp/rocm-doctor-venv/bin/python -m pytest -q
```

The pytest suite uses a real in-process HTTP endpoint rather than mocked-only provider calls. It exercises the same OpenAI-compatible adapter path for:

- `qwen3:0.6b`
- `smollm2:135m`
- `tinyllama:1.1b`

Covered failure classes include malformed JSON, empty responses, partial responses, HTTP 500, HTTP 429, timeout, retry recovery, retry exhaustion, context-length failure, tool-call parser mismatch, wrong tool-call name, hallucinated tool calls, streaming interruption, repetitive output loops, corrupted state, invalid config, bad template rendering, unknown recipes, unsafe commands, path traversal, and credential edits.

## Tiny-Model Tuning

For constrained models:

- Keep health prompts short and exact.
- Disable native tool-call checks unless the runtime reliably supports them.
- Use smaller `model.context.max_tokens` and conservative `safe_max_tokens`.
- Tune `validation.health_max_tokens`; local Qwen needed a larger budget because Ollama reported reasoning separately before final content.
- Increase `request.timeout_seconds` for local CPU-bound Ollama runs.
- Keep `temperature: 0` in adapter probes.
- Use repeated-output and max-response validation to catch weak reasoning loops.

## Optional Real Ollama Validation

The deterministic suite validates the provider path without requiring model downloads. To validate real local models, start Ollama and activate the provider in `demo/ollama-tiny-models.yaml`.

```bash
ollama pull qwen3:0.6b
ollama pull smollm2:135m
ollama pull tinyllama:1.1b
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/ollama-tiny-models.yaml
```

Switch `active_model_provider` to test each configured tiny model.

## AMD Hooks

AMD deployment assumptions are YAML-controlled:

- `hardware.backend`, `hardware.accelerator`, `hardware.runtime`, `hardware.amd.benchmark_profile`
- `launch.device_flags` and `launch.required_device_flags`
- `model_providers.<id>.runtime_type`
- endpoint URL, context limits, request timeout, retry policy, streaming flag
- safe repair recipes and health probes

Remaining AMD work is real MI300X/vLLM validation: add a `model_providers` entry for the deployed vLLM endpoint, set ROCm device flags, tune context for the selected model, and run the existing stress/failure suite against that provider.
