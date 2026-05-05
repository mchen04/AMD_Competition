# Local Tiny Model Testing

Use `demo/ollama-tiny-models.yaml` for optional real Ollama checks. The same adapter and stress tests are already covered by the deterministic pytest suite, so real model downloads are optional.

The main local success path is `qwen3:0.6b`. The two smaller profiles are included as constrained-model checks and are allowed to fail strict health validation if they drift or over-answer.

## Models

- `ollama-qwen3-0-6b`: `qwen3:0.6b`
- `ollama-smollm2-135m`: `smollm2:135m`
- `ollama-tinyllama-1-1b`: `tinyllama:1.1b`

## Commands

```bash
ollama pull qwen3:0.6b
ollama pull smollm2:135m
ollama pull tinyllama:1.1b
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/ollama-tiny-models.yaml
```

Switch `active_model_provider` in YAML before checking each model.

## Current Local Results

- `qwen3:0.6b`: passes direct health checks and the real-Qwen adversarial suite when Ollama is serving locally.
- `smollm2:135m`: reachable, but fails health validation by returning long explanatory text instead of only `ROCM_DOCTOR_OK`.
- `tinyllama:1.1b`: reachable, but fails health validation by returning extra prose around the sentinel.

These failures are useful evidence that ROCm Doctor rejects weak instruction following instead of accepting any model response that merely contains the sentinel somewhere.

## Tuning

Small models drift more often, so keep probes short, deterministic, and low-token. For local CPU-bound runs, increase `request.timeout_seconds`. Leave `tool_calling.enabled: false` unless the runtime emits native OpenAI tool calls reliably.

If a weak model fails with overlong output, prefer treating it as a failed provider profile. Tightening validation or switching to the minimal prompt may make the failure clearer, but it should not be relaxed just to make the check pass.
