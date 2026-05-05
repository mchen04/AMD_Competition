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
- `health.probes`: checks to run.
- `repair.safe_recipes`: deterministic recipes allowed for this provider.

Adding another OpenAI-compatible provider is a YAML-only change unless the provider uses a different protocol. A new protocol should add one adapter class implementing `models`, `chat_completion`, and `tool_call`, then register it in `get_model_provider_adapter`.

## Diagnosis Providers

`rules` is deterministic and default. `fake` exercises safety failures. `openai-codex` is optional, uses the OpenAI Responses API, and is skipped when `OPENAI_API_KEY` is absent.

Diagnosis providers may return structured diagnoses and repair plans, but the executor applies only known recipes. Free-form commands, path traversal, credential edits, unknown recipes, and non-deterministic config patches are rejected.

## Templates

Templates live in `templates/*.j2` and render with `StrictUndefined`.

- `health_chat.j2`: prompt for chat health.
- `tool_call_prompt.j2`: prompt for deterministic tool-call validation.
- `openai_diagnosis_system.j2`: system instructions for optional OpenAI diagnosis.
- `openai_repair_system.j2`: system instructions for optional OpenAI repair planning.

Bad template paths or render errors are reported as health or provider failures instead of crashing the harness.
