# AMD Developer Cloud Setup

This guide is for the AMD Developer Cloud console hosted on DigitalOcean.

## Current State

- AMD AI Developer Program account exists.
- AMD Developer Cloud / DigitalOcean console is reachable.
- Cloud credit request has been submitted.
- Project shown in the console: `My AMD Team`.

Do not create a GPU Droplet until credits are visible or the team deliberately decides to pay out of pocket.

## Before Creating A GPU Droplet

1. Open **Settings** in the AMD/DigitalOcean project.
2. Complete the **Action Needed** item by updating project information.
3. Open **Billing** or **My AMD Home** and verify that AMD credits are visible.
4. Add an SSH key to the DigitalOcean account.
5. Confirm the local ROCm Doctor demo loop works without a GPU:
   - health check fails/passes deterministically
   - diagnosis returns a specific failure class
   - repair plan is shown
   - verification reruns
   - incident report is generated

## Create The GPU Droplet

Use the smallest useful AMD GPU instance for the hackathon proof.

Recommended settings:

- Product: **GPU Droplet**
- GPU plan: **1x AMD Instinct MI300X**
- Avoid: 8x GPU plan unless there is a specific multi-GPU requirement
- Image: AMD **AI/ML-ready image** if available
- SSH: use key auth
- Name: `rocm-doctor-demo`
- Backups: off for the first validation pass
- Extra storage: avoid unless needed

DigitalOcean's current docs list the self-serve MI300X size as `gpu-mi300x1-192gb`, with 192 GB GPU memory, 240 GiB Droplet memory, 20 vCPUs, and a 720 GiB boot disk. Their AMD AI/ML-ready image is based on Ubuntu 24.04 and includes ROCm packages.

## First SSH Checks

After the VM is created, SSH into it and verify the ROCm stack before installing project code.

```bash
rocminfo | head
amd-smi || rocm-smi
python3 --version
docker --version
```

If GPU visibility fails, collect the command output and do not spend time installing the app yet.

## VM Usage Discipline

GPU Droplets bill until destroyed. Powering off is not enough because the disk, CPU, RAM, and IP remain reserved.

Working pattern:

1. Create the GPU Droplet only for an active validation window.
2. Clone the repo and run the GPU smoke checks.
3. Validate the vLLM endpoint and ROCm Doctor repair loop.
4. Save logs, screenshots, and reports back to git or local storage.
5. Destroy the GPU Droplet when the run is done.

## AMD Proof Goal

The cloud VM only needs to prove the AMD-specific path:

- vLLM can serve an OpenAI-compatible endpoint on MI300X/ROCm.
- ROCm Doctor can inspect the endpoint/runtime state.
- At least one failure diagnosis uses real ROCm/vLLM evidence.
- The report clearly shows the system running on AMD Developer Cloud.

The broader check/diagnose/heal/report loop should be developed locally before spending GPU time.

## References

- AMD Developer Cloud: https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html
- AMD getting started guide: https://www.amd.com/en/developer/resources/technical-articles/2025/how-to-get-started-on-the-amd-developer-cloud-.html
- DigitalOcean GPU Droplets: https://docs.digitalocean.com/products/gpu-droplets/
- DigitalOcean GPU setup: https://docs.digitalocean.com/products/droplets/getting-started/recommended-gpu-setup/

