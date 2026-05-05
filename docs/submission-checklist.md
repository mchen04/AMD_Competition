# Submission Checklist

Use this as the lablab submission prep list.

## Project Metadata

- Title: `ROCm Doctor`
- Short description: `An agentic self-healing harness that detects, diagnoses, repairs, and verifies failures in AI agent deployments running on AMD Developer Cloud.`
- Track: AI Agents and Agentic Workflows
- Team members confirmed on lablab
- Discord connected for the teammate who submits

## Required Links

- Public GitHub repo
- Demo URL or clear setup instructions
- Demo video
- Optional slide deck
- Optional final incident report artifact

## Repo Readiness

- Root README explains the project in under one minute.
- `docs/` contains setup, demo, and submission docs.
- Local demo can run without AMD GPU credits.
- AMD cloud setup is documented separately.
- Failure injection scripts are repeatable.
- Generated reports are saved under a predictable folder.

## Demo Video Outline

1. Show ROCm Doctor project title and one-sentence purpose.
2. Show a healthy model/agent check.
3. Inject one controlled failure.
4. Run diagnosis and highlight the root cause.
5. If available, show the same evidence through the optional Codex/OpenAI provider.
6. Run repair through deterministic recipes.
7. Run verification.
8. Show the incident report.
9. Close with why AMD Developer Cloud matters for the project.

## Final Polish

- Include screenshots of AMD Developer Cloud / MI300X evidence if available.
- Keep the video under three minutes unless rules allow more.
- Make the final report readable in plain English.
- Mention that the project targets real ROCm/vLLM deployment failure modes, not toy chatbot behavior.
- Make clear that diagnosis providers can classify and plan, while the harness controls execution and verification.
