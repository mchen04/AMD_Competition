#!/usr/bin/env bash
# ROCm Doctor demo runner — captures the canonical pin → supervise → inject →
# heal → restore → report sequence into ./evidence/ artifacts.
#
# Modes:
#   --local    (default) drives the bundled fake endpoint so the script runs
#              without ROCm hardware. Substitutes evidence/hardware-skipped.txt
#              for the GPU snapshots.
#   --droplet  asserts rocminfo / amd-smi / vLLM are reachable and captures
#              GPU snapshots before & after the heal. Auto-fills the AMD vLLM
#              template by parsing /v1/models for the served model id.
#
# Both modes produce the same evidence/0*.json|md|log artifacts so the demo
# narrative (and the screen recording driven through the dashboard) stays
# identical regardless of where it ran.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="local"
QUIET=0

for arg in "$@"; do
  case "$arg" in
    --local) MODE="local" ;;
    --droplet) MODE="droplet" ;;
    --quiet) QUIET=1 ;;
    --help|-h)
      sed -n '2,16p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

log() { [[ "${QUIET}" == "1" ]] || echo "[amd_demo:${MODE}] $*"; }

PYTHON="${PYTHON:-${ROOT}/$(test -x .venv/bin/python && echo .venv/bin/python || echo)}"
if [[ -z "${PYTHON}" || ! -x "${PYTHON}" ]]; then
  if [[ -x "/tmp/rocm-doctor-venv/bin/python" ]]; then
    PYTHON="/tmp/rocm-doctor-venv/bin/python"
  else
    PYTHON="$(command -v python3)"
  fi
fi

EVIDENCE_DIR="${ROOT}/evidence"
mkdir -p "${EVIDENCE_DIR}"

DEMO_CONFIG="${ROCM_DOCTOR_DEMO_CONFIG:-/tmp/rocm-doctor-amd-demo.yaml}"
FAKE_PORT="${ROCM_DOCTOR_FAKE_PORT:-8000}"
STARTED_FAKE_ENDPOINT=0
STARTED_SUPERVISOR=0

