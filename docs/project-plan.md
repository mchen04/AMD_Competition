# Project Plan

ROCm Doctor demonstrates an agentic reliability loop for AMD-oriented model deployments:

```text
check -> diagnose -> heal -> verify -> report
```

The current implementation is local-first and provider-agnostic. It validates the loop against a deterministic OpenAI-compatible endpoint, then keeps Ollama and AMD/vLLM as YAML-configured runtime targets.

## Build Priorities

1. Keep model/runtime specifics in YAML `model_providers`.
2. Keep prompts in Jinja templates.
3. Keep provider HTTP behavior behind adapters.
4. Keep diagnosis providers structured and optional.
5. Keep repair execution deterministic and safety-gated.
6. Keep AMD hardware assumptions configurable until real MI300X validation.

## Demo Scope

- Local fake endpoint for zero-cost repeatability.
- Qwen and two extra tiny-model profiles for constrained-model validation.
- Optional OpenAI Responses diagnosis provider when `OPENAI_API_KEY` is present.
- AMD/vLLM path documented but not hardcoded.

## Remaining Work

- Run the real Ollama tiny-model checks on machines with those models installed.
- Add a concrete MI300X/vLLM model provider entry after endpoint details are known.
- Record final hackathon demo once AMD credits and deployment constraints are confirmed.
