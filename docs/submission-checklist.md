# Submission Checklist

## Metadata

- **Title:** ROCm Doctor
- **Description:** Self-healing supervisor for self-hosted, OpenAI-compatible model endpoints on AMD Developer Cloud.
- **Track:** AI Agents and Agentic Workflows

## Required Links

- Public GitHub repo
- Demo URL or setup instructions
- Demo video (≤3 min)
- Optional: slide deck, final incident report

## Repo Readiness

- [ ] Top-level README explains the project in under one minute.
- [ ] `scripts/local_validate.sh` passes.
- [ ] `docs/` describes setup, demo, architecture, testing.
- [ ] Local demo runs without AMD credits.
- [ ] Failure injection scenarios are repeatable from CLI and dashboard.
- [ ] Reports include diagnosis, repair, verification, and before/after evidence.

## Demo Video Outline

1. Title + one-sentence purpose.
2. Healthy check against fake endpoint or real `qwen3:0.6b`.
3. Inject one controlled failure.
4. Show diagnosis (rules brain) → highlight failure class.
5. Optional: switch to an LLM brain (`codex-cli` / `anthropic` / `openai-compatible`) and show same evidence parsed.
6. Run repair through deterministic recipe.
7. Run verification.
8. Open the incident report.
9. Close on AMD MI300X evidence (or state explicitly that local Qwen + fake endpoint validated, MI300X pending credits).

## Key Talking Points

- Diagnosis is pluggable; repair execution is not.
- 18 audited recipes, 13 failure classes, allowlisted YAML edits only.
- LLM brains can sequence recipes or emit bounded patches; executor still rejects unsafe paths/types/credentials.
- Adversarial proxy injects 16 transport/protocol failures against a real backend.
- Learned-fixes memory keys repeat incidents to known-good recipes.

## If AMD Credits Are Unavailable

State explicitly in the submission: local fake-endpoint demo, real local Qwen adversarial suite, and multi-brain stress test (see [stress-test-report-2026-05-06.md](stress-test-report-2026-05-06.md)) all pass. MI300X/vLLM remains the final cloud proof.