cleanup() {
  if [[ "${STARTED_SUPERVISOR}" == "1" && -n "${SUPERVISOR_PID:-}" ]]; then
    kill "${SUPERVISOR_PID}" >/dev/null 2>&1 || true
  fi
  if [[ "${STARTED_FAKE_ENDPOINT}" == "1" && -n "${FAKE_ENDPOINT_PID:-}" ]]; then
    kill "${FAKE_ENDPOINT_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# ──────────────────────────────────────────────────────────────────────
# Mode-specific setup: capture pre-run hardware evidence + pick template.

if [[ "${MODE}" == "droplet" ]]; then
  for tool in rocminfo amd-smi curl; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      echo "missing required tool: ${tool} (rerun on a real MI300X droplet)" >&2
      exit 3
    fi
  done
  log "capturing GPU pre-snapshot"
  rocminfo > "${EVIDENCE_DIR}/rocminfo-pre.txt" 2>&1 || true
  amd-smi monitor --power --temperature --gfx --vram --usage > "${EVIDENCE_DIR}/amd-smi-pre.txt" 2>&1 || true

  AMD_BASE_URL="${ROCM_DOCTOR_AMD_BASE_URL:-http://127.0.0.1:8000/v1}"
  if ! curl -fsS --max-time 5 "${AMD_BASE_URL}/models" -o "${EVIDENCE_DIR}/00-models.json"; then
    echo "vLLM /v1/models not reachable at ${AMD_BASE_URL}" >&2
    exit 4
  fi
  SERVED_MODEL_ID="$(${PYTHON} -c "
import json,sys
data=json.load(open('${EVIDENCE_DIR}/00-models.json'))
items=data.get('data') or []
print((items[0] or {}).get('id','') if items else '')
")"
  if [[ -z "${SERVED_MODEL_ID}" ]]; then
    echo "could not parse served model id from /v1/models" >&2
    exit 5
  fi
  log "served model: ${SERVED_MODEL_ID} @ ${AMD_BASE_URL}"

  cp "${ROOT}/demo/amd-vllm-template.yaml" "${DEMO_CONFIG}"
  ${PYTHON} - <<PY
import re, sys
from pathlib import Path
path = Path("${DEMO_CONFIG}")
text = path.read_text(encoding="utf-8")
text = text.replace("replace-with-served-model", "${SERVED_MODEL_ID}")
text = re.sub(r"http://replace-me\.example:8000/v1", "${AMD_BASE_URL}", text)
text = re.sub(r"http://replace-me\.example:8001/v1", "${AMD_BASE_URL%/*}/v1-broken", text)
path.write_text(text, encoding="utf-8")
PY
else
  log "running in --local mode (no MI300X required)"
  echo "ROCm hardware snapshot skipped: --local mode (no MI300X attached)" \
    > "${EVIDENCE_DIR}/hardware-skipped.txt"

  # Spin up the fake endpoint if nothing is already there.
  if ! curl -fsS --max-time 1 "http://127.0.0.1:${FAKE_PORT}/v1/models" >/dev/null 2>&1; then
    log "starting fake endpoint on :${FAKE_PORT}"
    "${PYTHON}" -m rocm_doctor fake-endpoint --port "${FAKE_PORT}" >"${EVIDENCE_DIR}/fake-endpoint.log" 2>&1 &
    FAKE_ENDPOINT_PID="$!"
    STARTED_FAKE_ENDPOINT=1
    sleep 1
  fi
  curl -fsS "http://127.0.0.1:${FAKE_PORT}/v1/models" -o "${EVIDENCE_DIR}/00-models.json"

  cp "${ROOT}/demo/rocm-doctor.yaml" "${DEMO_CONFIG}"
fi

# ──────────────────────────────────────────────────────────────────────
# 01 — pre-flight check (expected: healthy).
log "01 pre-flight check"
"${PYTHON}" -m rocm_doctor check --config "${DEMO_CONFIG}" \
  > "${EVIDENCE_DIR}/01-check-pre.json"

# 02 — pin the operator-blessed baseline.
log "02 pin baseline"
"${PYTHON}" -m rocm_doctor pin-baseline --config "${DEMO_CONFIG}" \
  > "${EVIDENCE_DIR}/02-pin.json"

# 03 — start the supervisor in the background; tail its events to a log.
log "03 supervise (max 6 cycles, interval 2s)"
PYTHONUNBUFFERED=1 "${PYTHON}" -u -m rocm_doctor supervise \
  --config "${DEMO_CONFIG}" \
  --interval 2 \
  --max-iterations 6 \
  > "${EVIDENCE_DIR}/03-supervise.log" 2>&1 &
SUPERVISOR_PID="$!"
STARTED_SUPERVISOR=1
sleep 1

# 04 — inject a deterministic drift the supervisor will notice & heal.
log "04 inject wrong_endpoint_port"
"${PYTHON}" -m rocm_doctor inject-failure wrong_endpoint_port \
  --config "${DEMO_CONFIG}" \
  > "${EVIDENCE_DIR}/04-inject.json"

# Wait up to ~30s for the supervisor to log a recovered cycle.
log "waiting for supervisor to heal"
heal_seen=0
for _ in $(seq 1 30); do
  if grep -q '"recovered": true' "${EVIDENCE_DIR}/03-supervise.log" 2>/dev/null; then
    heal_seen=1
    break
  fi
  sleep 1
done
[[ "${heal_seen}" == "1" ]] || log "WARN: supervisor did not log a recovered=true cycle within 30s"

# Stop the supervisor cleanly.
if kill -0 "${SUPERVISOR_PID}" >/dev/null 2>&1; then
  kill "${SUPERVISOR_PID}" >/dev/null 2>&1 || true
fi
wait "${SUPERVISOR_PID}" 2>/dev/null || true
STARTED_SUPERVISOR=0

# 05 — restore the pinned baseline and reverify.
log "05 restore baseline"
"${PYTHON}" -m rocm_doctor restore-baseline --config "${DEMO_CONFIG}" \
  > "${EVIDENCE_DIR}/05-restore.json"

# 06 — emit the markdown incident report.
log "06 generate report"
"${PYTHON}" -m rocm_doctor report --config "${DEMO_CONFIG}" \
  > "${EVIDENCE_DIR}/06-report.json"
REPORT_PATH=$("${PYTHON}" -c "import json; print(json.load(open('${EVIDENCE_DIR}/06-report.json')).get('path',''))")
if [[ -n "${REPORT_PATH}" && -f "${REPORT_PATH}" ]]; then
  cp "${REPORT_PATH}" "${EVIDENCE_DIR}/06-report.md"
fi

# Mode-specific post-snapshot.
if [[ "${MODE}" == "droplet" ]]; then
  log "capturing GPU post-snapshot"
  amd-smi monitor --power --temperature --gfx --vram --usage > "${EVIDENCE_DIR}/amd-smi-post.txt" 2>&1 || true
fi

# Tar everything up so it can be scp'd off a droplet.
TAR_NAME="evidence-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
( cd "${ROOT}" && tar -czf "${TAR_NAME}" evidence )
log "wrote ${TAR_NAME}"
log "done"
