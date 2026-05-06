# ROCm Doctor

ROCm Doctor is a self-healing harness for model-serving and agent runtimes. It checks an OpenAI-compatible endpoint, diagnoses failures, applies only deterministic repair recipes, verifies recovery, rolls back failed repairs, and writes incident evidence.

The codebase is model-agnostic and provider-agnostic: model runtime details live in YAML under `model_providers`, prompt text lives in Jinja templates, and Python code talks to providers through adapters.

## Quick Start

Install dependencies in a virtual environment:

```bash
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
```

Run the local deterministic endpoint in one terminal:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor fake-endpoint --port 8000
```

Run the harness in another terminal:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal --provider rules --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor report --config demo/rocm-doctor.yaml
```

Use a copy of the demo config when you want to mutate it repeatedly.

Open the web console (static React app under `web/`, served by Python's stdlib HTTP server):

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor dashboard --port 8765
```

Then visit `http://localhost:8765/`. The console surfaces all 16 failure classes from `healing_policy.FAILURE_TAXONOMY` and the 17 recipes from `recipes.py`, and animates the `check → diagnose → heal → verify → report` loop for any injected failure.

The dashboard binds against an isolated working copy of the supplied template config (`<workspace>/.rocm-doctor.dashboard.yaml`) and writes incident reports under `<workspace>/reports/dashboard/`, so the template config and CLI state are never mutated by clicks in the UI. POST `/api/reset` restores the working copy from the template.

When scripting browser tests (e.g. via `agent-browser`), prefer `find text "<chip-label>" click` or a direct `eval "(() => Array.from(document.querySelectorAll('.failure-grid .chip')).find(b => b.textContent.trim() === '<id>').click())()"` over `click @<ref>` — React 18's delegated event listener can ignore the `@ref` form when refs go stale across re-renders. Real human clicks are unaffected.

Run the full no-AMD local validation path:

```bash
scripts/local_validate.sh
```

This creates or reuses `/tmp/rocm-doctor-venv`, runs compile and pytest checks, exercises the fake-endpoint demo loop on a copied config, writes an incident report, and runs the optional real-Qwen suite when local Ollama is serving `qwen3:0.6b`.

## Core Files

- `rocm_doctor/config.py`: YAML loading, normalization, validation, path helpers, redaction.
- `rocm_doctor/model_providers.py`: model-provider adapter boundary. The implemented adapter is `openai-compatible`.
- `rocm_doctor/transport.py`: shared HTTP transport, retries, rate-limit, timeout, JSON, and SSE streaming handling.
- `rocm_doctor/adversarial_proxy.py`: real-backend proxy for injecting transport/protocol failures in front of local Qwen or another OpenAI-compatible runtime.
- `rocm_doctor/templates.py`: strict Jinja template rendering.
- `rocm_doctor/providers.py`: diagnosis/planning providers: `rules`, `fake`, optional `openai-codex`.
- `rocm_doctor/healing_policy.py`: failure taxonomy, candidate-recipe ordering, and learned-fix lookup.
- `rocm_doctor/recipes.py`: deterministic repair recipes and allowed config paths.
- `rocm_doctor/executor.py`: safety gate for recipe execution.
- `tests/`: integration and stress coverage for Qwen, two additional tiny-model profiles, malformed responses, retries, tool calls, config failures, and self-healing loops.

## Config Layout

- `demo/rocm-doctor.yaml`: local fake OpenAI-compatible provider with all deterministic checks enabled.
- `demo/ollama-tiny-models.yaml`: optional Ollama profiles for `qwen3:0.6b`, `smollm2:135m`, and `tinyllama:1.1b`.
- `demo/amd-vllm-template.yaml`: AMD Developer Cloud/vLLM template with MI300X hooks.
- `templates/*.j2`: health-check, tool-call, and OpenAI Responses diagnosis/planning templates.

To add a model provider, add one entry under `model_providers`, set `active_model_provider`, and choose capabilities, endpoint URLs, context limits, retry settings, prompt template fallbacks, health probes, and safe recipes. The core monitor and executor should not change for another OpenAI-compatible runtime.

## Self-Healing Behavior

The `self-heal` command runs `check -> diagnose -> candidate recipes -> apply one safe recipe -> verify`. Every attempted config edit snapshots the current config first. If verification fails, ROCm Doctor restores the snapshot and tries the next safe candidate. Successful repairs are stored in the state file under `learned_fixes` so the same provider/failure signature tries the known working recipe first next time.

Current deterministic recipes include endpoint repair, retry-only recovery, retry backoff tuning, timeout increases, streaming disablement, Qwen health-token tuning, prompt template fallback, strict health-response validation, weak-model tool-probe disablement, fallback-provider switching, last-known-good config restore, context-limit lowering, tool-parser correction, ROCm device flag repair, and dry-run restart accounting.

## Verification

Run the complete no-AMD local validation path:

```bash
scripts/local_validate.sh
```

Manual deterministic checks:

```bash
/tmp/rocm-doctor-venv/bin/python -m compileall rocm_doctor tests
/tmp/rocm-doctor-venv/bin/python -m pytest -q
```

Optional real tiny-model checks require Ollama:

```bash
ollama pull qwen3:0.6b
ollama pull smollm2:135m
ollama pull tinyllama:1.1b
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check --config demo/ollama-tiny-models.yaml
```

`qwen3:0.6b` is the primary local model proof path. `smollm2:135m` and `tinyllama:1.1b` are intentionally useful as weak-model rejection checks when they over-answer the strict health sentinel.

Run the full real-Qwen adversarial suite when local Ollama is hosting `qwen3:0.6b`:

```bash
ROCM_DOCTOR_RUN_REAL_QWEN=1 /tmp/rocm-doctor-venv/bin/python -m pytest tests/test_real_qwen_adversarial.py -q -s
```

## AMD Readiness

AMD-specific assumptions are config, not code: `hardware`, `launch.required_device_flags`, provider endpoint URLs, context limits, safe recipes, and stress-test targets are all YAML-controlled. For MI300X/vLLM validation, add or activate a `model_providers` entry with the vLLM endpoint, ROCm device flags, benchmark profile, and context limit appropriate for that deployment.

See `docs/provider-architecture.md` and `docs/testing-and-amd-readiness.md` for maintainer details.
