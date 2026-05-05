# Project Plan

ROCm Doctor is an agentic reliability harness that watches an AI agent stack running on AMD GPUs, detects failures, diagnoses root causes, applies safe repairs, and verifies that the system is healthy again.

The project is designed for Track 1 of the AMD Developer Hackathon: AI Agents and Agentic Workflows. It is not just a chatbot or RAG app. It is a coordinated multi-agent system that performs real operational work around a live model-serving and agent runtime.

## Problem

Running open-source models and agent frameworks on GPU infrastructure is powerful, but brittle. A small configuration issue can break the whole workflow:

- vLLM fails to start.
- The selected model does not fit memory.
- ROCm Docker flags are wrong.
- GPU devices are not mounted into the container.
- The model endpoint is alive but tool calling is broken.
- Context length settings cause crashes or severe latency.
- An agent tool schema changes and downstream calls fail.
- A runaway process consumes GPU memory.

These failures are especially painful during hackathons, demos, and early production experiments. Developers need more than logs. They need a system that can observe, reason, repair, and prove the fix worked.

## Solution

ROCm Doctor wraps a model-serving and agent runtime with a self-healing control loop:

1. Observe the system.
2. Detect failure symptoms.
3. Collect logs, metrics, configs, and endpoint responses.
4. Diagnose the most likely root cause.
5. Propose a repair plan.
6. Apply safe repairs.
7. Restart or reconfigure the affected component.
8. Rerun health checks and agent task tests.
9. Produce an incident report with evidence.

The harness can run locally against a remote AMD Developer Cloud instance or directly on the GPU VM.

This follows the classic MAPE-K shape from autonomic/self-healing systems:

- Monitor: collect endpoint, runtime, log, process, config, and GPU evidence.
- Analyze: classify the failure and identify likely root cause.
- Plan: choose a bounded repair recipe.
- Execute: apply the approved repair.
- Knowledge: retain run history, known failure signatures, safe recipes, and verification evidence.

For the MVP, LLMs are allowed to help with Analyze and Plan. They are not allowed to execute arbitrary shell commands. Execution stays inside deterministic recipes that the harness owns.

## Agent Architecture

### Observer Agent

Monitors the system and collects signals:

- vLLM `/v1/models` availability
- OpenAI-compatible chat completion checks
- Tool-calling test results
- Docker container state
- Process state
- GPU memory and utilization
- Recent logs
- Config files

### Diagnosis Agent

Classifies failure modes from evidence:

- Startup failure
- Endpoint failure
- Model loading failure
- GPU memory failure
- Docker/ROCm device issue
- Tool-calling issue
- Performance regression
- Agent framework error

The MVP should implement a rule-based diagnosis path first. A Codex/OpenAI provider can then be added as an optional second opinion that returns the same structured diagnosis schema.

### Repair Planner Agent

Turns diagnosis into a concrete repair plan:

- Change vLLM launch arguments.
- Lower max model length.
- Switch to a smaller model.
- Add ROCm Docker device flags.
- Restart the serving process.
- Kill runaway GPU processes.
- Patch agent tool schemas.
- Update endpoint configuration.

The repair planner may use a Codex/OpenAI provider to explain a repair and select a recipe, but the selected recipe must be one of the harness's known safe actions.

### Executor Agent

Applies approved repairs through shell, Docker, config edits, or service restarts.

The MVP should keep destructive operations gated and reversible. For demo purposes, repairs can be limited to known config files and known test containers.

The executor should reject free-form commands from any model provider. It should accept only typed repair recipes such as `update_endpoint_url`, `lower_max_model_len`, `set_tool_parser`, or `restart_known_service`.

### Verifier Agent

Runs checks after every repair:

- Model endpoint responds.
- Chat completion works.
- Tool call is parsed correctly.
- Agent completes a representative task.
- GPU memory is within expected range.
- Latency is under a configured threshold.

### Report Agent

Writes a human-readable incident record:

- What broke
- What evidence was found
- What repair was applied
- Whether verification passed
- What a developer should change permanently

## MVP Scope

The first version should support a narrow but impressive set of failures around vLLM on AMD Developer Cloud.

### Must Have

- Health check runner for a vLLM OpenAI-compatible endpoint.
- Simple CLI showing system health.
- Failure injection scripts for repeatable demos.
- Log collector for Docker/vLLM output.
- Rule-based diagnosis for at least three failure classes.
- Automated repair for at least two failure classes through deterministic recipes.
- Verification loop after repair.
- Generated incident report.
- Provider interface with `rules` as the default provider and `openai-codex` as an optional provider.
- Structured diagnosis and repair-plan schemas shared by all providers.

### Nice To Have

- Streamlit demo UI.
- GPU metrics dashboard.
- Before/after performance comparison.
- Browser-based demo timeline.
- Config diff viewer.
- Human approval mode for repairs.
- Exportable run report for hackathon submission.
- Codex/OpenAI provider confidence comparison against the rule-based provider.

## Initial Failure Scenarios

### Scenario 1: Wrong Endpoint Port

Symptom:

- Agent cannot reach the model endpoint.

Diagnosis:

- vLLM is running, but the configured base URL uses the wrong port.

Repair:

- Update agent config to the active endpoint.

Verification:

- Run `/v1/models` check and one chat completion.

### Scenario 2: Context Length Too Large

Symptom:

- vLLM crashes or fails to allocate memory.

Diagnosis:

