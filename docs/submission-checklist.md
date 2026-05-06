# Submission Checklist

## Metadata

- **Title:** ROCm Doctor — Model CI/CD for AMD MI300X
- **Description:** Continuous CI/CD-style supervisor for self-hosted, OpenAI-compatible model endpoints on AMD Developer Cloud. Pins a known-good baseline, runs `check → diagnose → classify intent → heal → verify` continuously, and an LLM agent decides whether each break was an operator change (record only) or drift (heal until pass). Diagnosis is pluggable; repair is bounded by 18 audited recipes.
- **Track:** AI Agents and Agentic Workflows

## Required Links

- Public GitHub repo
- Demo URL or setup instructions
- Demo video (≤3 min)
- Optional: slide deck, final incident report

## Repo Readiness

- [x] Top-level README explains the project in under one minute. → [README.md](../README.md)
- [x] `scripts/local_validate.sh` passes. → [scripts/local_validate.sh](../scripts/local_validate.sh) (66 tests, full pass; `CHAOS=1` and `DEMO=1` extend the gate)
- [x] `docs/` describes setup, demo, architecture, testing. → [docs/amd-developer-cloud-setup.md](amd-developer-cloud-setup.md), [docs/demo-runbook.md](demo-runbook.md), [docs/provider-architecture.md](provider-architecture.md), [docs/testing-and-amd-readiness.md](testing-and-amd-readiness.md), [docs/ci-cd-mode.md](ci-cd-mode.md)
- [x] Local demo runs without AMD credits. → `bash scripts/amd_demo.sh --local` produces `evidence/0*.json|md|log` against the bundled fake endpoint.
- [x] Failure injection scenarios are repeatable from CLI and dashboard. → `rocm_doctor inject-failure <scenario>` (CLI) and the dashboard's Failure picker — 11 scenarios including `rocm_oom_inference` and `max_model_len_mismatch`.
- [x] Reports include diagnosis, repair, verification, and before/after evidence. → see `evidence/06-report.md` produced by `scripts/amd_demo.sh`.

## Demo Video Outline

1. Title + one-sentence purpose: *Model CI/CD for AMD MI300X.*
2. Healthy check against the deployment (fake endpoint or real `qwen3:0.6b`).
3. **Pin baseline.** Show the dashboard baseline strip flip from "not pinned" to "pinned just now".
4. **Start supervisor.** Show the live SSE event log on the Overview page.
5. **Intentional change** (e.g. `hardware.deployment_target = "cluster-mi300x-ord1"`). Watch the next cycle classify it as `intentional → record_only`. The supervisor does *not* heal. Show the badge on the Incidents page.
6. **Unintentional drift** via `inject-failure wrong_endpoint_port`. Watch the next cycle classify as `unintentional → heal`, run `update_endpoint_url`, and return healthy.
7. Optional: switch the diagnosis brain (`rules` → `codex-cli`/`anthropic`) and replay the drift scenario; same outcome via a different reasoner.
8. Open the incident report on the Incidents page; show the intent reasoning string.
9. Close on AMD MI300X evidence (or state explicitly that local Qwen + fake endpoint validated, MI300X pending credits).

## Key Talking Points

- **CI/CD framing.** Pin a baseline, supervise continuously, classify intent, heal until pass — the same shape as software CI/CD applied to model deployments.
- **Intent classifier.** A new step between diagnosis and repair: distinguishes operator changes from drift. LLM-driven with a deterministic rules-engine fallback so a brain hiccup never blocks a heal.
- **Continuous supervisor.** First-class CLI (`rocm_doctor supervise`), dashboard endpoints, SSE event stream. `--until-pass` raises the per-cycle heal cap to effectively unbounded.
- **Pinned baseline.** Operator-blessed snapshot, never auto-overwritten. The intent classifier diffs against it (falls back to last-known-good if no pin).
- **Diagnosis is pluggable; repair execution is not.** 18 audited recipes, 13 failure classes, allowlisted YAML edits only.
- **LLM brains can sequence recipes or emit bounded patches.** Executor still rejects unsafe paths/types/credentials.
- **Adversarial proxy** injects 16 transport/protocol failures against a real backend.
- **Learned-fixes memory** keys repeat incidents to known-good recipes.

## MI300X Demo Evidence

`bash scripts/amd_demo.sh --droplet` is the one command that produces every artifact below. Once it lands on a droplet, each box can be checked with the named path.

- [ ] `evidence/rocminfo-pre.txt` — `rocminfo` output captured by the script (proves ROCm visible).
- [ ] `evidence/amd-smi-pre.txt` and `evidence/amd-smi-post.txt` — GPU snapshots before & after the heal.
- [ ] `evidence/00-models.json` — `/v1/models` response from the served vLLM endpoint.
- [ ] `evidence/01-check-pre.json` — pre-flight health check (expected: healthy).
- [ ] `evidence/02-pin.json` — operator pinned the baseline.
- [ ] `evidence/03-supervise.log` — supervisor's newline-delimited SSE event log; must contain `"recovered": true` after the inject.
- [ ] `evidence/04-inject.json` — drift injection record.
- [ ] `evidence/05-restore.json` — baseline restored after the demo.
- [ ] `evidence/06-report.md` — final markdown incident report; ends with `Verification healthy: True`.
- [ ] Screen recording: pin baseline → injected drift → intent classified `unintentional` → heal → verify on the dashboard, ≤90s. Captured separately via `rocm_doctor dashboard --port 8765`.

## If AMD Credits Are Unavailable

Local proof points (all current):

- `scripts/local_validate.sh` — 66 unit tests + fake-endpoint demo + real-Qwen adversarial suite when Ollama is serving `qwen3:0.6b`.
- `bash scripts/amd_demo.sh --local` — produces the same `evidence/0*` artifact set as the droplet path, minus the GPU snapshots; run before recording the dashboard demo.
- Chaos suite: see [chaos-report-2026-05-06.md](chaos-report-2026-05-06.md) (5-layer stack, 100% heal rate).
- Multi-brain stress: see [stress-test-report-2026-05-06.md](stress-test-report-2026-05-06.md).

The new CI/CD layer (intent classifier + supervisor + pinned baseline + supervisor cycle history) is exercised end-to-end against the fake endpoint, with two new MI300X-specific recipes (`lower_gpu_memory_utilization` for HIP OOM and `align_max_tokens_with_served` for served context-length mismatch). MI300X/vLLM remains the final cloud proof.
