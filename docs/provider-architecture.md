# Provider Architecture

ROCm Doctor separates two provider concepts:

- Model providers serve model requests. They are configured under `model_providers` and accessed through `rocm_doctor.model_providers`.
- Diagnosis providers classify evidence and choose repair recipes. They are configured under `diagnosis.providers` and implemented in `rocm_doctor.providers`.

## Model Providers

Each model provider entry defines:

- `adapter`: currently `openai-compatible`.
- `runtime_type`: descriptive runtime label such as `fake`, `ollama`, or `amd-vllm`.
- `model.id`: provider-specific model id.
- `model.endpoint`: `base_url`, `expected_base_url`, and `wrong_base_url` used by health checks and repair scenarios.
- `model.context`: `max_tokens` and `safe_max_tokens`.
- `model.tool_calling`: parser settings and whether native tool-call checks are enabled.
- `capabilities`: feature flags for models, chat, tool calls, context checks, ROCm device flags, and restart.
- `request`: timeout, streaming, retry count, retry statuses, and retry-on-invalid-JSON behavior.
- `templates`: Jinja files for health and tool-call prompts.
- `templates.health_chat_fallbacks`: ordered prompt fallbacks used by template self-healing.
- `health.probes`: checks to run.
- `repair.safe_recipes`: deterministic recipes allowed for this provider.
- `validation`: expected health sentinel, response matching mode, max response length, repeated-token guard, and health generation budget.

Adding another OpenAI-compatible provider is a YAML-only change unless the provider uses a different protocol. A new protocol should add one adapter class implementing `models`, `chat_completion`, and `tool_call`, then register it in `get_model_provider_adapter`.

OpenAI-compatible streaming is parsed once in the shared transport layer and normalized back into a chat-completion-shaped payload before adapter validation runs.

## Diagnosis Providers

`rules` is deterministic and default. `fake` exercises safety failures. `openai-codex` is optional, uses the OpenAI Responses API, and is skipped when `OPENAI_API_KEY` is absent.

Diagnosis providers may return structured diagnoses and repair plans, but the executor applies only known recipes. Free-form commands, path traversal, credential edits, unknown recipes, and non-deterministic config patches are rejected.

## Healing Policy

`rocm_doctor.healing_policy` maps failure classes to safe candidate recipes. The loop does not stop at the first diagnosis unless no safe candidate exists. It ranks learned fixes first, then provider-recommended recipes, then taxonomy defaults.

The policy covers endpoint errors, one-time and repeated rate limits, timeouts, empty Qwen output, instruction drift, repetitive loops, broken streaming, bad templates, permanent provider 500s, invalid config, context limits, tool parser mismatch, and missing ROCm device flags.

For each candidate, `self-heal` snapshots the normalized config, applies one deterministic recipe through the executor, verifies the health check, and keeps the edit only if verification passes. Failed edits are rolled back before the next recipe is tried. The loop does not keep retrying the same recipe for the same failure signature. Successful repairs are recorded in the configured state file under `learned_fixes`.

## Templates

Templates live in `templates/*.j2` and render with `StrictUndefined`. Template paths are resolved relative to the active config first; copied demo configs can also resolve bundled `templates/...` references back to the repository template directory.

- `health_chat.j2`: prompt for chat health.
- `health_chat.qwen_strict.j2`, `health_chat.no_reasoning.j2`, `health_chat.minimal.j2`: fallback health prompts for Qwen drift, loops, empty output, or bad template recovery.
- `tool_call_prompt.j2`: prompt for deterministic tool-call validation.
- `openai_diagnosis_system.j2`: system instructions for optional OpenAI diagnosis.
- `openai_repair_system.j2`: dynamic system instructions for optional OpenAI repair planning, including provider context, health evidence, previous attempts, learned fixes, allowed edit scope, rollback, and safety rules.

Bad template paths or render errors are reported as health or provider failures instead of crashing the harness.

## Incident Reports

The `report` command reads the persisted state from the latest check, diagnosis, repair, verification, or `self-heal` run. Reports include the active model provider, adapter, runtime type, skipped checks, failure class, diagnosis provider, suspected cause, repair recipe, repair status, verification health, and stable before/after evidence.

## Real-Backend Adversarial Proxy

`rocm_doctor.adversarial_proxy` forwards healthy traffic to a real OpenAI-compatible backend and injects failure modes around that backend. Use it when a failure is transport/protocol-level and cannot be caused by the model alone, such as malformed JSON, partial responses, rate limits, dropped connections, slow responses, provider 500s, or streaming interruptions.

Prompt-level adversarial tests should still route through the proxy in healthy mode so the real model generates the bad output.
