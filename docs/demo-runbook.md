# Demo Runbook

The judge-facing demo should be repeatable and short.

## Target Story

Break a working AI agent deployment on AMD Developer Cloud, then run ROCm Doctor and watch it diagnose, repair, verify, and report the recovery.

## Local Demo Loop

Build this before using GPU credits.

1. Start the deterministic fake OpenAI-compatible endpoint:

```bash
python3 -m rocm_doctor fake-endpoint --port 8000
```

2. In another terminal, run a healthy check:

```bash
python3 -m rocm_doctor check --config demo/rocm-doctor.json
```

3. Inject a failure and run the repair loop:

```bash
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/rocm-doctor.json
python3 -m rocm_doctor diagnose --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor heal --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor verify --config demo/rocm-doctor.json
python3 -m rocm_doctor report --config demo/rocm-doctor.json
```

4. Open the generated markdown report under `demo/reports/`.

The report records the active runtime profile and any checks skipped by profile capability.

## Optional Real Tiny Qwen Loop

Use this only after the fake endpoint path is stable.

1. Start Ollama and pull the tiny model:

```bash
ollama serve
ollama pull qwen3:0.6b
```

2. Run the profile-backed check:

```bash
python3 -m rocm_doctor check --config demo/ollama-qwen.json
```

3. Validate the wrong-port repair loop:

```bash
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/ollama-qwen.json
python3 -m rocm_doctor diagnose --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor heal --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor verify --config demo/ollama-qwen.json
python3 -m rocm_doctor report --config demo/ollama-qwen.json
```

The `ollama-qwen` profile checks `/v1/models`, chat completion, and context length. Tool-call checks are skipped because local Ollama/Qwen is not required to emit native OpenAI tool calls for this demo path. ROCm device-flag checks are skipped because local Ollama is not a ROCm container launch.

If the Codex/OpenAI provider is implemented, run diagnosis twice during the local demo:

```bash
python3 -m rocm_doctor diagnose --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor diagnose --provider openai-codex --config demo/rocm-doctor.json
```

The important judge-facing point is that both providers emit the same structured diagnosis shape, while `heal` still applies only deterministic recipes owned by the harness.
If `OPENAI_API_KEY` is absent, `openai-codex` returns a structured `provider_skipped` diagnosis and performs no paid call.

## Minimum Failure Scenarios

### Wrong Endpoint Port

- Symptom: agent cannot reach the model endpoint.
- Diagnosis: configured base URL points at the wrong port.
- Repair: update config to the active endpoint.
- Verification: `/v1/models` and one chat completion pass.

### Context Length Too Large

- Symptom: model server fails to start or crashes on allocation.
- Diagnosis: launch args request an unsafe max model length.
- Repair: lower `--max-model-len` to a known safe value.
- Verification: restart server and run smoke prompts.

### Tool Calling Parser Misconfigured

- Symptom: model responds, but tool calls fail or appear as plain text.
- Diagnosis: selected vLLM tool-calling flags/parser do not match the model.
- Repair: restart with model-appropriate tool-calling settings.
- Verification: deterministic tool-call test passes.

### Missing ROCm Device Flags

- Symptom: launch config does not include required ROCm device nodes.
- Diagnosis: `/dev/kfd` and/or `/dev/dri` missing from the demo launch config.
- Repair: patch `launch.device_flags` with the required flags.
- Verification: config validation passes.

## AMD Cloud Demo Loop

Use this only after the local loop is stable.

1. Create a single MI300X GPU Droplet with the AMD AI/ML-ready image.
2. Verify ROCm with `rocminfo` and `amd-smi` or `rocm-smi`.
3. Start a small vLLM OpenAI-compatible server.
4. Point ROCm Doctor at the remote endpoint.
5. Run one passing check.
6. Inject one controlled failure.
7. Run heal/verify.
8. Save the incident report and a terminal/browser recording.
9. Destroy the GPU Droplet.

## Demo Recording Checklist

- Project name visible: ROCm Doctor
- AMD Developer Cloud or MI300X evidence visible
- Failure is obvious before repair
- Diagnosis names a concrete root cause
- Repair action is specific
- Verification passes after repair
- Final report is readable in under one minute
- Optional Codex/OpenAI provider is framed as diagnosis and repair planning, not uncontrolled execution
