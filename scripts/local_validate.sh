#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROCM_DOCTOR_VENV:-/tmp/rocm-doctor-venv}"
PYTHON="${PYTHON:-python3}"
DEMO_CONFIG="${ROCM_DOCTOR_DEMO_CONFIG:-/tmp/rocm-doctor-local-demo.yaml}"
FAKE_PORT="${ROCM_DOCTOR_FAKE_PORT:-8000}"
STARTED_FAKE_ENDPOINT=0

cleanup() {
  if [[ "${STARTED_FAKE_ENDPOINT}" == "1" && -n "${FAKE_ENDPOINT_PID:-}" ]]; then
    kill "${FAKE_ENDPOINT_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ ! -x "${VENV}/bin/python" ]]; then
  "${PYTHON}" -m venv "${VENV}"
fi

"${VENV}/bin/python" -m pip install -q -e "${ROOT}[test]"

cd "${ROOT}"

"${VENV}/bin/python" -m compileall rocm_doctor tests
"${VENV}/bin/python" -m pytest -q

if ! curl -fsS --max-time 1 "http://127.0.0.1:${FAKE_PORT}/v1/models" >/dev/null 2>&1; then
  "${VENV}/bin/python" -m rocm_doctor fake-endpoint --port "${FAKE_PORT}" &
  FAKE_ENDPOINT_PID="$!"
  STARTED_FAKE_ENDPOINT=1
  sleep 1
fi

cp demo/rocm-doctor.yaml "${DEMO_CONFIG}"
"${VENV}/bin/python" -m rocm_doctor check --config "${DEMO_CONFIG}" >/dev/null
"${VENV}/bin/python" -m rocm_doctor inject-failure wrong_endpoint_port --config "${DEMO_CONFIG}" >/dev/null
"${VENV}/bin/python" -m rocm_doctor self-heal --provider rules --config "${DEMO_CONFIG}" >/dev/null
"${VENV}/bin/python" -m rocm_doctor report --config "${DEMO_CONFIG}" >/dev/null

if command -v ollama >/dev/null 2>&1 && curl -fsS --max-time 2 "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
  if ollama list | grep -q '^qwen3:0.6b'; then
    "${VENV}/bin/python" -m rocm_doctor check --config demo/ollama-tiny-models.yaml >/dev/null
    ROCM_DOCTOR_RUN_REAL_QWEN=1 "${VENV}/bin/python" -m pytest tests/test_real_qwen_adversarial.py -q -s
  else
    echo "Skipping real-Qwen checks: qwen3:0.6b is not installed in Ollama."
  fi
else
  echo "Skipping Ollama checks: Ollama is unavailable or not serving on 127.0.0.1:11434."
fi

echo "Local validation complete."
