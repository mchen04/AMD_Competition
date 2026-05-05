# Testing And AMD Readiness

## Test Coverage

Run:

```bash
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
/tmp/rocm-doctor-venv/bin/python -m compileall rocm_doctor tests
/tmp/rocm-doctor-venv/bin/python -m pytest -q
```

The default pytest suite uses a real in-process HTTP endpoint rather than mocked-only provider calls. It exercises the same OpenAI-compatible adapter path for:

- `qwen3:0.6b`
- `smollm2:135m`
- `tinyllama:1.1b`

Covered failure classes include malformed JSON, empty responses, empty model content, partial responses, HTTP 500, HTTP 429, one-time rate limits, repeated rate limits, timeout, retry recovery, retry exhaustion, context-length failure, tool-call parser mismatch, wrong tool-call name, hallucinated tool calls, instruction drift, streaming interruption, repetitive output loops, corrupted state, invalid config, bad template rendering, unknown recipes, unsafe commands, path traversal, and credential edits.

The deterministic self-healing tests assert full detect-heal-verify behavior for retry-only recovery, `health_max_tokens` tuning, timeout tuning, streaming disablement, prompt-template fallback, fallback-provider switching, rollback after failed repairs, and learned-fix state recording.

The optional real-Qwen suite puts an adversarial proxy in front of local Ollama. Healthy requests are forwarded to `qwen3:0.6b`; transport/protocol failures are injected at the proxy boundary; prompt-level adversarial probes are answered by Qwen itself.

When enabled, the real-Qwen suite also runs healing loops for empty chat content, slow responses, broken streaming, and bad endpoint recovery, then verifies the final health check against the actual local Qwen model.

```bash
ROCM_DOCTOR_RUN_REAL_QWEN=1 /tmp/rocm-doctor-venv/bin/python -m pytest tests/test_real_qwen_adversarial.py -q -s
```

The proxy can also be run manually:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor adversarial-proxy \
  --upstream-base-url http://127.0.0.1:11434/v1 \
  --failure-mode chat_invalid_json
```

## Tiny-Model Tuning

For constrained models:

- Keep health prompts short and exact.
- Disable native tool-call checks unless the runtime reliably supports them.
- Use smaller `model.context.max_tokens` and conservative `safe_max_tokens`.
- Tune `validation.health_max_tokens`; local Qwen needed a larger budget because Ollama reported reasoning separately before final content.
- Keep `validation.expected_health_response` configured and use `health_response_match: case_insensitive` for Qwen-style casing drift.
- Configure `templates.health_chat_fallbacks` so drift, loops, empty output, or bad templates can switch to a stricter prompt without Python edits.
- Increase `request.timeout_seconds` for local CPU-bound Ollama runs.
- Set `request.stream: false` automatically when streaming is the failing path and non-streaming health checks still work.
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
