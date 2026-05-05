# Self-Healing Research And Codex Provider Plan

This note turns the self-healing research into concrete MVP decisions for ROCm Doctor.

## Research Synthesis

### MAPE-K Is The Right Base Shape

Classic autonomic and self-healing systems use a closed feedback loop: Monitor, Analyze, Plan, Execute, with shared Knowledge. ROCm Doctor maps cleanly to that:

- Monitor: endpoint checks, Docker/process state, logs, config, GPU state
- Analyze: failure classification and root-cause hypothesis
- Plan: select a repair recipe
- Execute: patch config, restart known service, or relaunch known container
- Knowledge: failure signatures, safe recipes, run history, verification results

MVP implication: do not build a loose chatbot. Build a stateful control loop with typed stages and explicit transition rules.

### Failure Injection Matters

Self-healing system evaluation depends on controlled and reproducible failure traces, because real failures are rare and hard to reproduce. ROCm Doctor should ship with deterministic failure injection scripts before it claims self-healing behavior.

MVP implication: the first demo should inject wrong endpoint port, unsafe context length, and tool-parser mismatch. The report should include before/after evidence.

### AI Helps Most In Analyze And Plan

Recent agent-repair work points toward agent loops that gather evidence, propose fixes, critique them, and validate results. The strongest pattern is not "let the model do anything"; it is "give the model evidence and tools, then force validation."

MVP implication: use AI for diagnosis and repair planning, but keep execution inside known recipes and always run verification afterward.

### Harnesses Beat Raw Model Calls

Agent-harness research shows that a well-designed harness can prevent illegal or unsafe actions and make smaller models more useful. For ROCm Doctor, the harness is the product: the model provider is replaceable.

MVP implication: provider output must be structured and checked against schemas. The executor must reject unknown actions.

## Codex/OpenAI Provider Plan

The "Codex provider" should be an optional OpenAI API backend, not the whole system.

Use the OpenAI Responses API with a coding-oriented model for code/config-aware diagnosis and repair planning. Current OpenAI docs describe the Responses API as the recommended primitive for new agent-like applications, with tool use, state, function calling, and structured outputs. OpenAI's GPT-5.3-Codex model is described as optimized for agentic coding tasks in Codex or similar environments and supports the Responses endpoint, function calling, and structured outputs.

### Provider Boundary

Implement model access behind a provider interface:

```text
rules
fake
ollama-qwen
openai-codex
vllm-amd
```

The default path is `rules` because it is deterministic and free. `openai-codex` is used when `OPENAI_API_KEY` is set and the user passes `--provider openai-codex`.

### Structured Outputs

Every provider should return the same typed objects.

`DiagnosisResult`:

```json
{
  "failure_class": "endpoint_unreachable",
  "confidence": 0.92,
  "evidence": ["GET /v1/models failed on port 8001", "configured endpoint is http://localhost:8001"],
  "suspected_cause": "Configured endpoint port does not match running server.",
  "missing_evidence": [],
  "recommended_recipe_ids": ["update_endpoint_url"]
}
```

`RepairPlan`:

```json
{
  "recipe_id": "update_endpoint_url",
  "rationale": "The configured endpoint points to a closed port while the model server is reachable on the expected demo port.",
  "config_patch": {
    "path": "rocm-doctor.yaml",
    "changes": {
      "model.base_url": "http://localhost:8000/v1"
    }
  },
  "command_preview": [],
  "risk_level": "low",
  "rollback": "Restore the previous model.base_url value.",
  "verification_steps": ["GET /v1/models", "POST /v1/chat/completions"]
}
```

### Execution Safety

The OpenAI/Codex provider must not execute shell commands directly in the MVP.

Allowed:

- classify failure
- explain likely cause
- choose from known repair recipes
- generate a config patch that the harness validates
- suggest verification steps from a known list

Disallowed:

- free-form shell execution
- arbitrary file edits
- package installation
- deleting containers or data
- opening network ports
- modifying credentials

## MVP Goal Update

MVP success means:

1. `rocm-doctor check` detects healthy and broken endpoints.
2. `rocm-doctor diagnose --provider rules` returns a structured diagnosis for three failure classes.
3. `rocm-doctor diagnose --provider openai-codex` can return the same structured schema from evidence, when an OpenAI API key is available.
4. `rocm-doctor heal` applies only known deterministic recipes.
5. `rocm-doctor verify` proves the fix worked.
6. `rocm-doctor report` writes a before/after incident report.
7. The demo can run locally against a fake endpoint and `qwen3:0.6b`, then later swap to AMD Developer Cloud/vLLM.

## Implemented Provider Contract

The package exposes the provider boundary in `rocm_doctor.providers`.

- `rules`: default deterministic provider; no network, GPU, API key, Ollama, or AMD cloud required.
- `fake`: deterministic provider for local safety tests; can emit malformed schemas, unknown recipes, unsafe commands, path traversal, and credential edits.
- `openai-codex`: optional OpenAI Responses API adapter. It returns `provider_skipped` when `OPENAI_API_KEY` is absent.
- `ollama-qwen` and `vllm-amd`: delegating providers that preserve the provider boundary while endpoint behavior is driven by runtime profiles.

Runtime/model specificity lives in config profiles, not in the core control loop. The default `fake-openai` profile enables all deterministic local checks. The optional `ollama-qwen` profile targets `qwen3:0.6b` through Ollama's OpenAI-compatible API and declares that native tool-call and ROCm container checks should be skipped with clear reasons. A future `vllm-amd` profile can enable ROCm device checks and vLLM tool-parser checks without changing the Monitor/Analyze/Plan/Execute/Knowledge shape.

The OpenAI adapter uses Responses API structured outputs with JSON schemas for `DiagnosisResult` and `RepairPlan`. The executor still applies only known local recipes and revalidates the provider plan before writing anything.

Known deterministic recipes:

- `update_endpoint_url`
- `lower_max_model_len`
- `set_tool_parser`
- `set_rocm_device_flags`
- `restart_known_service` in dry-run/fake-service form only
- `noop`

Executor rejection rules:

- free-form command previews from provider output
- unknown recipe ids
- recipe ids not allowed by the active runtime profile
- recipes whose required profile capabilities are disabled
- provider patch paths outside the configured workspace
- patches to any file other than the active config
- credential/secret/token modifications
- edits outside the recipe's declared config paths
- provider values that differ from deterministic recipe output

## References

- MAPE-K and autonomic self-healing concepts: https://link.springer.com/article/10.1007/s11334-020-00361-8
- Self-healing evaluation and failure injection: https://www.mdpi.com/2073-431X/9/1/16
- SelfHeal multi-agent bug repair for LLM agents: https://arxiv.org/abs/2604.17699
- VIGIL reflective runtime for self-healing agents: https://arxiv.org/abs/2512.07094
- AutoHarness agent harness synthesis: https://arxiv.org/abs/2603.03329
- RepairAgent autonomous LLM-based program repair: https://arxiv.org/abs/2403.17134
- OpenAI Responses API migration guide: https://developers.openai.com/api/docs/guides/migrate-to-responses
- OpenAI tools guide: https://developers.openai.com/api/docs/guides/tools
- OpenAI Structured Outputs guide: https://developers.openai.com/api/docs/guides/structured-outputs
- GPT-5.3-Codex model docs: https://developers.openai.com/api/docs/models/gpt-5.3-codex
