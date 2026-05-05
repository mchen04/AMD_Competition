# Local Tiny Model Testing

We can build and test almost all of ROCm Doctor before AMD Developer Cloud credits are available.

The local goal is not model quality. The goal is protocol and recovery behavior:

1. health checks hit an OpenAI-compatible endpoint
2. failures are detected deterministically
3. diagnosis names a concrete cause
4. repair changes config or runtime state
5. verification proves recovery
6. a report captures the incident

## Recommended Local Stack

Use three levels of realism.

### Level 1: Fake OpenAI-Compatible Endpoint

This should be the first implementation target.

The MVP includes a tiny Python HTTP server:

- `GET /v1/models`
- `POST /v1/chat/completions`
- deterministic tool-call response when `X-ROCm-Doctor-Tool-Parser` matches the expected parser
- failure modes controlled by command-line flags for model/chat endpoint failures and malformed chat JSON

This is best for the first ROCm Doctor loop because it is fast, deterministic, and requires no model download.

Run it with:

```bash
python3 -m rocm_doctor fake-endpoint --port 8000
```

Then point a config at `http://127.0.0.1:8000/v1`.

The default demo config uses:

```json
{
  "active_profile": "fake-openai"
}
```

That profile enables endpoint, chat, tool-call, context-length, ROCm device-flag, and dry-run restart checks.

### Level 2: Smallest Qwen3 Local Model

After the fake endpoint works, run a very small local model behind an OpenAI-compatible server.

Default choice:

- `qwen3:0.6b`
- expected Ollama tag: `qwen3:0.6b-q4_K_M`
- approximate download size: 523 MB
- avoid for local testing unless needed: `qwen3:0.6b-q8_0` and `qwen3:0.6b-fp16`

Use the smallest Qwen3 quantized variant because the project needs endpoint behavior and repair-loop validation, not strong model intelligence. The verifier should assert endpoint shape, tool-call shape, and simple expected tokens rather than judging answer quality.

### Level 3: AMD Developer Cloud vLLM

Use this only after Levels 1 and 2 work.

The AMD validation should swap the local endpoint URL for a real vLLM OpenAI-compatible endpoint on MI300X/ROCm. The rest of ROCm Doctor should not need a redesign.

## Current Machine State

Current local checks showed:

- Apple Silicon macOS
- Python 3.14 available
- Ollama not installed
- llama.cpp tools not installed
- Python ML packages such as `torch`, `transformers`, `mlx`, and `mlx_lm` not installed

That makes the fake endpoint the fastest zero-install path. Installing Ollama later is the simplest route for the real tiny local model: `qwen3:0.6b`.

## Ollama Path

If using Ollama, the expected workflow is:

```bash
ollama serve
ollama pull qwen3:0.6b
```

Then use the included optional config:

```bash
python3 -m rocm_doctor check --config demo/ollama-qwen.json
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/ollama-qwen.json
python3 -m rocm_doctor diagnose --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor heal --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor verify --config demo/ollama-qwen.json
python3 -m rocm_doctor report --config demo/ollama-qwen.json
```

`demo/ollama-qwen.json` expects Ollama's OpenAI-compatible API at `http://127.0.0.1:11434/v1`. If the local Ollama build does not expose that API, add a small adapter server that exposes the exact `/v1/models` and `/v1/chat/completions` behavior ROCm Doctor expects.

The `ollama-qwen` profile intentionally skips native OpenAI tool-call verification and ROCm container device-flag checks. Those skipped checks are included in evidence and reports with explicit reasons. The fake endpoint remains the deterministic source for tool-parser and ROCm flag failure scenarios.

The profile also uses a longer `request_timeout_seconds` than the fake endpoint because the first local model chat request may include model load time.

Do not start with larger Qwen tags. Only move up if the smallest model cannot produce stable enough output for a demo check.

## What To Avoid

- Do not block the core harness on model quality.
- Do not spend AMD GPU credits debugging local control-flow bugs.
- Do not require a large model for the demo; the judge should see recovery behavior, not benchmark quality.
- Do not hard-code Ollama-specific behavior into the core harness; keep the endpoint OpenAI-compatible.

## Acceptance Criteria

The local tiny-model path is good enough when:

- `check` can detect healthy and unhealthy endpoints
- `diagnose` can distinguish wrong port from bad model/tool config
- `heal` can patch a local config
- `verify` reruns the endpoint checks
- `report` writes a clear incident summary

Current default local verification uses the fake endpoint. Ollama and `qwen3:0.6b` remain optional.

Run the optional Qwen loop only when Ollama is installed, serving, and `qwen3:0.6b` is pulled:

```bash
python3 -m rocm_doctor check --config demo/ollama-qwen.json
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/ollama-qwen.json
python3 -m rocm_doctor diagnose --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor heal --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor verify --config demo/ollama-qwen.json
```

Live Codex/OpenAI validation is intentionally manual because it makes paid API calls:

```bash
python3 -m rocm_doctor diagnose --provider openai-codex --config demo/rocm-doctor.json
python3 -m rocm_doctor heal --provider openai-codex --config demo/rocm-doctor.json
```

The default fake-endpoint command path remains offline, free, deterministic, and local-only.
