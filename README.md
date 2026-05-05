# ROCm Doctor

ROCm Doctor is an agentic self-healing harness for AI deployments on AMD Developer Cloud.

The demo story is simple: start with a working vLLM-powered agent on AMD GPUs, inject a realistic failure, run `check -> diagnose -> heal -> verify`, and produce an incident report that explains what broke and how it was fixed.

The MVP now runs fully locally with a deterministic OpenAI-compatible fake endpoint, no GPU, no Docker, no Ollama, no AMD cloud, and no paid API.

## Hackathon Scope

- Track: AI Agents and Agentic Workflows
- Platform: AMD Developer Cloud on DigitalOcean
- Target hardware: 1x AMD Instinct MI300X GPU
- Runtime: ROCm, Docker, vLLM, OpenAI-compatible endpoint
- MVP surface: local CLI first, optional Streamlit UI after the loop works
- Local real-model target: `qwen3:0.6b` using the smallest Ollama quantized variant

## Why It Matters

Most hackathon projects build an agent that completes a user task. ROCm Doctor builds an agent that keeps other agents alive.

It watches model-serving and agent runtime health, classifies failure symptoms, applies safe repairs, reruns validation checks, and writes a postmortem developers can act on.

## Documentation

- [Documentation Index](docs/README.md)
- [Project Plan](docs/project-plan.md)
- [Self-Healing Research And Codex Provider Plan](docs/self-healing-research-and-codex-provider.md)
- [Local Tiny Model Testing](docs/local-tiny-model-testing.md)
- [AMD Developer Cloud Setup](docs/amd-developer-cloud-setup.md)
- [Demo Runbook](docs/demo-runbook.md)
- [Submission Checklist](docs/submission-checklist.md)

## Current Priorities

1. Run and polish the local fake-endpoint demo loop.
2. Keep the executor deterministic: providers can classify and propose repairs, but only known recipes are applied.
3. Use `openai-codex` only as an optional structured diagnosis/planning provider when `OPENAI_API_KEY` is present.
4. Test against `qwen3:0.6b` locally only after the fake endpoint loop is stable.
5. Keep GPU spend at zero until AMD credits are visible in the cloud console.
6. Launch a single MI300X GPU Droplet only when the local demo is ready to validate on ROCm.
7. Record a repeatable judge-facing demo: break the agent, heal it, show the evidence.

## Quick Start

Use `python3` on macOS if `python` is not installed.

Terminal 1:

```bash
python3 -m rocm_doctor fake-endpoint --port 8000
```

Terminal 2:

```bash
python3 -m rocm_doctor --help
python3 -m rocm_doctor check --config demo/rocm-doctor.json
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/rocm-doctor.json
python3 -m rocm_doctor diagnose --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor heal --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor verify --config demo/rocm-doctor.json
python3 -m rocm_doctor report --config demo/rocm-doctor.json
```

Manual local verification path:

```bash
python3 -m rocm_doctor fake-endpoint --port 8000
python3 -m rocm_doctor check --config demo/rocm-doctor.json
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/rocm-doctor.json
python3 -m rocm_doctor diagnose --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor heal --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor verify --config demo/rocm-doctor.json
```

Optional real Qwen verification uses Ollama's OpenAI-compatible API:

```bash
brew install ollama
brew services start ollama
ollama pull qwen3:0.6b
python3 -m rocm_doctor check --config demo/ollama-qwen.json
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/ollama-qwen.json
python3 -m rocm_doctor diagnose --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor heal --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor verify --config demo/ollama-qwen.json
```

Optional Codex/OpenAI planner validation makes a paid API call when `OPENAI_API_KEY` is set:

```bash
python3 -m rocm_doctor diagnose --provider openai-codex --config demo/rocm-doctor.json
python3 -m rocm_doctor heal --provider openai-codex --config demo/rocm-doctor.json
```

If your shell maps `python` to Python 3.11 or newer, the same commands work as `python -m ...`.

## Implemented Architecture

- `rocm_doctor.config`: config loading and runtime profile normalization. Legacy `model.*` fields remain the repair target, while `active_profile` and `profiles` define endpoint capabilities and safe recipes.
- `rocm_doctor.schemas`: typed dataclass schemas for health checks, evidence, diagnoses, repair plans, repair results, verification results, and incident reports.
- `rocm_doctor.monitor`: profile-driven endpoint, chat, tool-call, context-length, and ROCm device-flag checks, with skipped checks recorded in evidence.
- `rocm_doctor.providers`: provider boundary for `rules`, `fake`, optional `openai-codex`, and delegating placeholders for `ollama-qwen` and `vllm-amd`.
- `rocm_doctor.recipes`: explicit deterministic repair recipes with supported profile capabilities, risk, preconditions, rollback notes, and verification steps.
- `rocm_doctor.executor`: safety gate that rejects unknown recipes, shell commands, credential edits, path traversal, out-of-workspace edits, and non-deterministic provider patches.
- `rocm_doctor.failure_injection`: repeatable local failure scenarios.
- `rocm_doctor.fake_endpoint`: local fake OpenAI-compatible endpoint with `/v1/models` and `/v1/chat/completions`.
- `rocm_doctor.reporting`: markdown and JSON incident reports under the configured reports directory.

## Runtime Profiles

The default config uses the `fake-openai` profile. It exercises every deterministic local check and repair path without paid services or hardware.

`demo/ollama-qwen.json` is the optional real tiny-model profile for `qwen3:0.6b` behind Ollama's OpenAI-compatible API. It enables `/v1/models`, chat, and context checks, while skipping native tool-call and ROCm container checks with explicit reasons in evidence and reports.

## Failure Scenarios

The local loop supports these injected failures:

- `wrong_endpoint_port`: repairs `model.base_url` back to `model.expected_base_url`.
- `context_length_too_large`: lowers `model.max_model_len` to `model.safe_max_model_len`.
- `tool_parser_mismatch`: restores `model.tool_parser` to `model.expected_tool_parser`.
- `missing_rocm_device_flags`: restores required `/dev/kfd` and `/dev/dri` launch flags.
- Provider safety scenarios: `malformed_provider_output`, `unknown_recipe`, `unsafe_command`, `path_traversal`, and `credential_modification` fail safely with no config changes.

## Troubleshooting

- If `python` is missing on macOS, run the commands with `python3`.
- If `check` reports `GET /v1/models failed`, make sure `fake-endpoint` is running on the same port as `model.base_url`.
- If `tool-call verification failed`, reset with `python3 -m rocm_doctor heal --config demo/rocm-doctor.json`.
- If a provider repair is rejected, inspect the JSON output's `reason`; the executor intentionally rejects unsafe provider output.
- Generated reports are written to `demo/reports/` for the demo config.
- If `demo/ollama-qwen.json` fails, confirm Ollama is serving `qwen3:0.6b` at `http://127.0.0.1:11434/v1`.
- If `openai-codex` returns `provider_skipped`, set `OPENAI_API_KEY` only for the command that should make a paid OpenAI API call.
