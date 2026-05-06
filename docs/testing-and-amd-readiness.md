# Testing and AMD Readiness

## Validation Gate

```bash
scripts/local_validate.sh
```

Creates/reuses `/tmp/rocm-doctor-venv`, installs `'.[test]'`, runs `compileall` + `pytest`, exercises the fake-endpoint demo on a copied config, generates a report, and runs the real-Qwen suite when Ollama is serving `qwen3:0.6b`.

Manual equivalent:

```bash
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
/tmp/rocm-doctor-venv/bin/python -m compileall rocm_doctor tests
/tmp/rocm-doctor-venv/bin/python -m pytest -q
```

Latest local status (no AMD credits): deterministic suite passes, real-Qwen suite passes, fake-endpoint demo + report path passes. AMD MI300X/vLLM path pending GPU credits.

## Coverage

The pytest suite uses real in-process HTTP, not mocks, against the OpenAI-compatible adapter for `qwen3:0.6b`, `smollm2:135m`, `tinyllama:1.1b`.

**Failure modes covered:** malformed JSON, empty response, empty chat content, partial response, HTTP 500, HTTP 429 (one-time + repeated), timeout, retry recovery, retry exhaustion, context-length failure, tool-call parser mismatch, wrong tool name, hallucinated tool call, instruction drift, streaming interruption, repetitive output, corrupted state, invalid config, bad template, unknown recipe, unsafe command, path traversal, credential edit.

**Self-heal flows asserted end-to-end:** retry-only recovery, `health_max_tokens` tuning, timeout tuning, streaming disablement, prompt-template fallback, fallback-provider switching, rollback after failed repair, learned-fix state recording.

**Report path:** generated reports include diagnosis, repair recipe, verification status, before/after evidence.

## Real-Qwen Adversarial Suite

```bash
ROCM_DOCTOR_RUN_REAL_QWEN=1 \
  /tmp/rocm-doctor-venv/bin/python -m pytest tests/test_real_qwen_adversarial.py -q -s
```

Adversarial proxy fronts local Ollama. Healthy requests forward to `qwen3:0.6b`; transport/protocol failures inject at the proxy boundary; prompt-level probes are answered by the real model. Healing loops covered: empty chat content, slow response, broken streaming, bad endpoint recovery.

The proxy can also be run manually:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor adversarial-proxy \
  --upstream-base-url http://127.0.0.1:11434/v1 \
  --failure-mode chat_invalid_json
