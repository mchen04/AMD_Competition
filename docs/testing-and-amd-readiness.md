# Testing and AMD Readiness

## Validation Gate

```bash
scripts/local_validate.sh
```

Creates/reuses `/tmp/rocm-doctor-venv`, installs `'.[test]'`, runs `compileall` + `pytest`, exercises the fake-endpoint demo on a copied config, generates a report, and runs the real-Qwen suite when Ollama is serving `qwen3:0.6b`.

Manual equivalent:

```bash
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
/tmp/rocm-doctor-venv/bin/python -m compileall rocm_doctor tests
/tmp/rocm-doctor-venv/bin/python -m pytest -q
```

Latest local status (no AMD credits): deterministic suite passes, real-Qwen suite passes, fake-endpoint demo + report path passes. AMD MI300X/vLLM path pending GPU credits.

## Coverage

The pytest suite uses real in-process HTTP, not mocks, against the OpenAI-compatible adapter for `qwen3:0.6b`, `smollm2:135m`, `tinyllama:1.1b`.

**Failure modes covered:** malformed JSON, empty response, empty chat content, partial response, HTTP 500, HTTP 429 (one-time + repeated), timeout, retry recovery, retry exhaustion, context-length failure, tool-call parser mismatch, wrong tool name, hallucinated tool call, instruction drift, streaming interruption, repetitive output, corrupted state, invalid config, bad template, unknown recipe, unsafe command, path traversal, credential edit.

**Self-heal flows asserted end-to-end:** retry-only recovery, `health_max_tokens` tuning, timeout tuning, streaming disablement, prompt-template fallback, fallback-provider switching, rollback after failed repair, learned-fix state recording.

**Report path:** generated reports include diagnosis, repair recipe, verification status, before/after evidence.

## Real-Qwen Adversarial Suite

```bash
ROCM_DOCTOR_RUN_REAL_QWEN=1 \
  /tmp/rocm-doctor-venv/bin/python -m pytest tests/test_real_qwen_adversarial.py -q -s
```

Adversarial proxy fronts local Ollama. Healthy requests forward to `qwen3:0.6b`; transport/protocol failures inject at the proxy boundary; prompt-level probes are answered by the real model. Healing loops covered: empty chat content, slow response, broken streaming, bad endpoint recovery.

The proxy can also be run manually:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor adversarial-proxy \
  --upstream-base-url http://127.0.0.1:11434/v1 \
  --failure-mode chat_invalid_json
```

## Tiny-Model Behavior

`demo/ollama-tiny-models.yaml` ships profiles for `qwen3:0.6b`, `smollm2:135m`, `tinyllama:1.1b`. Switch `active_model_provider` to test each.

| Model | Behavior |
|---|---|
| `qwen3:0.6b` | Passes direct health checks and the real-Qwen adversarial suite. |
| `smollm2:135m` | Reachable; fails strict health by returning long explanatory text instead of `ROCM_DOCTOR_OK`. |
| `tinyllama:1.1b` | Reachable; fails strict health by returning prose around the sentinel. |

The two smaller profiles are negative controls — evidence that the harness rejects weak instruction-following instead of accepting any response containing the sentinel.

### Tiny-Model Tuning

- Keep health prompts short and exact; keep `temperature: 0` in adapter probes.
- Disable native tool-call checks unless the runtime emits them reliably.
- Use smaller `model.context.max_tokens` and conservative `safe_max_tokens`.
- Tune `validation.health_max_tokens` (Qwen needs more headroom because Ollama reports reasoning separately).
- Set `validation.health_response_match: case_insensitive` for Qwen casing drift.
- Configure `templates.health_chat_fallbacks` so drift/loops/empty-output can switch prompts without Python edits.
- Increase `request.timeout_seconds` for CPU-bound Ollama runs.
- Use repeated-output and max-response validation to catch weak reasoning loops.

If a weak model fails with overlong output, treat it as a failed provider profile rather than relaxing validation.

## AMD Hooks

Everything AMD-specific is YAML-controlled:

- `hardware.{backend, accelerator, runtime}`, `hardware.amd.benchmark_profile`
- `launch.{device_flags, required_device_flags}`
- `model_providers.<id>.runtime_type`
- endpoint URL, context limits, request timeout, retry policy, streaming flag
- safe repair recipes and health probes

Remaining work is real MI300X/vLLM validation: add a `model_providers` entry pointing at the deployed vLLM endpoint, set ROCm device flags, tune context for the served model, run the same scenarios listed in [demo-runbook.md](demo-runbook.md). See [amd-developer-cloud-setup.md](amd-developer-cloud-setup.md) for droplet setup.
