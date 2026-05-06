# AMD Cloud Validation Plan

This plan is for the first real AMD Developer Cloud run after credits are active.

The goal is not to train or improve a model. The goal is to prove that ROCm Doctor can supervise a real AMD ROCm/vLLM model endpoint, detect failures, apply deterministic fixes, verify recovery, and write evidence.

## Current Architecture

ROCm Doctor is already built as a provider-agnostic reliability loop:

```text
check -> diagnose -> repair -> verify -> report
```

The core code does not know about one specific cloud provider or model. Runtime details live in YAML:

- `demo/amd-vllm-template.yaml`: AMD/vLLM provider template.
- `rocm_doctor/model_providers.py`: OpenAI-compatible `/v1/models` and `/v1/chat/completions` adapter.
- `rocm_doctor/monitor.py`: health probes and evidence collection.
- `rocm_doctor/providers.py`: rules-based diagnosis.
- `rocm_doctor/recipes.py`: deterministic repair recipes.
- `rocm_doctor/operations.py`: `check`, `self-heal`, `verify`, and report flow.

Local validation is already proven by `scripts/local_validate.sh`. The missing proof is the same loop against a real MI300X ROCm/vLLM endpoint.

## Cloud Decision

Use the cheapest useful AMD GPU path:

- GPU: **1x MI300X**
- Avoid: **8x MI300X** unless a later benchmark specifically needs multi-GPU throughput.
- First model: `openai/gpt-oss-120b`
- Fallback model: `openai/gpt-oss-20b`
- First image choice: **ROCm enabled GPT-OSS 120b - ROCm 7**
- Fallback image choice: **vLLM ROCm quick-start image**

Reasoning:

- 1x MI300X has enough VRAM for the proof and preserves the $100 credit window.
- The repo only needs a real OpenAI-compatible endpoint, not maximum tokens/sec.
- `gpt-oss-120b` makes the demo materially more credible than a tiny model.
- `gpt-oss-20b` is the fallback if model download, boot, or vLLM compatibility costs too much time.

## What We Are Validating

We are validating three things:

1. **Use the model:** vLLM serves `gpt-oss` through an OpenAI-compatible endpoint on AMD ROCm.
2. **Break the deployment:** ROCm Doctor sees controlled failures in endpoint config, context limits, ROCm launch flags, tool parser config, or request behavior.
3. **Auto-fix and verify:** ROCm Doctor applies only safe deterministic config repairs, reruns health checks, and writes a report with before/after evidence.

We are not changing model weights. "Breaking the model" means breaking the serving/runtime configuration around the model in ways that happen in real deployments.

## Continuous Self-Healing Model

The production shape should be continuous supervision:

```text
loop forever:
  check endpoint and runtime assumptions
  if healthy:
    record last-known-good state
    sleep
  if unhealthy:
    diagnose
    apply one safe deterministic repair
    verify
    report incident
    roll back failed repair
    sleep with cooldown
```

The current CLI command, `self-heal`, is one bounded recovery cycle. That is intentional: it is easy to test, safe to demo, and avoids runaway repair loops. A production daemon or scheduler should call the same bounded cycle repeatedly.

For the AMD validation, prove both shapes:

- **Single incident proof:** inject one failure, run `self-heal`, show recovery and report.
- **Continuous supervisor proof:** run a shell loop that calls `check`; when `check` fails, call `self-heal` and `report`.

Continuous does not mean ROCm Doctor should constantly edit config. It should constantly observe, then repair only when evidence says the deployment is unhealthy.

## Success Criteria

The run is successful when we have:

- ROCm evidence from the droplet: `rocminfo`, `amd-smi` or `rocm-smi`.
- vLLM evidence: `/v1/models` returns the served model.
- ROCm Doctor healthy check passes against the real endpoint.
- At least one controlled failure is injected.
- `self-heal` recovers from that failure.
- `report` writes a readable incident report with before/after evidence.
- Screenshots or terminal output show this happened on AMD Developer Cloud.
- The droplet is destroyed after evidence is saved.

## Preflight Before Creating The Droplet

Run locally:

```bash
scripts/local_validate.sh
```

Expected status:

```text
40 passed, 19 skipped
19 passed
Local validation complete.
```

Add the local SSH key to DigitalOcean if it is not already there:

```bash
cat ~/.ssh/id_ed25519.pub
```

## Droplet Lifecycle

Create the droplet only when ready to validate.

Recommended settings:

