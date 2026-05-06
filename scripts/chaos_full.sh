#!/usr/bin/env bash
# Aggregate chaos gate.
#
# Runs all five layers of the chaos suite and exits non-zero if any layer fails:
#   1. Deterministic chaos pytests (no external services)
#   2. Adversarial-proxy heal-cycle sweep against real Ollama (skip if unavailable)
#   3. Two-brain stress matrix run (skip if dashboard or OPENAI_API_KEY missing)
#   4. (this script — aggregator)
#   5. Supervisor stability soak (Python, in-process)
#
# Writes a per-layer pass/fail summary to docs/chaos-report-<UTC date>.md.
#
# Usage:
#   scripts/chaos_full.sh
#
# Env knobs:
#   PYTHON_BIN      python interpreter (default: /tmp/rocm-doctor-venv/bin/python)
#   STRESS_PORT     dashboard port for Layer 3 (default: 8765)
#   STRESS_PROVIDERS  whitespace list passed as PROVIDERS (default: rules openai-codex)
#   CHAOS_CYCLES    supervisor cycle count (default: 100)
#   OUT_DIR         where Layer 2/3 markdown lands (default: docs/stress-test-screens)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-/tmp/rocm-doctor-venv/bin/python}"
STRESS_PORT="${STRESS_PORT:-8765}"
STRESS_PROVIDERS="${STRESS_PROVIDERS:-rules openai-codex}"
CHAOS_CYCLES="${CHAOS_CYCLES:-100}"
OUT_DIR="${OUT_DIR:-docs/stress-test-screens}"

date_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
date_short=$(date -u +"%Y-%m-%d")
REPORT="docs/chaos-report-${date_short}.md"
mkdir -p "$(dirname "$REPORT")"

L1_STATUS="not_run"
L2_STATUS="not_run"
L3_STATUS="not_run"
L5_STATUS="not_run"
L1_DETAIL=""
L2_DETAIL=""
L3_DETAIL=""
L5_DETAIL=""

overall_rc=0

# --- Layer 1: deterministic pytests ---------------------------------------
echo "chaos_full: Layer 1 — deterministic chaos pytests"
if "$PYTHON_BIN" -m pytest \
    tests/test_chaos_fake_endpoint.py \
    tests/test_chained_failures.py \
    tests/test_learned_fix_replay.py \
    tests/test_sequence_chaos.py \
    -q >/tmp/chaos-l1.log 2>&1; then
  L1_STATUS="pass"
else
  L1_STATUS="fail"
  overall_rc=1
fi
L1_DETAIL=$(tail -n 1 /tmp/chaos-l1.log || true)

# --- Layer 2: adversarial-proxy sweep -------------------------------------
echo "chaos_full: Layer 2 — chaos_qwen.sh"
if command -v ollama >/dev/null 2>&1 && \
   curl -fsS --max-time 2 "http://127.0.0.1:11434/v1/models" >/dev/null 2>&1; then
  if PYTHON_BIN="$PYTHON_BIN" OUT_DIR="$OUT_DIR" \
       bash scripts/chaos_qwen.sh >/tmp/chaos-l2.log 2>&1; then
    L2_STATUS="pass"
  else
    L2_STATUS="fail"
    overall_rc=1
  fi
  L2_DETAIL=$(grep -E "^chaos_qwen|wrote " /tmp/chaos-l2.log | tail -n 3 | tr '\n' '; ')
else
  L2_STATUS="skipped"
  L2_DETAIL="Ollama unavailable on 127.0.0.1:11434"
fi

# --- Layer 3: two-brain stress matrix -------------------------------------
echo "chaos_full: Layer 3 — stress_matrix.sh"
if curl -s -m 2 "http://127.0.0.1:${STRESS_PORT}/api/snapshot" >/dev/null 2>&1; then
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    if PORT="$STRESS_PORT" PROVIDERS="$STRESS_PROVIDERS" OUT_DIR="$OUT_DIR" \
         bash scripts/stress_matrix.sh >/tmp/chaos-l3.log 2>&1; then
      L3_STATUS="pass"
    else
      L3_STATUS="fail"
      overall_rc=1
    fi
    L3_DETAIL="providers=$STRESS_PROVIDERS · $(tail -n 2 /tmp/chaos-l3.log | tr '\n' '; ')"
  else
    L3_STATUS="skipped"
    L3_DETAIL="OPENAI_API_KEY not set"
  fi
else
  L3_STATUS="skipped"
  L3_DETAIL="Dashboard not running on :$STRESS_PORT"
fi

# --- Layer 5: supervisor soak ---------------------------------------------
echo "chaos_full: Layer 5 — chaos_supervisor.py"
SUPERVISOR_OUT="docs/chaos-supervisor-${date_short}.json"
if "$PYTHON_BIN" scripts/chaos_supervisor.py \
    --cycles "$CHAOS_CYCLES" \
    --seed 0 \
    --output "$SUPERVISOR_OUT" >/tmp/chaos-l5.log 2>&1; then
  L5_STATUS="pass"
else
  L5_STATUS="fail"
  overall_rc=1
fi
L5_DETAIL=$(tail -n 1 /tmp/chaos-l5.log || true)

# --- Aggregate report -----------------------------------------------------
{
  echo "# Chaos report · $date_utc"
  echo
  if [ "$overall_rc" = "0" ]; then
    echo "Overall: **PASS**"
  else
    echo "Overall: **FAIL**"
  fi
  echo
  echo "| layer | what | status | detail |"
  echo "|---|---|---|---|"
  echo "| 1 | deterministic chaos pytests | $L1_STATUS | $L1_DETAIL |"
  echo "| 2 | adversarial-proxy sweep (real Qwen) | $L2_STATUS | $L2_DETAIL |"
  echo "| 3 | two-brain stress matrix | $L3_STATUS | $L3_DETAIL |"
  echo "| 5 | supervisor stability soak ($CHAOS_CYCLES cycles) | $L5_STATUS | $L5_DETAIL |"
  echo
  if [ "$L2_STATUS" = "pass" ] || [ "$L2_STATUS" = "fail" ]; then
    echo "Layer 2 markdown: \`$OUT_DIR/chaos-qwen.md\`"
  fi
  if [ "$L3_STATUS" = "pass" ] || [ "$L3_STATUS" = "fail" ]; then
    echo "Layer 3 markdown: \`$OUT_DIR/stress-matrix.md\`"
  fi
  echo "Layer 5 JSON: \`$SUPERVISOR_OUT\`"
} > "$REPORT"

echo "wrote $REPORT"
exit $overall_rc
