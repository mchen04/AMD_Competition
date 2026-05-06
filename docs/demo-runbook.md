# Demo Runbook

## No-AMD Local Loop

```bash
scripts/local_validate.sh
```

Runs pytest, exercises the fake-endpoint demo on a copied config, writes a report, and runs the real-Qwen suite when Ollama is serving `qwen3:0.6b`.

## Manual Demo

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor fake-endpoint --port 8000   # terminal 1

cp demo/rocm-doctor.yaml /tmp/rocm-doctor-demo.yaml                          # terminal 2
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check          --config /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal      --provider rules --config /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor report         --config /tmp/rocm-doctor-demo.yaml
```

Copied configs resolve bundled `templates/*.j2` back to the repo. `self-heal` snapshots config, applies one candidate, verifies, and rolls back the candidate if verification fails.

## Dashboard

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor dashboard --port 8765
```

Open `http://localhost:8765/`. Topbar pills switch active model provider and diagnosis brain. Failure chips trigger one full `check → diagnose → heal → verify → report` cycle streamed over SSE.

The dashboard binds against `<workspace>/.rocm-doctor.dashboard.yaml` (auto-created from the template). `POST /api/reset` restores it.

## Failure Scenarios

| `inject-failure` | Diagnosis | Recipe |
|---|---|---|
| `wrong_endpoint_port` | `wrong_endpoint_port` | `update_endpoint_url` |
| `context_length_too_large` | `context_length_too_large` | `lower_max_model_len` |
| `tool_parser_mismatch` | `tool_parser_mismatch` | `set_tool_parser` |
| `missing_rocm_device_flags` | `missing_rocm_device_flags` | `set_rocm_device_flags` |
| Endpoint/proxy: `empty_chat_content_once`, `slow_response`, `stream_interrupt` | timeout / empty / broken_streaming | token-budget, timeout, or streaming recipes |
| Safety: `malformed_provider_output`, `unknown_recipe`, `unsafe_command`, `path_traversal`, `credential_modification` | — | rejected, no edits applied |

## Optional Tiny-Model Loop

`demo/ollama-tiny-models.yaml` ships profiles for `qwen3:0.6b`, `smollm2:135m`, `tinyllama:1.1b`. Switch `active_model_provider` then:

```bash
ollama pull qwen3:0.6b
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/ollama-tiny-models.yaml
```

`qwen3:0.6b` passes; the smaller two are reachable but fail strict sentinel validation by over-answering — that's intentional weak-model rejection evidence.

## Real-Qwen Adversarial Suite

```bash
ROCM_DOCTOR_RUN_REAL_QWEN=1 \
  /tmp/rocm-doctor-venv/bin/python -m pytest tests/test_real_qwen_adversarial.py -q -s
```

Adversarial proxy in front of local Ollama. Healthy traffic forwards to `qwen3:0.6b`; transport/protocol failures inject at the proxy boundary; prompt-level probes are answered by Qwen.

## AMD Demo (after MI300X is up)

Prereqs: GPU droplet created, `rocminfo`/`amd-smi` working, vLLM serving on `:8000`. See [amd-developer-cloud-setup.md](amd-developer-cloud-setup.md).

```bash
cp demo/amd-vllm-template.yaml /tmp/rocm-doctor-amd.yaml
# Edit model.id + endpoint.base_url to match /v1/models output

/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config /tmp/rocm-doctor-amd.yaml
```

Run the same scenarios from the table above against the real endpoint. Expected mappings (validated locally):

- `wrong_endpoint_port` → `update_endpoint_url`
- `context_length_too_large` → `lower_max_model_len`
- `missing_rocm_device_flags` → `set_rocm_device_flags`
- `tool_parser_mismatch` → `set_tool_parser` (only if vLLM/model supports tool calls)

## Continuous Supervisor

```bash
while true; do
  if /tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config /tmp/rocm-doctor-amd.yaml >/tmp/last-check.json; then
    date -u +"%Y-%m-%dT%H:%M:%SZ healthy"
  else
    /tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config /tmp/rocm-doctor-amd.yaml
    /tmp/rocm-doctor-venv/bin/python -m rocm_doctor report --config /tmp/rocm-doctor-amd.yaml
  fi
  sleep 30
done
```

`self-heal` is one bounded recovery cycle by design. A production daemon should call the same bounded cycle repeatedly with a cooldown.

## Evidence to Save

For an AMD submission run: droplet plan screenshot, `rocminfo | head`, `amd-smi`/`rocm-smi`, `/v1/models` response, healthy `check` output, failed check after injection, successful `self-heal`, final report path, short screen recording.