- Launch args request a max model length too large for the selected model/runtime budget.

Repair:

- Lower `--max-model-len` to a known safe value.

Verification:

- Restart vLLM and run smoke prompts.

### Scenario 3: Missing ROCm Docker Device Flags

Symptom:

- Container starts but cannot access AMD GPU devices.

Diagnosis:

- Docker launch command is missing `/dev/kfd`, `/dev/dri`, or video group access.

Repair:

- Relaunch container with the required ROCm device flags.

Verification:

- Check GPU visibility and model load.

### Scenario 4: Tool Calling Parser Misconfigured

Symptom:

- Model responds, but agent tool calls fail or arrive as plain text.

Diagnosis:

- vLLM was launched without the right tool-calling flags or parser for the selected model.

Repair:

- Restart vLLM with model-appropriate tool-calling settings.

Verification:

- Run a deterministic tool-call test.

## Proposed Tech Stack

- AMD Developer Cloud
- AMD Instinct MI300X GPU
- ROCm
- Docker
- vLLM
- `qwen3:0.6b` for local tiny-model testing
- Qwen, Llama, Mistral, or DeepSeek model for AMD/vLLM validation if needed
- Python
- FastAPI for the harness API
- OpenAI Responses API for optional Codex-backed diagnosis and repair planning
- `gpt-5.3-codex` as the optional Codex provider model for code/config-aware reasoning
- React or Streamlit for the demo UI
- LangGraph, CrewAI, AutoGen, or a lightweight custom agent graph

## Provider Architecture

ROCm Doctor should treat model access as a provider boundary:

- `rules`: default, deterministic, no network, no API key.
- `fake`: deterministic model endpoint for harness development.
- `ollama-qwen`: local `qwen3:0.6b` endpoint for OpenAI-compatible model validation.
- `openai-codex`: optional OpenAI Responses API provider using `gpt-5.3-codex` for structured diagnosis and repair planning.
- `vllm-amd`: AMD Developer Cloud vLLM endpoint for the final ROCm proof.

Runtime behavior should be described by config profiles. A profile declares the endpoint protocol, runtime type, model name, health probes, capability flags, known failure signatures, and safe repair recipes. This keeps the core harness model/runtime agnostic: Qwen/Ollama, fake OpenAI-compatible endpoints, and AMD/vLLM differ by profile data rather than separate control loops.

The provider contract should return typed objects, not prose:

- `DiagnosisResult`: failure class, confidence, evidence, suspected cause, missing evidence, recommended recipe ids.
- `RepairPlan`: selected recipe id, rationale, config patch, command preview if applicable, risk level, rollback notes, verification steps.

The CLI should expose this as:

```bash
rocm-doctor diagnose --provider rules
rocm-doctor diagnose --provider openai-codex
rocm-doctor heal --provider rules
```

For MVP safety, `heal` should use provider output only to select among known recipes. Free-form command execution is out of scope.

## Why AMD Matters

ROCm Doctor is built around the developer experience of running open-source AI workloads on AMD GPUs. The harness directly exercises the AMD stack:

- Serves open-source models on AMD Instinct GPUs.
- Uses ROCm-compatible vLLM containers.
- Monitors GPU runtime behavior.
- Captures real issues developers hit when deploying on AMD Developer Cloud.
- Produces actionable feedback for improving AMD AI developer workflows.

This makes the project useful as both a hackathon submission and practical developer tooling.

## Judging Alignment

### Application Of Technology

The project uses open-source models, agent orchestration, vLLM, ROCm, and AMD Developer Cloud in a real operational workflow.

### Presentation

The demo has a clear story: a working agent breaks, ROCm Doctor diagnoses the issue, applies a repair, and proves recovery.

### Business Value

Reliable AI infrastructure is a practical need for developers and companies deploying agents. A self-healing harness can reduce debugging time, improve demo reliability, and make AMD GPU adoption easier.

### Originality

Most hackathon projects build an agent that completes a user task. ROCm Doctor builds an agent that keeps other agents alive.

## Build Plan

### Phase 1: Harness Skeleton

- Define a local config format for model endpoint, container name, launch command, and test prompts.
- Implement health checks.
- Implement a CLI command: `rocm-doctor check`.
- Store each run as structured JSON.
- Define `DiagnosisResult` and `RepairPlan` schemas.
- Define the provider interface with `rules` as the first implementation.

### Phase 2: Failure Detection

- Add log collection.
- Add GPU/process inspection.
- Add failure classifiers for the first three scenarios.
- Implement `rocm-doctor diagnose`.
- Add `openai-codex` provider as an optional diagnosis backend using the same schemas.

### Phase 3: Repair Loop

- Implement safe config patching.
- Add known repair recipes.
- Implement `rocm-doctor heal`.
- Require confirmation before shell-level changes unless demo mode is enabled.
- Reject model-suggested commands unless they map to a known recipe.
- Add verification evidence to the run report.

### Phase 4: Demo UI

- Show health status.
- Show failure timeline.
- Show diagnosis and repair plan.
- Show verification result.
- Show generated incident report.

### Phase 5: Hackathon Polish

- Add repeatable failure injection scripts.
- Record demo video.
- Publish GitHub repo.
- Deploy or document the AMD Developer Cloud setup.
- Write technical walkthrough and AMD developer feedback.
- Show the judge two provider modes: local deterministic repair and optional Codex-backed diagnosis/planning.
