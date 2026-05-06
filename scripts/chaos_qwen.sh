#!/usr/bin/env bash
# Adversarial-proxy heal-cycle sweep against real Ollama qwen3:0.6b.
#
# For each adversarial-proxy failure mode, boots the proxy in front of a real
# Ollama backend, points a copy of demo/ollama-tiny-models.yaml at it, runs
# self-heal + verify, and logs {mode, recipe_used, attempts, healed, ms} to a
# per-mode JSON file. Closes the gap left by detect-only adversarial tests.
#
# Skips cleanly when Ollama isn't reachable.
#
# Usage:
#   scripts/chaos_qwen.sh
#
# Env knobs:
#   OLLAMA_BASE_URL  upstream OpenAI-compatible base url (default: 127.0.0.1:11434/v1)
#   QWEN_MODEL_ID    upstream model id                  (default: qwen3:0.6b)
#   PROXY_PORT       proxy listen port                  (default: 8001)
#   OUT_DIR          where to write per-run JSON + chaos-qwen.md (default: docs/stress-test-screens)
#   PYTHON_BIN       python interpreter                 (default: /tmp/rocm-doctor-venv/bin/python)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434/v1}"
QWEN_MODEL_ID="${QWEN_MODEL_ID:-qwen3:0.6b}"
PROXY_PORT="${PROXY_PORT:-8001}"
OUT_DIR="${OUT_DIR:-docs/stress-test-screens}"
RUNS_DIR="${OUT_DIR}/runs"
RESULTS_MD="${OUT_DIR}/chaos-qwen.md"
PYTHON_BIN="${PYTHON_BIN:-/tmp/rocm-doctor-venv/bin/python}"

mkdir -p "$RUNS_DIR"

# Modes that are expected to heal cleanly through detect → heal → verify on real
# Qwen. The remaining adversarial modes inject persistent upstream failures
# (e.g. chat_500, drop_connection) that no config edit can recover from while
# the proxy is still misbehaving — those are detect-only by design and do not
# count as failures here.
EXPECTED_HEAL_MODES="healthy rate_limit_once slow_response empty_chat_content_once stream_interrupt"

if ! command -v ollama >/dev/null 2>&1; then
  echo "chaos_qwen: ollama CLI not found, skipping." >&2
  exit 0
fi

if ! curl -fsS --max-time 2 "${OLLAMA_BASE_URL%/}/models" >/dev/null 2>&1; then
  echo "chaos_qwen: Ollama not reachable at ${OLLAMA_BASE_URL}, skipping." >&2
  exit 0
fi

if ! "$PYTHON_BIN" -c "import rocm_doctor" >/dev/null 2>&1; then
  echo "chaos_qwen: rocm_doctor not importable from $PYTHON_BIN" >&2
  exit 2
fi

MODES="$("$PYTHON_BIN" - <<'PY'
from rocm_doctor.adversarial_proxy import ADVERSARIAL_FAILURE_MODES
print("\n".join(ADVERSARIAL_FAILURE_MODES))
PY
)"

date_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

{
  echo "# Chaos-Qwen adversarial heal-cycle sweep · $date_utc"
  echo
  echo "Upstream: \`$OLLAMA_BASE_URL\`  ·  model: \`$QWEN_MODEL_ID\`  ·  proxy: \`127.0.0.1:$PROXY_PORT\`"
  echo
  printf "| mode | recipe | attempts | outcome | duration_ms |\n"
  printf "|---|---|---:|---|---:|\n"
} > "$RESULTS_MD"

