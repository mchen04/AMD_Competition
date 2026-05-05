# Demo Runbook

## Local Loop

For the complete no-AMD validation path, run:

```bash
scripts/local_validate.sh
```

The script runs the test suite, exercises the fake endpoint demo on a copied config, writes an incident report, and runs the real-Qwen local suite when Ollama is available.

Current no-AMD validation status: deterministic tests, copied-config fake endpoint demo, incident report generation, and real local Qwen all pass. AMD MI300X/vLLM validation still requires cloud credits.

Start the fake endpoint:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor fake-endpoint --port 8000
```

Use a copied config if you do not want to mutate the checked-in demo file:

```bash
cp demo/rocm-doctor.yaml /tmp/rocm-doctor-demo.yaml
```

Copied configs are supported. Relative references to bundled `templates/*.j2` still resolve back to the repo templates.

Run the loop:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor report --config /tmp/rocm-doctor-demo.yaml
```

The report records the model provider, adapter, skipped checks, diagnosis, repair, and before/after evidence.

`self-heal` snapshots the config before each candidate repair, verifies after applying it, and rolls back the candidate if verification still fails.

## Optional Tiny Models

`demo/ollama-tiny-models.yaml` contains OpenAI-compatible Ollama profiles for:

- `qwen3:0.6b`
- `smollm2:135m`
- `tinyllama:1.1b`

Switch `active_model_provider` to the provider you want to test, then run:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/ollama-tiny-models.yaml
```

Tool-call and ROCm device checks are disabled for these local Ollama profiles unless the runtime is configured to support them.

## Failure Scenarios

- `wrong_endpoint_port`: repairs the active model provider endpoint URL.
- `context_length_too_large`: lowers the active model provider context limit.
- `tool_parser_mismatch`: restores the active provider tool parser.
- `missing_rocm_device_flags`: restores required ROCm device flags.
- Endpoint/proxy modes such as `empty_chat_content_once`, `slow_response`, and `stream_interrupt`: exercise token-budget tuning, timeout tuning, and streaming disablement.
- `malformed_provider_output`, `unknown_recipe`, `unsafe_command`, `path_traversal`, `credential_modification`: fail closed with no unsafe edits.

## AMD Demo

Do this only after the local loop passes:

1. Create one MI300X droplet.
2. Verify ROCm with `rocminfo` and `amd-smi` or `rocm-smi`.
3. Start vLLM with an OpenAI-compatible endpoint.
4. Add or activate a YAML `model_providers` entry for that endpoint.
5. Run `check`, one controlled failure, `self-heal`, and `report`.
6. Destroy the droplet after the validation window.
