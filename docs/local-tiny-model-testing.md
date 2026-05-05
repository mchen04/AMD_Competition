# Local Tiny Model Testing

Use `demo/ollama-tiny-models.yaml` for optional real Ollama checks. The same adapter and stress tests are already covered by the deterministic pytest suite, so real model downloads are optional.

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

## Tuning

Small models drift more often, so keep probes short, deterministic, and low-token. For local CPU-bound runs, increase `request.timeout_seconds`. Leave `tool_calling.enabled: false` unless the runtime emits native OpenAI tool calls reliably.
