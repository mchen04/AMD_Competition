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

## AMD Demo (captured via `scripts/amd_demo.sh`)

The bundled demo script runs the canonical pin → supervise → inject → heal → restore → report sequence and drops the artifacts into `evidence/` plus a tarball.

```bash
# No GPU required — runs against the bundled fake endpoint.
bash scripts/amd_demo.sh --local

# On a real MI300X droplet (rocminfo + amd-smi + vLLM on :8000):
bash scripts/amd_demo.sh --droplet
```

Both modes produce the same `evidence/0*.json|md|log` shape so the demo
narrative is identical regardless of where it ran. `--droplet` additionally
captures `evidence/rocminfo-pre.txt`, `evidence/amd-smi-pre.txt`,
`evidence/amd-smi-post.txt`. See [amd-developer-cloud-setup.md](amd-developer-cloud-setup.md).

Expected recipe mappings (covered by automated tests):

- `wrong_endpoint_port` → `update_endpoint_url`
- `context_length_too_large` → `lower_max_model_len`
- `missing_rocm_device_flags` → `set_rocm_device_flags`
- `rocm_oom_inference` → `lower_gpu_memory_utilization`
- `max_model_len_mismatch` → `align_max_tokens_with_served`
- `tool_parser_mismatch` → `set_tool_parser` (only if vLLM/model supports tool calls)

The screen recording stays manual: run `rocm_doctor dashboard --port 8765`
and drive the same scenarios via the UI. The script handles all shell-side
artifact capture so the video can focus on the dashboard.

## Continuous Supervisor

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor supervise \
  --config /tmp/rocm-doctor-amd.yaml \
  --interval 30 \
  --until-pass
```

The supervisor runs `check → diagnose → classify intent → heal → verify` on the configured interval, forever. `--until-pass` raises the per-cycle `max_attempts` to effectively unbounded so a stubborn drift gets every safe recipe before giving up. Cooldowns after a heal (`60s`) and after an intent skip (`300s`) keep the loop from thrashing — both tunable via the `supervision:` block in YAML. Stop with Ctrl-C.

For the dashboard equivalent, the Overview page exposes a Supervisor panel with the same interval / until-pass controls and a live SSE event log.

## Pin & Drift Demo

This is the canonical Track-1 storyline: pin a healthy state, watch the harness ignore an *intentional* operator change, then watch it heal an *unintentional* drift.

```bash
cp demo/rocm-doctor.yaml /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor fake-endpoint --port 8000 &

# Pin the current healthy state.
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check         --config /tmp/rocm-doctor-demo.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor pin-baseline  --config /tmp/rocm-doctor-demo.yaml

# Start the supervisor.
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor supervise \
  --config /tmp/rocm-doctor-demo.yaml --interval 5 --until-pass &

# 1) INTENTIONAL — edit a path the recipe set does NOT touch.
python3 -c "import yaml; \
  d=yaml.safe_load(open('/tmp/rocm-doctor-demo.yaml')); \
  d['hardware']['deployment_target']='cluster-mi300x-ord1'; \
  open('/tmp/rocm-doctor-demo.yaml','w').write(yaml.safe_dump(d, sort_keys=False))"
# Next cycle: intent → intentional → record_only. Heal is skipped.

# 2) UNINTENTIONAL — inject a known drift the recipe set fixes.
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port \
  --config /tmp/rocm-doctor-demo.yaml
# Next cycle: intent → unintentional → heal. update_endpoint_url runs, verify passes.

# Inspect the latest classification.
jq '.intent' < /tmp/.rocm-doctor-state.json
```

The supervisor records each intent under the `intent` key in `state.json` and surfaces it on the Incidents page in the dashboard.

## Evidence to Save

For an AMD submission run: droplet plan screenshot, `rocminfo | head`, `amd-smi`/`rocm-smi`, `/v1/models` response, healthy `check` output, failed check after injection, successful `self-heal`, final report path, short screen recording.
