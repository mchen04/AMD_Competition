# AMD Developer Cloud Setup

GPU droplet setup on AMD Developer Cloud / DigitalOcean. Run the local validation gate (`scripts/local_validate.sh`) before spending GPU time.

## Before Creating a Droplet

1. Verify AMD credits visible in **Billing** / **My AMD Home**.
2. Add SSH key to the DigitalOcean account.
3. Confirm the local loop works: `scripts/local_validate.sh`.

## Droplet Settings

- **Plan:** `gpu-mi300x1-192gb` (1× MI300X, 192 GB GPU mem, 240 GiB RAM, 20 vCPU, 720 GiB disk).
- **Image:** AMD AI/ML-ready (Ubuntu 24.04 + ROCm) or **ROCm-enabled GPT-OSS 120b** image.
- **Auth:** SSH key only.
- **Backups:** off for first pass.
- **Name:** `rocm-doctor-demo`.

Avoid the 8× MI300X plan unless a benchmark needs multi-GPU.

## First SSH Checks

```bash
rocminfo | head
amd-smi || rocm-smi
python3 --version
docker --version
```

If GPU isn't visible, capture the output and stop. Don't install the harness yet.

## Find or Start vLLM

Check for a pre-started endpoint:

```bash
ss -ltnp | grep ':8000' || true
curl -sS http://127.0.0.1:8000/v1/models | head
```

If none exists, start vLLM manually:

```bash
MODEL_ID=openai/gpt-oss-120b   # fallback: openai/gpt-oss-20b
python3 -m vllm.entrypoints.openai.api_server \
  --model "${MODEL_ID}" --host 0.0.0.0 --port 8000 --max-model-len 4096
```

Verify:

```bash
curl -sS http://127.0.0.1:8000/v1/models
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"'"${MODEL_ID}"'","messages":[{"role":"user","content":"Return exactly ROCM_DOCTOR_OK"}],"temperature":0,"max_tokens":32}'
```

## Install ROCm Doctor

```bash
git clone https://github.com/mchen04/AMD_Competition.git
cd AMD_Competition
python3 -m venv /tmp/rocm-doctor-venv
/tmp/rocm-doctor-venv/bin/python -m pip install -e '.[test]'
```

## Configure the AMD Provider

```bash
cp demo/amd-vllm-template.yaml /tmp/rocm-doctor-amd.yaml
```

Edit `/tmp/rocm-doctor-amd.yaml`:

- `model.id` — actual id from `/v1/models`
- `model.endpoint.base_url` — `http://127.0.0.1:8000/v1`
- `model.endpoint.expected_base_url` — same as `base_url`
- `model.endpoint.wrong_base_url` — `http://127.0.0.1:8001/v1`
- `model.context.max_tokens: 4096`, `safe_max_tokens: 8192`
- `request.timeout_seconds: 30.0` if responses are slow
- `model.tool_calling.enabled: false` if the model/image doesn't expose tool calls cleanly
- `runtime_type: amd-vllm`
- `capabilities.rocm_device_flags: true`
- `launch.required_device_flags: ["/dev/kfd", "/dev/dri"]`

## Run the Demo

See [demo-runbook.md](demo-runbook.md) for the full scenario list. Minimum proof:

```bash
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor check        --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor inject-failure wrong_endpoint_port --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor self-heal    --provider rules --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor verify       --config /tmp/rocm-doctor-amd.yaml
/tmp/rocm-doctor-venv/bin/python -m rocm_doctor report       --config /tmp/rocm-doctor-amd.yaml
```

## Cost Discipline

GPU droplets bill until **destroyed** — power-off doesn't free the resources. Pattern:

1. Create the droplet only for an active validation window.
2. Run smoke checks → validate vLLM → run ROCm Doctor scenarios → save logs/screenshots/reports.
3. Destroy the droplet.

Destroy if: GPU not visible after first SSH checks; vLLM can't serve either model in the planned window; the healthy check + at least one self-heal report are saved; the validation session is over.

## References

- AMD Developer Cloud: https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html
- DigitalOcean GPU Droplets: https://docs.digitalocean.com/products/gpu-droplets/
