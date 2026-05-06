#!/usr/bin/env bash
# Stress-test driver for the ROCm Doctor dashboard.
#
# Boots the dashboard (or assumes one is already running on $PORT) and walks
# the cartesian product of:
#   - real-config injectable scenarios (real recipes should fire and heal)
#   - safety/fake scenarios            (recipes should be rejected, not heal)
# across a list of diagnosis providers (rules, codex-cli, anthropic,
# openai-compatible, ...).
#
# Output: a markdown results table and per-row JSON dumps under $OUT_DIR.
#
# Usage:
#   PORT=8765 OUT_DIR=docs/stress-test-screens \
#     PROVIDERS="rules codex-cli anthropic openai-compatible" \
#     scripts/stress_matrix.sh
#
# Requires: curl, jq.

set -euo pipefail

PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
BASE="http://${HOST}:${PORT}"
PROVIDERS="${PROVIDERS:-rules codex-cli anthropic openai-compatible}"
REAL_SCENARIOS="${REAL_SCENARIOS:-wrong_endpoint_port context_length_too_large tool_parser_mismatch missing_rocm_device_flags}"
SAFETY_SCENARIOS="${SAFETY_SCENARIOS:-malformed_provider_output unknown_recipe unsafe_command path_traversal credential_modification}"
OUT_DIR="${OUT_DIR:-docs/stress-test-screens}"
RESULTS_MD="${RESULTS_MD:-${OUT_DIR}/stress-matrix.md}"
RESULTS_JSON_DIR="${OUT_DIR}/runs"

mkdir -p "$RESULTS_JSON_DIR"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 2
fi

# Wait for the dashboard.
wait_ready() {
  local i
  for i in $(seq 1 30); do
    if curl -s -m 2 "$BASE/api/snapshot" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "dashboard at $BASE not reachable after 30s" >&2
  exit 3
}

reset_workspace() {
  curl -s -X POST "$BASE/api/reset" -d '{}' >/dev/null
}

call_run() {
  local scenario="$1"
  local provider="$2"
  local body
  body=$(jq -n --arg s "$scenario" --arg p "$provider" '{scenario:$s, provider_name:$p}')
  curl -s -X POST -H 'Content-Type: application/json' -d "$body" "$BASE/api/run"
}

summarize_md_row() {
  # Reads JSON on stdin, writes a single markdown table row.
  jq -r '
    . as $r
    | (($r.self_heal.repairs // []) | last // {}) as $rep
    | "| " + ($r.scenario // "")
    + " | " + ($r.diagnosis_provider // "")
    + " | " + ($rep.recipe_id // "")
    + " | " + (($r.duration_ms // 0) | tostring)
    + " | " + (
        if $r.self_heal.healthy then "healed"
        elif (($r.self_heal.repairs // []) | length) == 0 then "no_attempt"
        elif ($rep.applied // false) and ($rep.rolled_back // false) then "rolled_back"
        elif ($rep.applied // false) then "verify_failed"
        else "rejected"
        end
      )
    + " | " + ($r.incident_id // "")
    + " |"'
}

wait_ready

date_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

{
  echo "# Stress matrix · $date_utc"
  echo
  echo "Dashboard: $BASE  ·  providers: \`$PROVIDERS\`"
  echo
  echo "## Real-config scenarios (heal expected)"
  echo
  printf "| scenario | provider | recipe | duration_ms | outcome | incident |\n"
  printf "|---|---|---|---:|---|---|\n"
} > "$RESULTS_MD"

run_phase() {
  local label="$1"
  local list="$2"
  for scenario in $list; do
    for provider in $PROVIDERS; do
      reset_workspace
      local out_json
      out_json="${RESULTS_JSON_DIR}/${label}-${provider}-${scenario}.json"
      local body
      body=$(call_run "$scenario" "$provider" || echo '{}')
      printf '%s' "$body" > "$out_json"
      local row
      row=$(printf '%s' "$body" | summarize_md_row 2>/dev/null || true)
      if [ -z "$row" ]; then
        printf "| %s | %s | (api error — see %s) | — | error | — |\n" \
          "$scenario" "$provider" "$(basename "$out_json")" >> "$RESULTS_MD"
      else
        printf '%s\n' "$row" >> "$RESULTS_MD"
      fi
    done
  done
}

run_phase "real" "$REAL_SCENARIOS"

{
  echo
  echo "## Safety / fake-provider scenarios (rejection expected)"
  echo
  printf "| scenario | provider | recipe | duration_ms | outcome | incident |\n"
  printf "|---|---|---|---:|---|---|\n"
} >> "$RESULTS_MD"

run_phase "safety" "$SAFETY_SCENARIOS"

echo "wrote $RESULTS_MD"
echo "raw runs in $RESULTS_JSON_DIR"
