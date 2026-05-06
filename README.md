# ROCm Doctor

Self-healing supervisor for self-hosted, OpenAI-compatible model endpoints (vLLM on AMD MI300X, Ollama, any chat-completions server). It runs `check → diagnose → heal → verify → report` in a bounded loop, applies only deterministic config repairs, and rolls back anything that doesn't recover the endpoint.

Diagnosis is pluggable (rules engine or any of three LLM brains). Repair execution is not — every fix maps to one of 18 audited recipes that can only edit allowlisted YAML paths.

## Quick Start

```bash
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'

# Terminal 1: deterministic local endpoint
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor fake-endpoint --port 8000

# Terminal 2: the loop
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check        --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal    --config demo/rocm-doctor.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor report       --config demo/rocm-doctor.yaml
```

Use a copy of the demo config when you want to mutate it repeatedly.

Web console (Vite/React, served by stdlib HTTP + SSE):

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor dashboard --port 8765
```

Open `http://localhost:8765/`. The topbar exposes two pills — **active model provider** (which OpenAI-compatible runtime is being healed) and **diagnosis brain** (`rules`, `openai-codex`, `anthropic`, or `openai-compatible`). Brains whose API key env var is absent skip gracefully and the harness falls through. The dashboard binds against an isolated working copy at `<workspace>/.rocm-doctor.dashboard.yaml` and writes reports under `<workspace>/reports/dashboard/`; the template config is never mutated by clicks. `POST /api/reset` restores the working copy.

When scripting browser tests, prefer `find text "<chip-label>" click` over `click @<ref>` — React 18's delegated event listener can ignore stale refs.

Full no-AMD validation gate:

```bash
scripts/local_validate.sh
```

This runs `compileall`, `pytest`, the fake-endpoint demo loop on a copied config, report generation, and the optional real-Qwen suite when Ollama is serving `qwen3:0.6b`.

## Architecture

```
diagnosis brain  →  recipe_id  →  executor  →  verifier  →  learned-fixes
(rules or LLM)     (audited list)  (allowlist+    (re-runs    (provider, signature)
                                    rollback)      probes)     → recipe
```

- **`monitor.py`** — health probes against `/v1/models`, `/v1/chat/completions`, optional tool-call probe, context-length check. Emits an `EvidenceBundle`.
- **`providers/`** — diagnosis brains. `rules` evaluates `providers/rules/rules.yaml`; LLM brains share `LLMDiagnosisProvider` in `providers/base.py` and call out via Jinja-rendered prompts under structured JSON-schema output.
- **`failures.yaml`** — 13 failure classes mapped to ordered candidate recipes.
- **`recipes/registry.yaml` + `recipes/builders.py`** — 18 deterministic recipes. YAML metadata + Python builder per id.
- **`healing_policy.py`** — orders candidates: learned fixes first, then provider-recommended, then taxonomy default. Filtered to the active profile's `safe_repair_recipes`.
- **`executor.py`** — applies a recipe (or recipe sequence, or bounded patch synthesis), snapshots config, validates type/path/credential safety, rolls back on verification failure.
- **`operations.py`** — orchestrates the full `self_heal_config` loop with `max_attempts`.
- **`state.py`** — persists `learned_fixes` keyed by `(provider, failure_class, signature)` so repeat incidents try the known-good recipe first.
- **`dashboard.py`** — `/api/snapshot`, `/api/check`, `/api/run` (SSE), `/api/reset`, `/api/active-provider`, `/api/configs/{select,import}`, `/api/incident/{id}`.
- **`adversarial_proxy.py`** — sits in front of a real backend and injects 16 transport/protocol failure modes for stress testing.

## What the LLM Brain Can and Cannot Do

The repair-system prompt (`templates/openai_repair_system.j2`) constrains the LLM to three escalating outputs:

1. **Single recipe** — pick one entry from the active profile's safe list.
2. **Recipe sequence** — pick a primary recipe plus an ordered list applied as one transaction; any rejection rolls the whole sequence back.
3. **Bounded patch synthesis** — emit `recipe_id: synthesize_patch` with dotted YAML edits. The executor rejects any path outside the union of recipe-reachable paths, any value whose type doesn't match the existing one, and anything credential-shaped.

