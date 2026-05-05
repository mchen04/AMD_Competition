# Model-Agnostic Qwen + Codex Validation Agent Prompt

Use this prompt with a coding agent after the local fake-endpoint MVP is implemented.

```text
You are working in the ROCm Doctor repo. The current MVP already has:

- Python package `rocm_doctor`
- CLI commands: check, diagnose, heal, verify, report, inject-failure, fake-endpoint
- deterministic fake OpenAI-compatible endpoint
- typed schemas
- rules/fake/openai-codex provider boundary
- deterministic repair recipes
- executor safety gates
- manual CLI verification path that requires no GPU, Docker, Ollama, OpenAI key, or external network

Read the repository first, especially:

- README.md
- docs/project-plan.md
- docs/self-healing-research-and-codex-provider.md
- docs/local-tiny-model-testing.md
- docs/demo-runbook.md
- docs/implementation-agent-prompt.md
- rocm_doctor/

Goal:
Evolve ROCm Doctor from a fake-endpoint MVP into a model-agnostic self-healing deployment harness validated against a real tiny local model endpoint, preferably Qwen3 0.6B through Ollama or another OpenAI-compatible local server, while preserving the zero-cost fake endpoint as the default test path. Add optional Codex/OpenAI diagnosis and repair planning validation without allowing Codex to execute commands or arbitrary edits.

Important framing:
Do not make the core harness "Qwen Doctor" or "Ollama Doctor". Qwen is just the first real endpoint profile. The architecture should support fake endpoint, Ollama/Qwen, vLLM on AMD, and future OpenAI-compatible endpoints through capability profiles and provider adapters.

Primary product principle:
ROCm Doctor self-heals deployments, not models. Models and runtimes are replaceable. The control loop remains:

1. Monitor: collect endpoint, config, runtime, log, process, and optional GPU evidence.
2. Analyze: classify the failure and root cause.
3. Plan: select a known deterministic recipe.
4. Execute: apply only harness-owned deterministic repairs.
5. Knowledge: save run history, signatures, recipes, and verification evidence.

Core safety rule:
Codex/OpenAI and any other LLM provider may classify failures and choose repair recipes. They must never run arbitrary shell commands, install packages, edit arbitrary files, modify credentials, open network ports, delete files, or bypass recipe validation. The executor remains the only component that writes changes, and only known recipes may be applied.

High-level adaptation plan:

1. Add a runtime/model profile layer.
   - Introduce a schema such as `RuntimeProfile` or `EndpointProfile`.
   - It should describe endpoint protocol, model name, base URL, max context policy, tool-calling capability, expected tool parser if applicable, health probes, known failure signatures, and safe repair recipes.
   - Keep this data in config, not hard-coded in classifiers.
   - Existing fake endpoint config should become one profile.
   - Add an `ollama-qwen` profile for `qwen3:0.6b`.
   - Leave room for a `vllm-amd` profile.

2. Make checks capability-driven.
   - `/v1/models` check applies to OpenAI-compatible endpoints.
   - Chat completion check applies when chat is supported.
   - Tool-call check should run only when the profile says tool calling is supported and should degrade cleanly when a runtime does not support native tool calls.
   - Context-length checks should use the profile's safe threshold.
   - ROCm device flag checks should run only for container/vLLM/AMD-style profiles, not for pure local Ollama unless explicitly configured.

3. Add a real tiny Qwen local validation path.
   - Prefer Ollama if available because setup is simple.
   - Do not make Ollama required for default tests.
   - Add docs for:
     - install/start Ollama
     - pull/run `qwen3:0.6b`
     - expose or adapt to an OpenAI-compatible endpoint
     - point ROCm Doctor at the endpoint config
   - If Ollama's API shape differs from OpenAI-compatible Chat Completions in the local environment, add a small adapter rather than polluting core monitor logic with Ollama-specific branches.

4. Add optional external manual verification.
   - Keep Ollama/Qwen validation opt-in.
   - Keep OpenAI/Codex validation opt-in because it can make paid calls.
   - Default manual verification must remain free, deterministic, offline, and fake-endpoint-only.
   - Document explicit commands for optional Qwen and Codex validation.

5. Validate Qwen with rules first.
   - Start from a healthy local Qwen endpoint.
   - Run:
     - `check`
     - `diagnose --provider rules`
     - `inject-failure wrong_endpoint_port`
     - `heal --provider rules`
     - `verify`
     - `report`
   - Then test context length and tool parser behavior only if the local runtime exposes meaningful failure signals for those scenarios.
   - If Qwen/Ollama cannot support a given failure class directly, document that and keep the fake endpoint as the deterministic scenario source.

6. Validate Codex as planner, not executor.
   - Use the existing `openai-codex` provider boundary.
   - The provider should return only `DiagnosisResult` and `RepairPlan`.
   - Use structured outputs.
   - The provider must be skipped when `OPENAI_API_KEY` is absent.
   - Add tests that mock provider output for safety behavior.
   - Optional live Codex tests should prove:
     - Codex sees evidence from a real or fake endpoint.
     - Codex returns the same schema shape as rules.
     - Codex selects a known recipe.
     - Executor applies only deterministic recipe output.
     - Unsafe Codex output is rejected.

7. Refactor recipe selection to be model/runtime agnostic.
   - Recipes should declare supported failure classes, supported profile capabilities, exact config paths, risk, rollback, and verification steps.
   - Avoid recipes like `fix_qwen_parser` unless the logic is genuinely Qwen-specific.
   - Prefer recipes like `set_tool_parser`, driven by profile config.
   - Prefer `update_endpoint_url`, `lower_max_model_len`, `set_tool_parser`, `set_rocm_device_flags`, and dry-run `restart_known_service`.

8. Improve evidence and reports for real endpoints.
   - Capture endpoint profile id.
   - Capture runtime type: fake, ollama, vllm, openai-compatible, amd-vllm.
   - Capture which checks were skipped and why.
   - Capture before/after config diff in a deterministic way.
   - Never include API keys, tokens, secrets, or credential-like values.

9. Keep docs honest.
   - README should show default fake-endpoint flow first.
   - docs/local-tiny-model-testing.md should show Qwen/Ollama as optional second layer.
   - docs/demo-runbook.md should include both:
     - reliable fake endpoint demo
     - optional real tiny Qwen demo
   - docs/self-healing-research-and-codex-provider.md should state that Codex plans only and the harness executes only deterministic recipes.
   - Add a troubleshooting section for Ollama not installed, Qwen not pulled, endpoint not OpenAI-compatible, tool calls unsupported, and missing OPENAI_API_KEY.

Acceptance gates:

Default gates:

- Manual fake-endpoint verification passes without Ollama, AMD cloud, GPU, Docker, OpenAI key, or external network.
- `python3 -m rocm_doctor --help` works.
- `python3 -m rocm_doctor check --config demo/rocm-doctor.json` works when fake endpoint is running.
- Classic fake endpoint failure scenarios still heal or fail safely exactly as before.
- Safety gates still reject unknown recipes, unsafe commands, path traversal, credential edits, malformed provider output, and non-deterministic provider patches.

Optional Qwen gates:

- A documented Qwen/Ollama config exists.
- When Ollama and `qwen3:0.6b` are available, `check` can validate the endpoint.
- At least wrong endpoint port injection can be diagnosed and healed against the Qwen profile.
- Tool-call checks either pass or are skipped with a clear capability reason.
- Reports identify the runtime profile and skipped checks.

Optional Codex gates:

- With `OPENAI_API_KEY` absent, `diagnose --provider openai-codex` returns/skips cleanly and makes no paid call.
- With `OPENAI_API_KEY` present, Codex returns structured diagnosis and repair plan objects.
- Codex-selected repairs still pass executor safety validation.
- Unsafe or malformed Codex-like output is rejected by tests without changing config.

Suggested implementation sequence:

1. Add profile schema and config loading normalization.
2. Convert existing fake endpoint config into the first profile.
3. Update monitor checks to honor profile capabilities and record skipped checks.
4. Add Qwen/Ollama demo config and docs.
5. Add Qwen wrong-port optional manual validation.
6. Harden `openai-codex` optional validation and docs.
7. Run default manual verification.
8. Run optional Qwen verification only if local Qwen is available.
9. Run optional Codex verification only if `OPENAI_API_KEY` is available.
11. Do a code review focused on model/runtime agnosticism, safety gates, and docs honesty.
12. Fix all blocking findings and rerun relevant gates.

Final response requirements:

Report:

- what changed in the architecture
- how profiles make the harness model/runtime agnostic
- how Qwen was tested or why it was skipped
- how Codex/OpenAI was tested or why it was skipped
- exact commands run and results
- safety gates verified
- remaining limits before AMD Developer Cloud/vLLM validation
```