```

## Tiny-Model Behavior

`demo/ollama-tiny-models.yaml` ships profiles for `qwen3:0.6b`, `smollm2:135m`, `tinyllama:1.1b`. Switch `active_model_provider` to test each.

| Model | Behavior |
|---|---|
| `qwen3:0.6b` | Passes direct health checks and the real-Qwen adversarial suite. |
| `smollm2:135m` | Reachable; fails strict health by returning long explanatory text instead of `ROCM_DOCTOR_OK`. |
| `tinyllama:1.1b` | Reachable; fails strict health by returning prose around the sentinel. |

The two smaller profiles are negative controls — evidence that the harness rejects weak instruction-following instead of accepting any response containing the sentinel.

### Tiny-Model Tuning

- Keep health prompts short and exact; keep `temperature: 0` in adapter probes.
- Disable native tool-call checks unless the runtime emits them reliably.
- Use smaller `model.context.max_tokens` and conservative `safe_max_tokens`.
- Tune `validation.health_max_tokens` (Qwen needs more headroom because Ollama reports reasoning separately).
- Set `validation.health_response_match: case_insensitive` for Qwen casing drift.
- Configure `templates.health_chat_fallbacks` so drift/loops/empty-output can switch prompts without Python edits.
- Increase `request.timeout_seconds` for CPU-bound Ollama runs.
- Use repeated-output and max-response validation to catch weak reasoning loops.

If a weak model fails with overlong output, treat it as a failed provider profile rather than relaxing validation.

## Chaos Suite

Opt-in pre-merge gate that drives detect → heal → verify across deterministic, real-Qwen, and brain-matrix paths. The default fast path stays at ~30s; chaos runs are gated:

```bash
CHAOS=1 ./scripts/local_validate.sh
```

This runs `scripts/chaos_full.sh`, which aggregates five layers and writes `docs/chaos-report-<date>.md`:

1. **Layer 1 — Deterministic chaos pytests** (no external services).
   - `tests/test_chaos_fake_endpoint.py` — randomized 50-round sweep across real + safety scenarios; healed scenarios end on the expected recipe id, safety scenarios produce `repair.rejected=True` with the config unchanged.
   - `tests/test_chained_failures.py` — sequential injection of `wrong_endpoint_port` → `context_length_too_large` → `wrong_endpoint_port`; checks recipe-per-failure correctness and that learned-fix entries persist across heals.
   - `tests/test_learned_fix_replay.py` — repeats the same incident 3× and asserts `result.attempts == 1` by round 3 (learned fix is tried first and succeeds).
   - `tests/test_sequence_chaos.py` — drives a streaming-timeout that single-recipe heal can't cleanly fix; asserts `result.applied_recipe_ids == ["increase_timeout", "disable_streaming"]` and that verification heals.

2. **Layer 2 — Adversarial-proxy heal-cycle sweep against real Ollama** (`scripts/chaos_qwen.sh`).
   - Walks all 16 modes in `adversarial_proxy.ADVERSARIAL_FAILURE_MODES`; runs self-heal + verify for each; emits `docs/stress-test-screens/chaos-qwen.md` and per-mode JSON under `docs/stress-test-screens/runs/chaos-qwen-<mode>.json`.
   - Skips cleanly if `ollama` is not on `$PATH` or `127.0.0.1:11434/v1/models` is unreachable.

3. **Layer 3 — Two-brain stress matrix run** (`scripts/stress_matrix.sh`).
   - Drives the dashboard `/api/run` matrix across providers × scenarios. Default `PROVIDERS` is `"rules openai-codex anthropic openai-compatible"`; for chaos validation runs override to the brains with keys actually present:

   ```bash
   OPENAI_API_KEY=... \
     PROVIDERS="rules openai-codex" \
     scripts/stress_matrix.sh
   ```

   - Anthropic and OpenRouter are explicitly excluded (rather than emitted as `no_attempt` rows) so the markdown reflects the actual scope of the run. Re-add them to `PROVIDERS` (and set `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY`) when keys are available.

4. **Layer 4 — Aggregate gate** (`scripts/chaos_full.sh`). Runs Layers 1–3 + Layer 5, writes a per-layer pass/fail summary to `docs/chaos-report-<date>.md`, exits non-zero if any layer fails.

5. **Layer 5 — Supervisor stability soak** (`scripts/chaos_supervisor.py`). 100 cycles of randomized real-scenario injection through `self_heal_config`, with time-to-heal and attempts-per-heal tracking. Pass criteria: 100% of injected scenarios heal; mean attempts ≤ 1.5 by round 50.

### Env vars used by the chaos scripts

| Var | Used by | Default | Purpose |
|---|---|---|---|
| `CHAOS` | `local_validate.sh` | unset | When `=1`, run `chaos_full.sh` after the standard checks |
| `PROVIDERS` | `stress_matrix.sh` | `rules openai-codex anthropic openai-compatible` | Whitespace-separated provider list to drive |
| `OPENAI_API_KEY` | `stress_matrix.sh` (codex) | unset | Required for the `openai-codex` row |
| `ANTHROPIC_API_KEY` | `stress_matrix.sh` (anthropic) | unset | Required for the `anthropic` row |
| `OPENROUTER_API_KEY` | `stress_matrix.sh` (openai-compatible) | unset | Required for the `openai-compatible` row |
| `OLLAMA_BASE_URL` | `chaos_qwen.sh` | `http://127.0.0.1:11434/v1` | Upstream OpenAI-compatible base for the adversarial proxy |
| `QWEN_MODEL_ID` | `chaos_qwen.sh` | `qwen3:0.6b` | Model id served by Ollama |
| `PROXY_PORT` | `chaos_qwen.sh` | `8001` | Port the adversarial proxy listens on |
| `OUT_DIR` | `chaos_qwen.sh` / `stress_matrix.sh` | `docs/stress-test-screens` | Where markdown + per-run JSON land |
| `PYTHON_BIN` | `chaos_qwen.sh` / `chaos_supervisor.py` | `/tmp/rocm-doctor-venv/bin/python` | Interpreter used to drive the harness |

## AMD Hooks

Everything AMD-specific is YAML-controlled:

- `hardware.{backend, accelerator, runtime}`, `hardware.amd.benchmark_profile`
- `launch.{device_flags, required_device_flags}`
- `model_providers.<id>.runtime_type`
- endpoint URL, context limits, request timeout, retry policy, streaming flag
- safe repair recipes and health probes

Remaining work is real MI300X/vLLM validation: add a `model_providers` entry pointing at the deployed vLLM endpoint, set ROCm device flags, tune context for the served model, run the same scenarios listed in [demo-runbook.md](demo-runbook.md). See [amd-developer-cloud-setup.md](amd-developer-cloud-setup.md) for droplet setup.
