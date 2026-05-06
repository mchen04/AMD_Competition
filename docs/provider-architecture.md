# Provider Architecture

ROCm Doctor separates two provider concepts:

- **Model providers** serve model requests. Configured under `model_providers`, accessed via `rocm_doctor.model_providers`.
- **Diagnosis providers** classify evidence and choose repair recipes. Configured under `diagnosis.providers`, implemented in `rocm_doctor/providers/`.

## Model Providers

Each entry defines:

- `adapter` — currently `openai-compatible`.
- `runtime_type` — descriptive label: `fake`, `ollama`, `amd-vllm`, …
- `model.id`, `model.endpoint.{base_url, expected_base_url, wrong_base_url}`
- `model.context.{max_tokens, safe_max_tokens}`
- `model.tool_calling.{enabled, parser, expected_parser, parser_header}`
- `capabilities` — feature flags: `models`, `chat_completions`, `tool_calls`, `context_length`, `rocm_device_flags`, `restart`
- `request.{timeout_seconds, stream, retry}`
- `templates.{health_chat, tool_call_prompt, health_chat_fallbacks}`
- `health.probes`
- `repair.safe_recipes`
- `validation.{expected_health_response, health_response_match, max_response_length, repeated_token_threshold, health_max_tokens}`

Adding another OpenAI-compatible provider is a YAML-only change. A new protocol needs one adapter class implementing `models`, `chat_completion`, `tool_call`, registered in `get_model_provider_adapter`.

OpenAI-compatible streaming is parsed once in `transport.py` and normalized back into a chat-completion-shaped payload before validation runs.

## Diagnosis Providers

Five built-in types, all behind the same `Provider` protocol (`providers/base.py`):

| Type | Module | Notes |
|---|---|---|
| `rules` | `providers/rules/engine.py` + `rules.yaml` | Default. Deterministic. First matching rule wins. |
| `fake` | `providers/fake.py` | Test-only. Exercises safety failures. |
| `openai-responses` | `providers/openai_responses.py` | OpenAI Responses API with strict JSON-schema output. |
| `anthropic-messages` | `providers/anthropic.py` | Claude Messages API with forced tool-use to satisfy schema. |
| `openai-chat-completions` | `providers/openai_compat.py` | Any chat-completions endpoint (OpenRouter, vLLM, LM Studio, Together). |

LLM brains share `LLMDiagnosisProvider._invoke` — render Jinja → POST → parse JSON → validate against `DIAGNOSIS_JSON_SCHEMA` or `REPAIR_PLAN_JSON_SCHEMA`. Missing API key env var raises `OptionalProviderUnavailable` and the harness records `provider_skipped`. Invalid JSON or schema violation records `provider_output_invalid`. Either way the loop falls through cleanly.

Diagnosis output is never trusted directly. The executor only applies known recipes; free-form commands, path traversal, credential edits, unknown recipes, and out-of-allowlist patches are all rejected.

## Recipes

`recipes/registry.yaml` holds metadata (id, description, supported failure classes, supported capabilities, config-path templates, risk level, rollback strategy, verification steps). `recipes/builders.py` holds the Python callable per id that computes the dotted-path config patch.

Adding a recipe = one YAML entry + one builder keyed by id.

Three execution shapes:

1. **Single recipe** — `plan.recipe_id` only.
2. **Recipe sequence** — `plan.recipe_id_sequence` (≥2 ids); applied as a transaction, full rollback on any rejection.
3. **Bounded patch synthesis** — `recipe_id: synthesize_patch`. LLM emits dotted edits in `config_patch.changes`. Executor rejects paths outside the union of paths reachable by other recipes, any type mismatch, anything credential-shaped.

## Healing Policy

`healing_policy.candidate_recipe_ids` orders candidates: learned fixes first → provider-recommended → `failures.yaml` taxonomy default → hardcoded handling for `tool_parser_mismatch`, `context_length_too_large`, `missing_rocm_device_flags`, `endpoint_unreachable`, `unknown_failure`. Filtered to `profile.safe_repair_recipes`.

`self_heal_config` (in `operations.py`) snapshots config, applies one candidate, verifies, and either records a learned fix or rolls back and tries the next. Up to `self_healing.max_attempts`. The same `(failure_class, signature, recipe)` tuple is never retried within a run.

Successful repairs are persisted to the state file's `learned_fixes` keyed by `(provider, failure_class, signature)`.

## Templates

`templates/*.j2`, rendered with `StrictUndefined`. Resolved relative to the active config first; bundled `templates/...` paths fall back to the repo directory.

- `health_chat.j2`, `health_chat.qwen_strict.j2`, `health_chat.no_reasoning.j2`, `health_chat.minimal.j2`, `health_chat.default.j2` — health probe prompts and fallbacks.
- `tool_call_prompt.j2` — deterministic tool-call probe.
- `openai_diagnosis_system.j2` — system instructions for LLM diagnosis.
- `openai_repair_system.j2` — system instructions for LLM repair planning, including provider context, evidence, previous attempts, learned fixes, allowed edit scope, safety rules.
- `anthropic_tool_description.j2` — schema description for Claude tool-use forced JSON.

Render errors surface as health/provider failures, never crashes.

## Incident Reports

`reporting.generate_report` reads the persisted state from the latest check/diagnose/heal/verify/self-heal run. Reports include active model provider, adapter, runtime type, skipped checks, failure class, diagnosis provider, suspected cause, repair recipe, repair status, verification health, and stable before/after evidence. Written under `<workspace>/reports/` (CLI) or `<workspace>/reports/dashboard/` (UI).

## Adversarial Proxy

`rocm_doctor.adversarial_proxy` forwards healthy traffic to a real OpenAI-compatible backend and injects transport/protocol failures around it: `models_500`, `chat_500`, `chat_invalid_json`, `empty_response`, `partial_response`, `rate_limit`, `rate_limit_once`, `slow_response`, `drop_connection`, `empty_chat_content`, `empty_chat_content_once`, `instruction_drift`, `hallucinated_tool_call`, `repetitive_output`, `stream_interrupt`. Use it to exercise failure modes the model alone can't reproduce.

Prompt-level adversarial tests still route through the proxy in `healthy` mode so the real model generates the bad output.

## Dashboard API

`/api/snapshot` (full bundle) · `/api/check` · `/api/run` (202 → SSE at `/api/run/{id}/events`) · `/api/run/{id}` (final result) · `/api/reset` · `/api/active-provider` · `/api/configs`, `/api/configs/select`, `/api/configs/import` · `/api/incident/{id}`.

The dashboard binds against an isolated working copy of the supplied template config. UI clicks and per-request brain overrides never mutate the template config or CLI state.