run_one_mode() {
  local mode="$1"
  local work_dir
  work_dir=$(mktemp -d -t rocm-doctor-chaos-qwen.XXXXXX)
  local config_path="${work_dir}/config.yaml"
  local out_json="${RUNS_DIR}/chaos-qwen-${mode}.json"

  cp demo/ollama-tiny-models.yaml "$config_path"
  "$PYTHON_BIN" - "$config_path" "$mode" "$PROXY_PORT" "$work_dir" <<'PY'
import sys
from pathlib import Path
import yaml

config_path = Path(sys.argv[1])
mode = sys.argv[2]
proxy_port = int(sys.argv[3])
work_dir = Path(sys.argv[4])

raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
provider = raw["model_providers"]["ollama-qwen3-0-6b"]
proxy_url = f"http://127.0.0.1:{proxy_port}/v1"
provider["model"]["endpoint"]["base_url"] = proxy_url
provider["model"]["endpoint"]["expected_base_url"] = proxy_url
provider["model"]["endpoint"]["wrong_base_url"] = "http://127.0.0.1:9/v1"
provider["request"]["timeout_seconds"] = 0.4 if mode == "slow_response" else 30.0
provider["request"]["retry"]["max_attempts"] = 2
provider["request"]["stream"] = mode == "stream_interrupt"
raw["active_model_provider"] = "ollama-qwen3-0-6b"
raw["workspace"] = str(work_dir)
raw["reports_dir"] = str(work_dir / "reports")
raw["state_file"] = str(work_dir / ".state.json")
config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
PY

  "$PYTHON_BIN" -m rocm_doctor adversarial-proxy \
    --upstream-base-url "$OLLAMA_BASE_URL" \
    --port "$PROXY_PORT" \
    --model-id "$QWEN_MODEL_ID" \
    --failure-mode "$mode" \
    --slow-response-seconds 0.4 \
    --forward-before-failure \
    >"${work_dir}/proxy.log" 2>&1 &
  local proxy_pid=$!
  trap 'kill '"$proxy_pid"' >/dev/null 2>&1 || true' EXIT

  # Wait for proxy to come up.
  local ready=0 i
  for i in $(seq 1 30); do
    if curl -fsS --max-time 1 "http://127.0.0.1:${PROXY_PORT}/v1/models" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 0.2
  done
  if [ "$ready" != "1" ] && [ "$mode" != "models_500" ] && [ "$mode" != "rate_limit" ] && [ "$mode" != "drop_connection" ]; then
    echo "chaos_qwen: proxy did not come up for $mode" >&2
  fi

  local start_ms heal_status verify_status
  start_ms=$(python3 -c "import time;print(int(time.time()*1000))")
  set +e
  "$PYTHON_BIN" -m rocm_doctor self-heal --provider rules --config "$config_path" \
    >"${work_dir}/self_heal.json" 2>"${work_dir}/self_heal.err"
  heal_status=$?
  "$PYTHON_BIN" -m rocm_doctor verify --config "$config_path" \
    >"${work_dir}/verify.json" 2>"${work_dir}/verify.err"
  verify_status=$?
  set -e
  local end_ms duration_ms
  end_ms=$(python3 -c "import time;print(int(time.time()*1000))")
  duration_ms=$((end_ms - start_ms))

  kill "$proxy_pid" >/dev/null 2>&1 || true
  wait "$proxy_pid" 2>/dev/null || true
  trap - EXIT

  local recipe attempts healed outcome
  recipe=$("$PYTHON_BIN" - "${work_dir}/self_heal.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
    repairs = data.get("repairs") or []
    print((repairs[-1].get("recipe_id") if repairs else "") or "")
except Exception:
    print("")
PY
)
  attempts=$("$PYTHON_BIN" - "${work_dir}/self_heal.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
    print(data.get("attempts", 0))
except Exception:
    print(0)
PY
)
  healed=$("$PYTHON_BIN" - "${work_dir}/self_heal.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
    print("true" if data.get("healthy") else "false")
except Exception:
    print("false")
PY
)

  if [ "$healed" = "true" ] && [ "$verify_status" = "0" ]; then
    outcome="healed"
  elif [ "$healed" = "true" ]; then
    outcome="heal_no_verify"
  elif [ "$mode" = "healthy" ] && [ "$heal_status" = "0" ]; then
    outcome="already_healthy"
  else
    outcome="unrecoverable"
  fi

  "$PYTHON_BIN" - "${work_dir}/self_heal.json" "$mode" "$recipe" "$attempts" "$healed" "$outcome" "$duration_ms" "$out_json" <<'PY'
import json, sys
heal_path, mode, recipe, attempts, healed, outcome, duration_ms, out_json = sys.argv[1:]
try:
    with open(heal_path) as fh:
        heal = json.load(fh)
except Exception:
    heal = {}
record = {
    "mode": mode,
    "recipe_used": recipe,
    "attempts": int(attempts or 0),
    "healed": healed == "true",
    "outcome": outcome,
    "duration_ms": int(duration_ms or 0),
    "self_heal": heal,
}
with open(out_json, "w") as fh:
    json.dump(record, fh, indent=2, sort_keys=True)
PY

  local expected_heal="no"
  for expected in $EXPECTED_HEAL_MODES; do
    if [ "$expected" = "$mode" ]; then
      expected_heal="yes"
      break
    fi
  done

  local gate_marker=""
  if [ "$expected_heal" = "yes" ] && [ "$outcome" != "healed" ] && [ "$outcome" != "already_healthy" ]; then
    gate_marker=" ❌"
    FAILED_EXPECTED_MODES="${FAILED_EXPECTED_MODES} ${mode}(${outcome})"
  fi

  printf "| %s | %s | %s | %s%s | %s |\n" \
    "$mode" "${recipe:-—}" "$attempts" "$outcome" "$gate_marker" "$duration_ms" \
    >> "$RESULTS_MD"

  rm -rf "$work_dir"
}

FAILED_EXPECTED_MODES=""

while IFS= read -r mode; do
  [ -z "$mode" ] && continue
  echo "chaos_qwen: running mode=$mode"
  run_one_mode "$mode"
done <<< "$MODES"

{
  echo
  echo "Expected-heal gate: \`$EXPECTED_HEAL_MODES\`"
  if [ -z "$FAILED_EXPECTED_MODES" ]; then
    echo
    echo "Gate: **PASS** — every expected-heal mode reached a healed outcome."
  else
    echo
    echo "Gate: **FAIL** — modes that should have healed did not:${FAILED_EXPECTED_MODES}"
  fi
} >> "$RESULTS_MD"

echo "wrote $RESULTS_MD"
echo "raw runs in $RUNS_DIR"

if [ -n "$FAILED_EXPECTED_MODES" ]; then
  echo "chaos_qwen: gate FAILED:${FAILED_EXPECTED_MODES}" >&2
  exit 1
fi
