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
- Real local `qwen3:0.6b` validation through Ollama when available.
- `smollm2:135m` and `tinyllama:1.1b` profiles as constrained-model rejection checks.
- Optional OpenAI Responses diagnosis provider when `OPENAI_API_KEY` is present.
- AMD/vLLM path documented but not hardcoded.

## Current Local Status

- The no-AMD validation gate is `scripts/local_validate.sh`.
- The deterministic local suite passes through the project venv.
- The fake endpoint demo path works on a copied `/tmp` config: healthy check, `wrong_endpoint_port` injection, rules-driven `self-heal`, verification, and incident report generation.
- Local Ollama `qwen3:0.6b` passes direct health checks and the real-Qwen adversarial suite when installed.
- `smollm2:135m` and `tinyllama:1.1b` are useful negative controls: they are reachable but currently fail strict sentinel health validation by over-answering.

## Remaining Work

- Add a concrete MI300X/vLLM model provider entry after endpoint details and credits are known.
- Record final hackathon demo once AMD credits and deployment constraints are confirmed.
