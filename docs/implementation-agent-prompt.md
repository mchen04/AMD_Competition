# Implementation Agent Prompt

Use this prompt with a coding agent to build ROCm Doctor end to end from this repo.

```text
You are working in the ROCm Doctor repo. Read the repository first, especially:

- README.md
- docs/project-plan.md
- docs/self-healing-research-and-codex-provider.md
- docs/local-tiny-model-testing.md
- docs/demo-runbook.md
- docs/submission-checklist.md

Goal:
Implement ROCm Doctor as a local-first, provider-agnostic, self-healing AI deployment harness. Build the full MVP, then repeatedly break it on purpose, test whether it heals, refactor weak areas, and rerun the verification loop until all acceptance gates pass with no blocking findings.

Important framing:
Do not chase "perfect" as an undefined endpoint. Treat the project as complete only when the acceptance gates below pass and a final review finds no blocking correctness, safety, or maintainability issues.

Product behavior:
ROCm Doctor is a MAPE-K-style control loop:

1. Monitor: collect endpoint, runtime, config, log, process, and optional GPU evidence.
2. Analyze: classify the failure and identify the likely root cause.
3. Plan: choose a bounded repair recipe.
4. Execute: apply the approved deterministic repair.
5. Knowledge: save run history, known signatures, safe recipes, and verification evidence.

MVP commands:

- rocm-doctor check
- rocm-doctor diagnose --provider rules
- rocm-doctor heal
- rocm-doctor verify
- rocm-doctor report
- rocm-doctor inject-failure <scenario>
- optional: rocm-doctor diagnose --provider openai-codex

Core safety rule:
LLM providers may classify failures and propose repair plans. They must not execute arbitrary shell commands or arbitrary file edits. The executor may apply only known deterministic recipes owned by the harness.

Implementation requirements:

1. Build a Python package with a clean CLI.
2. Prefer simple, boring dependencies. Use the standard library where reasonable.
3. Keep modules small and named by responsibility.
4. Define typed schemas for:
   - HealthCheckResult
   - EvidenceBundle
   - DiagnosisResult
   - RepairPlan
   - RepairResult
   - VerificationResult
   - IncidentReport
5. Implement a provider interface:
   - rules: default deterministic provider
   - fake: deterministic fake model endpoint/provider for tests
   - ollama-qwen: optional local qwen3:0.6b endpoint adapter
   - openai-codex: optional OpenAI Responses API provider for structured diagnosis and repair planning
   - vllm-amd: future AMD Developer Cloud/vLLM endpoint provider
6. The rules provider must work without API keys, GPUs, network access, Ollama, or AMD cloud.
7. The openai-codex provider must be optional and skipped when OPENAI_API_KEY is absent.
8. Add a fake OpenAI-compatible endpoint for local testing:
   - GET /v1/models
   - POST /v1/chat/completions
   - deterministic tool-call-like response if needed
   - failure modes controlled by config or CLI
9. Add deterministic repair recipes:
   - update_endpoint_url
   - lower_max_model_len
   - set_tool_parser
   - restart_known_service as a dry-run or local fake-service action only
10. Each repair recipe must declare:
   - id
   - supported failure classes
   - preconditions
   - exact config paths it can modify
   - risk level
   - rollback strategy
   - verification steps
11. The executor must reject:
   - free-form shell commands from model output
   - unknown recipe ids
   - edits outside the configured demo workspace
   - credential modifications
   - destructive filesystem actions
   - network port changes unless explicitly part of a known local fake endpoint scenario

Classic failure scenarios to implement and test:

1. Wrong endpoint port
   - Break: set model.base_url to a closed/wrong port.
   - Detect: /v1/models fails.
   - Diagnose: endpoint_unreachable or wrong_endpoint_port.
   - Heal: update config to active endpoint.
   - Verify: /v1/models and one chat completion pass.

2. Context length too large
   - Break: set max_model_len above allowed local/demo threshold.
   - Detect: fake endpoint or config verifier rejects launch config.
   - Diagnose: context_length_too_large.
   - Heal: lower max_model_len to safe value.
   - Verify: config validation and smoke prompt pass.

3. Tool-calling parser mismatch
   - Break: set tool_parser to a wrong value for the configured model.
   - Detect: tool-call verification fails or returns plain text.
   - Diagnose: tool_parser_mismatch.
   - Heal: set known-good parser value.
   - Verify: deterministic tool-call check passes.

4. Missing ROCm device flags, simulated locally
   - Break: remove required flags from demo launch config.
   - Detect: config verifier reports missing /dev/kfd or /dev/dri.
   - Diagnose: missing_rocm_device_flags.
   - Heal: patch launch config with required flags.
   - Verify: config validation passes.

5. Malformed provider output
   - Break: fake provider returns invalid schema, unknown recipe, or unsafe command.
   - Detect: schema validation or safety gate fails.
   - Heal: do not apply repair; report provider_output_invalid.
   - Verify: no unsafe changes occurred.

Manual robustness requirements:

1. Exercise each failure scenario from the CLI:
   - start healthy state
   - inject break
   - check detects unhealthy state
   - diagnose returns expected failure class
   - heal applies only expected deterministic changes
   - verify passes
   - report contains before/after evidence
2. Exercise negative cases manually:
   - unknown provider
   - unknown recipe id
   - unsafe command in model output
   - attempted path traversal in config patch
   - malformed JSON/model output
   - unreachable endpoint
   - missing config file
   - corrupted config file
   - absent optional OPENAI_API_KEY
3. The default manual path must not require AMD cloud, real GPUs, paid APIs, Ollama, Docker, or external network.
4. Optional external validation for Ollama/Qwen, OpenAI/Codex, or AMD cloud must be explicitly documented and opt-in.
5. Add demo configs for all classic breaks where practical.
6. Produce deterministic enough incident reports to inspect before/after evidence.
7. Try to break it by enumerating invalid configs, unsafe recipe ids, malformed provider outputs, repeated heals, and already-healthy states.

Verification commands:
Define and run the repo's standard verification commands. If the repo does not have tooling yet, add it. At minimum support:

- python -m rocm_doctor --help
- python -m rocm_doctor check --config <fixture>
- python -m rocm_doctor inject-failure <scenario> --config <fixture>

If you add linting/type checking, make it easy to run locally and avoid fragile configuration.

Development loop:

1. Inspect the repo and summarize the implementation plan.
2. Implement the smallest vertical slice first:
   - config load
   - fake endpoint fixture/server
   - check command
   - one failure scenario
   - diagnose/heal/verify/report
   - manual verification commands
3. Run the manual verification commands.
4. Add the remaining classic breaks.
5. Run the manual verification commands.
6. Try to break it:
   - malformed configs
   - invalid provider output
   - unknown recipes
   - path traversal
   - missing files
   - wrong endpoint ports
   - repeated heal calls
   - already-healthy state
   - concurrent or repeated report generation
7. Fix every failure that indicates a real defect.
8. Refactor for provider agnosticism and clean boundaries.
9. Run the full manual verification loop again.
10. Do a code-review pass focused on correctness, safety, maintainability, and missing manual gates.
11. Fix all blocking or important findings.
12. Repeat the review/test/fix loop until:
    - all required manual gates pass
    - all classic break scenarios heal or fail safely as designed
    - unsafe model/provider outputs are rejected
    - no optional paid/cloud dependency is required for default tests
    - docs are updated
    - final review finds no blocking issues

Architecture guidance:

- Keep the core harness provider-agnostic.
- Keep OpenAI/Codex behind an adapter.
- Keep fake endpoint and fixtures separate from production code.
- Keep the executor separate from diagnosis/planning.
- Keep recipe definitions explicit and auditable.
- Make reports deterministic enough to test.
- Prefer simple data models over hidden global state.
- Avoid hard-coding one model runtime into the core.
- Do not require AMD Developer Cloud for local success.
- Do not require Ollama for default tests.

OpenAI/Codex provider guidance:

- Implement only after the rules provider and all local failure scenarios work.
- Use the OpenAI Responses API with structured outputs.
- Target gpt-5.3-codex if available through the configured account.
- The provider returns DiagnosisResult and RepairPlan only.
- Skip tests cleanly when OPENAI_API_KEY is missing.
- Never put API keys in files, logs, reports, fixtures, snapshots, or test output.

Documentation requirements:

- Update README.md with the actual commands.
- Update docs/demo-runbook.md with the working local demo flow.
- Update docs/local-tiny-model-testing.md if Ollama/qwen behavior changes.
- Update docs/self-healing-research-and-codex-provider.md if provider contracts change.
- Add a short troubleshooting section for common local failures.

Final response requirements:

When complete, report:

- what was implemented
- how the architecture is organized
- which failures were injected and healed
- which safety gates were tested
- exact verification commands run and results
- remaining limitations, especially anything requiring AMD cloud, Ollama, OpenAI API, or real vLLM

Do not claim perfection. Claim only that the acceptance gates passed.
```
