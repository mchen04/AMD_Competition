# CI/CD Mode

ROCm Doctor's CI/CD mode is the supervised loop your model deployment runs *inside*. It pins a known-good baseline, then continuously checks the deployment, decides whether breakages are operator-driven or accidental, and only auto-heals the accidental ones.

This doc explains the four pieces and walks through the canonical demo.

## The four pieces

1. **Pinned baseline** — the operator-blessed config snapshot. `rocm_doctor pin-baseline` writes it into `state.json` under `pinned_baseline_config`. Auto-snapshots (`last_known_good_config`) keep updating on every healthy probe; the pin only changes when the operator says so.
2. **Continuous supervisor** — `rocm_doctor supervise` runs `check → diagnose → classify intent → heal → verify` on a fixed cadence forever. With `--until-pass` it raises the per-cycle heal `max_attempts` to effectively unbounded so a stubborn drift gets every recipe in the safe list before giving up.
3. **Intent classifier** — between diagnosis and planning, the brain (or the rules-engine fallback) sees the evidence bundle, the diagnosis, the diff between current config and pinned baseline, and the recent activity log. It returns `{intent, confidence, reasoning, recommend_action}`. `recommend_action` drives the loop:
   - `heal` → run the candidate-recipe loop as before.
   - `record_only` → write the intent stage to `state.json`, do not heal, sleep the *intent-skip cooldown* (default 5 min) so we don't spam the same conclusion every interval.
   - `ask_human` → same skip behaviour; the dashboard surfaces these so a human can decide.
4. **Recipe loop** — unchanged. 18 deterministic recipes, executor allowlist, snapshot+rollback. The CI/CD layer adds *when* to run them, not *what* they do.

## Sequence

```
┌────────────┐    ┌─────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│ supervisor │ →  │ monitor │ →  │ diagnosis │ →  │  intent  │ →  │ executor │ →  │ verify  │
└──────┬─────┘    └─────────┘    └───────────┘    └─────┬────┘    └──────────┘    └─────────┘
       │                                                │
       │              record_only / ask_human          │
       │  ┌─────────────────────────────────────────────┘
       │  │
       ▼  ▼
   intent-skip cooldown (default 5m); next cycle
```

The intent classifier *only fires when probes fail* — a healthy cycle exits at the monitor step, calls `record_last_known_good_config`, and waits for the interval.

## Decision rule (rules-engine fallback)

The deterministic fallback used when no LLM brain is configured (or the configured one errors):

1. **Empty diff** → `unintentional → heal`. Probes failed but nothing in the config changed, so this is external drift (transient 5xx, network blip, missing ROCm flag).
2. **Diff entirely inside the recipe allowlist** → `unintentional → heal`. The change is something one of our 18 recipes is built to fix; healing reverts that path.
3. **Diff touches paths outside the allowlist** → `intentional → record_only`. The operator edited something we don't understand — auto-healing would erase deliberate work. Record and wait.

LLM brains use the richer prompt in `templates/intent_classifier_system.j2` and may distinguish more shades (e.g. "timeout bumped to 30s is operator tuning even though the path is allowlisted"). Whatever they return is validated against `INTENT_CLASSIFIER_JSON_SCHEMA`; on any error we fall through to the rules engine. Intent is advisory; no LLM hiccup can block a heal.

## Canonical demo

```bash
cp demo/rocm-doctor.yaml /tmp/rocm-doctor-demo.yaml
python -m rocm_doctor fake-endpoint --port 8000 &       # terminal 1

# Pin a healthy baseline.
python -m rocm_doctor check        --config /tmp/rocm-doctor-demo.yaml
python -m rocm_doctor pin-baseline --config /tmp/rocm-doctor-demo.yaml

# Start the supervisor.
python -m rocm_doctor supervise --config /tmp/rocm-doctor-demo.yaml --interval 5 --until-pass &

# 1. INTENTIONAL change: edit a path outside the recipe allowlist.
yq -i '.hardware.deployment_target = "cluster-mi300x-ord1"' /tmp/rocm-doctor-demo.yaml
# → next cycle: intent reports `intentional → record_only`, heal skipped.

# 2. UNINTENTIONAL drift: a known failure inside the allowlist.
python -m rocm_doctor inject-failure wrong_endpoint_port --config /tmp/rocm-doctor-demo.yaml
# → next cycle: intent reports `unintentional → heal`, recipe `update_endpoint_url`
#   reverts the URL, verify passes, supervisor goes back to idle.
```

## Dashboard

The Vite/React console (`rocm_doctor dashboard`) wires these primitives directly:

- **Baseline strip** on Overview — pin/unpin/restore + a live diff view.
- **Supervisor panel** on Overview — start/stop with interval and `until-pass`, plus a live SSE log of cycle events.
- **Intent column** on Incidents — shows the latest classification badge (`unintentional → healed`, `intentional → recorded`, or `uncertain → human`) plus the reasoning string.

## Failure modes the supervisor handles

The supervisor doesn't add new failure modes — it adds a *cadence* and an *intent gate* on top of the existing 18-recipe loop. Specifically:

- **Drift you'd want auto-fixed**: dropped endpoint, transient timeout, expired token in the prompt, oversized context, missing ROCm device flag.
- **Operator changes you'd want left alone**: bumping `request.timeout_seconds`, switching `active_model_provider`, swapping `model.id`, editing hardware metadata.
- **Ambiguous changes**: surfaced as `ask_human` events on the dashboard rather than auto-healed.

## Cooldowns

Defined in the `supervision:` block (see `defaults.yaml`):

```yaml
supervision:
  enabled: false                   # whether the dashboard auto-starts the loop
  interval_seconds: 30             # cadence between cycles
  until_pass: false                # raise per-cycle max_attempts to ~unbounded
  cooldown_seconds_after_heal: 60  # back off after a successful repair
  cooldown_seconds_after_intent_skip: 300  # back off when intent says don't heal
```

The cooldowns matter for two reasons. (a) After a heal, verification can lag behind the underlying runtime — re-running 5s later risks a false-positive failure. (b) When intent says `record_only`, we don't want the supervisor to keep classifying the same operator change every 30s; we want one record per change.
