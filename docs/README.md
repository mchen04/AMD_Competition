# ROCm Doctor Docs

This folder keeps the project documentation split by use case so the root README can stay short.

## Start Here

- [Project Plan](project-plan.md): concept, architecture, MVP scope, failure scenarios, judging alignment, and build phases.
- [Self-Healing Research And Codex Provider Plan](self-healing-research-and-codex-provider.md): research synthesis, provider architecture, and concrete MVP decisions.
- [Implementation Agent Prompt](implementation-agent-prompt.md): reusable build prompt for implementing, breaking, testing, refactoring, and hardening the MVP.
- [Model-Agnostic Qwen + Codex Validation Agent Prompt](model-agnostic-qwen-codex-agent-prompt.md): next-phase prompt for validating the harness against tiny Qwen and optional Codex planning while keeping the core runtime/model agnostic.
- [Local Tiny Model Testing](local-tiny-model-testing.md): how to exercise the OpenAI-compatible loop without AMD cloud access.
- [AMD Developer Cloud Setup](amd-developer-cloud-setup.md): DigitalOcean/AMD console checklist, GPU Droplet creation guidance, and cost controls.
- [Demo Runbook](demo-runbook.md): the repeatable hackathon demo flow.
- [Submission Checklist](submission-checklist.md): lablab submission fields, repo/demo/video requirements, and final polish.

## Working Rule

Do not start a GPU Droplet until the local demo loop is runnable and AMD credits are visible. GPU Droplets continue billing while powered off; destroy them when the validation window is over.

## Current Local Command Surface

The MVP package can be run without installation from the repo root:

```bash
python3 -m rocm_doctor check --config demo/rocm-doctor.json
python3 -m rocm_doctor diagnose --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor heal --provider rules --config demo/rocm-doctor.json
python3 -m rocm_doctor verify --config demo/rocm-doctor.json
python3 -m rocm_doctor report --config demo/rocm-doctor.json
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/rocm-doctor.json
python3 -m rocm_doctor fake-endpoint --port 8000
```

Run the fake endpoint in one terminal and the command loop in another for manual local verification.

The optional real tiny-model config is `demo/ollama-qwen.json`. It uses the `ollama-qwen` runtime profile and should be run only when Ollama is serving `qwen3:0.6b`:

```bash
python3 -m rocm_doctor check --config demo/ollama-qwen.json
python3 -m rocm_doctor inject-failure wrong_endpoint_port --config demo/ollama-qwen.json
python3 -m rocm_doctor diagnose --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor heal --provider rules --config demo/ollama-qwen.json
python3 -m rocm_doctor verify --config demo/ollama-qwen.json
```

Paid OpenAI/Codex validation is manual and opt-in:

```bash
python3 -m rocm_doctor diagnose --provider openai-codex --config demo/rocm-doctor.json
python3 -m rocm_doctor heal --provider openai-codex --config demo/rocm-doctor.json
```