- Product: GPU Droplet
- Plan: MI300X, 1 GPU
- Name: `rocm-doctor-demo`
- Backups: off
- Extra storage: none for first pass
- SSH auth: key auth

Destroy the droplet when evidence is saved. Powering it off is not the cost-control step we want; the clean validation pattern is create, validate, save artifacts, destroy.

## First SSH Checks

On the droplet:

```bash
rocminfo | head
amd-smi || rocm-smi
python3 --version
docker --version || true
```

If the GPU is not visible, stop and save the failed command output. Do not install or run ROCm Doctor yet.

## Start Or Find vLLM

First check whether the quick-start image already started an endpoint:

```bash
ss -ltnp | grep ':8000' || true
curl -sS http://127.0.0.1:8000/v1/models | head
```

If an endpoint exists, record the model id from `/v1/models` and use it in the ROCm Doctor config.

If no endpoint exists, start vLLM manually. Prefer image-provided launch instructions when available. A baseline manual command is:

```bash
MODEL_ID=openai/gpt-oss-120b
python3 -m vllm.entrypoints.openai.api_server \
  --model "${MODEL_ID}" \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 4096
```

If `gpt-oss-120b` fails to load or costs too much time, switch to:

```bash
MODEL_ID=openai/gpt-oss-20b
```

Then verify:

```bash
curl -sS http://127.0.0.1:8000/v1/models
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "'"${MODEL_ID}"'",
    "messages": [{"role": "user", "content": "Return exactly ROCM_DOCTOR_OK"}],
    "temperature": 0,
    "max_tokens": 32
  }'
```

## Install ROCm Doctor On The Droplet

Use the repo directly on the droplet:

```bash
git clone https://github.com/mchen04/AMD_Competition.git
cd AMD_Competition
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
```

If the repo is not accessible from the droplet, copy the local checkout over SSH instead.

## Configure The AMD Provider

Copy the template before mutating it:

```bash
cp demo/amd-vllm-template.yaml /tmp/rocm-doctor-amd.yaml
```

Edit `/tmp/rocm-doctor-amd.yaml`:

- `model.id`: actual model id from `/v1/models`.
- `model.endpoint.base_url`: `http://127.0.0.1:8000/v1`
- `model.endpoint.expected_base_url`: `http://127.0.0.1:8000/v1`
- `model.endpoint.wrong_base_url`: `http://127.0.0.1:8001/v1`
- `model.context.max_tokens`: start at `4096`
- `model.context.safe_max_tokens`: start at `8192`
- `request.timeout_seconds`: start at `30.0` if model responses are slow.
- `model.tool_calling.enabled`: set `false` if the selected image/model does not support vLLM tool calling cleanly.

## Healthy Baseline

Run:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config /tmp/rocm-doctor-amd.yaml
```

Save the output. This is the proof that ROCm Doctor can use the real AMD-hosted model.

## Continuous Supervisor Demo

After the healthy baseline works, start a simple supervisor loop in one terminal:

```bash
while true; do
  if /tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config /tmp/rocm-doctor-amd.yaml >/tmp/rocm-doctor-last-check.json; then
    date -u +"%Y-%m-%dT%H:%M:%SZ healthy"
  else
    date -u +"%Y-%m-%dT%H:%M:%SZ unhealthy; running self-heal"
    /tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config /tmp/rocm-doctor-amd.yaml
    /tmp/rocm-doctor-venv/bin/python -m rocm_doctor report --config /tmp/rocm-doctor-amd.yaml
  fi
  sleep 30
done
```

Then inject a failure from a second terminal:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config /tmp/rocm-doctor-amd.yaml
```

Expected behavior:

- The next loop iteration notices the unhealthy endpoint.
- `self-heal` repairs the config.
- `report` writes the incident evidence.
- Later loop iterations return to `healthy`.

## Controlled Break/Fix Scenarios

Run at least one scenario end-to-end. Run more if time allows.

### Scenario 1: Wrong Endpoint Port

This is the safest first demo because it proves auto-fix without touching the model process.

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor verify --config /tmp/rocm-doctor-amd.yaml
```

Expected behavior:

- `check` fails because `/v1/models` is pointed at the wrong port.
- Diagnosis class is `wrong_endpoint_port`.
- Repair recipe is `update_endpoint_url`.
- Verification passes after the endpoint URL is restored.

### Scenario 2: Context Length Too Large

This validates model/runtime config sanity.

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure context_length_too_large --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config /tmp/rocm-doctor-amd.yaml
```