The LLM cannot run shell, edit Python, change credentials, or write files outside the workspace. Prompt-injection escalation is bounded by the executor, not by the prompt.

## Recipes (18)

`noop`, `retry_without_config_change`, `update_endpoint_url`, `increase_health_max_tokens`, `lower_health_max_tokens`, `increase_timeout`, `increase_retry_backoff`, `disable_streaming`, `switch_prompt_template`, `fallback_model_provider`, `restore_last_known_good_config`, `tighten_expected_health_response`, `disable_tool_probe_for_weak_model`, `lower_max_model_len`, `set_tool_parser`, `set_rocm_device_flags`, `synthesize_patch`, `restart_known_service` (dry-run only).

## Failure Classes (13)

`endpoint_broken`, `wrong_endpoint_port`, `one_time_rate_limit`, `repeated_rate_limit`, `timeout`, `empty_qwen_output`, `instruction_drift`, `repetitive_loop`, `broken_streaming`, `bad_template`, `permanent_500`, `invalid_config`, `config_invalid`. Plus harness-emitted `provider_output_invalid`, `provider_skipped`, `unknown_failure`, `tool_parser_mismatch`, `context_length_too_large`, `missing_rocm_device_flags` handled by `healing_policy.py` directly.

## Configs

- `demo/rocm-doctor.yaml` — local fake provider, all checks enabled.
- `demo/ollama-tiny-models.yaml` — Ollama profiles for `qwen3:0.6b`, `smollm2:135m`, `tinyllama:1.1b`.
- `demo/amd-vllm-template.yaml` — MI300X/vLLM template with ROCm device hooks.

To add a model provider, add an entry under `model_providers`, set `active_model_provider`, choose capabilities, endpoint URLs, context limits, retry settings, prompt template fallbacks, and safe recipes. The core monitor and executor do not change.

## Chaos Suite

Opt-in pre-merge gate. The default `local_validate.sh` stays at ~30s; add `CHAOS=1` to run the full suite:

```bash
CHAOS=1 scripts/local_validate.sh
```

Five layers, aggregated into `docs/chaos-report-<date>.md`:

1. **Deterministic chaos pytests** — randomized 50-round real/safety sweep, chained failures, learned-fix replay (`attempts == 1` after one priming run), recipe-sequence heal.
2. **Adversarial-proxy sweep against real Ollama qwen3:0.6b** — all 16 `ADVERSARIAL_FAILURE_MODES` driven through detect → heal → verify. **5 modes heal** (`healthy`, `rate_limit_once`, `slow_response` → `increase_timeout`, `empty_chat_content_once` → `increase_health_max_tokens`, `stream_interrupt` → `disable_streaming`); **11 modes are detect-only by design** (`chat_500`, `models_500`, `rate_limit`, `chat_invalid_json`, `empty_response`, `partial_response`, `drop_connection`, `empty_chat_content`, `instruction_drift`, `hallucinated_tool_call`, `repetitive_output` — these inject *permanent* upstream failures that no config edit can recover from while the proxy is misbehaving). Layer fails if any expected-heal mode misses.
3. **Two-brain stress matrix** — `PROVIDERS="rules openai-codex" scripts/stress_matrix.sh` walks providers × scenarios via the dashboard `/api/run`. Anthropic/OpenRouter excluded by default; add to `PROVIDERS` when keys are present.
4. **Aggregator** — `scripts/chaos_full.sh`, exits non-zero on any layer failure.
5. **Supervisor stability soak** — `scripts/chaos_supervisor.py` runs 100 cycles of randomized real-scenario injection. Pass criteria: 100% heal rate, mean attempts ≤ 1.5 by round 50 (proves learned fixes save cycles).

The detect-only modes are a feature, not a gap: a self-healing system has to know when it can't help. See `docs/testing-and-amd-readiness.md` for the full env-var table.

## AMD Readiness

AMD specifics live entirely in YAML: `hardware`, `launch.required_device_flags`, vLLM endpoint URL, context limits, safe recipes. For MI300X, activate a `model_providers` entry pointing at the deployed vLLM endpoint with `runtime_type: amd-vllm` and the appropriate ROCm device flags.

See `docs/` for setup, demo, testing, and provider details.