Expected behavior:

- Diagnosis class is `context_length_too_large`.
- Repair recipe is `lower_max_model_len`.
- Verification passes after max context is lowered to the configured safe limit.

### Scenario 3: Missing ROCm Device Flags

This validates the AMD-specific config hook.

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure missing_rocm_device_flags --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config /tmp/rocm-doctor-amd.yaml
```

Expected behavior:

- Diagnosis class is `missing_rocm_device_flags`.
- Repair recipe is `set_rocm_device_flags`.
- Verification passes after `/dev/kfd` and `/dev/dri` are restored in config.

### Scenario 4: Tool Parser Mismatch

Run this only if the vLLM/model path supports tool calls.

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure tool_parser_mismatch --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config /tmp/rocm-doctor-amd.yaml
```

Expected behavior:

- Diagnosis class is `tool_parser_mismatch`.
- Repair recipe is `set_tool_parser`, or the run documents that tool-call probing should be disabled for this provider.

## Generate Final Report

After a successful self-heal:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor report --config /tmp/rocm-doctor-amd.yaml
```

Copy the report path from the JSON output. Save it with the submission artifacts.

## Evidence To Save

Save:

- Droplet plan screenshot showing MI300X.
- Credit screenshot if useful.
- `rocminfo | head` output.
- `amd-smi` or `rocm-smi` output.
- `/v1/models` output.
- Healthy `rocm_doctor check` output.
- Failed check after injected failure.
- Successful `self-heal` output.
- Final report file.
- Short screen recording of the check/fail/heal/report sequence.

## Demo UI And Recording Plan

The current product surface is CLI-first. That is good for reliability, but the final demo should have a simple UI layer so the self-healing loop is visually obvious.

Build a minimal local dashboard only after the AMD endpoint path is known. It should not replace the CLI or add a separate healing engine. It should call the same Python operations already used by the CLI.

Recommended UI:

- Status header: current provider, model id, endpoint URL, healthy/unhealthy state.
- Timeline: `check`, `failure injected`, `diagnosis`, `repair`, `verification`, `report`.
- Controls:
  - Run check
  - Start/stop supervisor loop
  - Inject wrong endpoint failure
  - Run self-heal now
  - Generate report
- Evidence panel: diagnosis class, repair recipe, changed config paths, verification message.
- AMD proof panel: MI300X, ROCm, vLLM, served model, `/v1/models` evidence.

Keep the UI intentionally thin:

```text
browser UI -> local demo server -> rocm_doctor.operations -> YAML config/state/report
```

Do not put repair logic in JavaScript. The browser should only trigger and display the existing ROCm Doctor loop.

For recording, use a two-window layout:

1. Browser dashboard on the left.
2. Terminal on the right showing the actual commands/logs.

Demo recording sequence:

1. Show AMD Developer Cloud MI300X droplet and ROCm/vLLM evidence.
2. Open ROCm Doctor dashboard.
3. Click or run baseline check: status turns healthy.
4. Start continuous supervisor.
5. Inject wrong endpoint failure.
6. Show next supervisor tick detecting unhealthy state.
7. Show diagnosis `wrong_endpoint_port`.
8. Show repair `update_endpoint_url`.
9. Show verification healthy.
10. Open final incident report.
11. End on the report and state that the droplet is destroyed after the run.

If time is tight, skip the custom UI and record terminal-only. The terminal-only demo is still valid because the CLI already proves the architecture. The UI is for clarity, not correctness.

## Submission Narrative

The demo story should be:

```text
ROCm Doctor watches an AMD-hosted LLM endpoint like production infrastructure, not like a chatbot demo.
It proves the model is reachable, checks runtime assumptions, injects realistic deployment failures,
repairs only safe deterministic config issues, verifies recovery, and writes an incident report.
```

Keep the final video under three minutes:

1. Show AMD MI300X droplet and ROCm evidence.
2. Show vLLM serving `gpt-oss`.
3. Run healthy ROCm Doctor check.
4. Inject wrong endpoint failure.
5. Run self-heal.
6. Show verification and report.

## Stop Conditions

Destroy the droplet if:

- GPU is not visible after first SSH checks.
- vLLM cannot serve either `gpt-oss-120b` or `gpt-oss-20b` within the planned validation window.
- The endpoint is healthy and at least one self-heal report has been saved.
- The active validation session is over.
