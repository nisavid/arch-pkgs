# Utilyze NVIDIA Validation Rig

Retrieved: 2026-04-24

This note records the selected first validation rig for the experimental
`utilyze` package and the option survey behind it. It is a maintainer decision
note, not first-run user guidance. For the installed package behavior, read
[`packages/utilyze/README.Arch.md`](../../packages/utilyze/README.Arch.md).

## Decision

Use a short-lived TensorDock on-demand GPU VM with one NVIDIA RTX 4090 24 GB GPU,
a current Ubuntu control-plane image, SSH root access, and an Arch Linux
container or chroot as the package runtime environment.

Target shape:

- Provider: TensorDock.
- Region: Oregon, United States, when available from the RTX 4090 pool.
- GPU: 1x NVIDIA RTX 4090 24 GB.
- CPU and memory: smallest practical shape with at least 4 vCPU and 16 GiB RAM.
- Disk: at least 100 GiB temporary VM disk.
- Image: TensorDock Ubuntu 24.04 if available, otherwise the closest current
  Linux VM image.
- Runtime: Arch Linux userland in a privileged container or chroot with NVIDIA
  GPU access and `CAP_SYS_ADMIN`.
- Access model: SSH to the VM, then run the package validation from the Arch
  runtime.
- Cost target: less than 2 hours of active runtime for the first fixture pass.
- Teardown: copy run notes and artifacts back to the repo, destroy the VM, and
  confirm no stopped VM, reserved GPU, snapshot, persistent disk, or storage-only
  billing remains.

This is the cheapest practical path that still gives normal Linux control,
interactive SSH, and direct enough NVIDIA access for TUI validation. It does not
attempt to validate the upstream high-end attainable-SOL path.

## Why A100 Is Not The First Target

The package floor is Linux `x86_64`, NVIDIA Ampere or newer, and a CUDA/NVIDIA
runtime stack. The first acceptance target is live telemetry and TUI behavior, not
large-model throughput. Upstream lists RTX 3000+ systems alongside A100/H100-class
hardware for the base tool requirements, while the A100/H100 constraint applies
to the optional attainable-SOL inference-ceiling path.

For the first fixture, a single Ampere-or-newer RTX card is enough. A100, H100,
MIG, multi-GPU, and large-inference behavior can stay out of scope until the base
package validation passes.

## Option Survey

### TensorDock

TensorDock is the selected first attempt. Its public RTX 4090 page advertises
on-demand 4090 VM deployment from about $0.37/hour, with lower spot pricing, KVM
virtualization, root access, and a dedicated GPU passed through to the VM. That is
a good fit for a short interactive run where we want SSH, normal Linux tools, and
low hourly cost without a big-cloud quota request.

Tradeoffs:

- Arch is not advertised as a stock image, so the package runtime should be an
  Arch container or chroot inside the Linux VM.
- Marketplace inventory can change. If a 4090 is unavailable, use another
  Ampere-or-newer single GPU with similar access, such as RTX 3090, RTX A4000,
  RTX A5000, RTX A6000, A10, or L4.
- TensorDock uses prepaid billing. Do not use account-balance exhaustion as the
  teardown mechanism; explicitly delete the VM.

Sources:

- TensorDock RTX 4090 pricing and VM notes:
  <https://www.tensordock.com/gpu-4090.html>
- TensorDock GPU cloud overview:
  <https://www.tensordock.com/cloud-gpus.html>
- TensorDock SSH guide:
  <https://docs.tensordock.com/virtual-machines/how-to-ssh-into-your-instance>
- TensorDock instance creation API docs:
  <https://dashboard.tensordock.com/api/docs/instance-creation>

### RunPod

RunPod is the best quick container fallback. Its pod model supports SSH and
custom templates, and its public pricing includes inexpensive Ampere-or-newer
cards such as RTX A5000, RTX 3090, RTX 4090, A40, and L4. Use RunPod if a
containerized validation path is enough and TensorDock inventory is poor.

Tradeoffs:

- The natural unit is a container, not a native Arch VM.
- Storage and stopped-pod billing rules need close attention.
- Privileged profiling access must be verified before treating the run as a pass.

Sources:

- RunPod GPU pricing:
  <https://www.runpod.io/gpu-pricing>
- RunPod SSH docs:
  <https://docs.runpod.io/pods/configuration/use-ssh>
- RunPod custom template docs:
  <https://docs.runpod.io/pods/templates/create-custom-template>

### Vast.ai

Vast.ai is the lowest-cost flexible fallback if marketplace variance is acceptable.
It publishes live marketplace rates rather than one fixed rate. Its docs cover
SSH, custom Docker templates, and Linux VMs. The Linux VM path is useful because
it supports `systemd`, Docker, and fuller system control than a basic container.

Tradeoffs:

- Host quality, storage pricing, network, availability, and interruption behavior
  vary by offer.
- Start with verified hosts and on-demand rental for the first interactive TUI
  pass. Use interruptible offers only after the smoke test is automated.
- Stopped instances and storage can still cost money; delete the instance when
  done.

Sources:

- Vast.ai live pricing:
  <https://vast.ai/pricing>
- Vast.ai pricing model:
  <https://docs.vast.ai/documentation/instances/pricing>
- Vast.ai Linux VMs:
  <https://docs.vast.ai/linux-virtual-machines>
- Vast.ai SSH docs:
  <https://docs.vast.ai/documentation/instances/connect/ssh>

### GCP

GCP is viable as a fallback because the account already exists, but it is not the
best first choice. Use GCP only if quota is already available or if the goal is a
big-cloud baseline.

Reasonable GCP targets are T4 or L4 Spot VMs, not A100. A100 is unnecessary for
the base telemetry/TUI pass. GCP also does not provide a low-friction official
Arch base image path; native Arch would require custom-image work. That custom
image work is not justified for the first validation fixture.

If GCP is used, require these guardrails:

- Use Spot provisioning.
- Prefer T4 or L4.
- Set a short max runtime, such as 30-60 minutes.
- Use VM termination action `DELETE`.
- Keep boot disk auto-delete enabled.
- Avoid Local SSD and persistent data disks.
- Verify GPU-family quota before planning the run.

Sources:

- GCP GPU pricing:
  <https://cloud.google.com/compute/gpus-pricing>
- GCP Spot VM pricing:
  <https://cloud.google.com/spot-vms/pricing>
- GCP GPU machine types:
  <https://docs.cloud.google.com/compute/docs/gpus>
- GCP OS images:
  <https://docs.cloud.google.com/compute/docs/images>
- GCP custom OS image guide:
  <https://cloud.google.com/compute/docs/images/building-custom-os>
- GCP VM runtime limits:
  <https://cloud.google.com/compute/docs/instances/limit-vm-runtime>

### Lambda Cloud

Lambda Cloud is a reliable fallback but not cost-competitive for this task. Its
self-serve instance list is oriented toward higher-end GPUs, and the small
single-GPU options are still more expensive than the marketplace providers above.
Use it only if reliability matters more than hourly cost and a suitable
single-GPU instance is available.

Source:

- Lambda pricing:
  <https://lambda.ai/pricing>

### SaladCloud, CoreWeave, FluidStack, And Cluster Providers

These are not first-pass choices for this package.

SaladCloud can be very cheap, but its distributed/stateless model is a poor fit
for manual interactive TUI validation until the acceptance suite is automated.
CoreWeave and FluidStack are stronger fits for Kubernetes or cluster-scale GPU
workloads than for a one-off package smoke.

## Acceptance Boundaries

The first rig must prove:

- The packaged `utilyze` binary runs on live NVIDIA hardware from an Arch userland.
- The runtime sees an Ampere-or-newer NVIDIA GPU.
- `sudo utlz` or an equivalent `CAP_SYS_ADMIN` path can access the profiling
  counters required by the TUI.
- The TUI updates under idle, steady-load, and changing-load conditions.

The first rig does not need to prove:

- Native Arch boot on the cloud provider.
- A100/H100 attainable-SOL behavior.
- Multi-GPU behavior.
- MIG behavior.
- Long-running production monitoring.

## Next Step

Materialize the TensorDock fixture:

1. Confirm current TensorDock inventory for a 1x RTX 4090 VM in Oregon.
2. If unavailable, choose the cheapest on-demand Ampere-or-newer single-GPU VM
   with SSH/root access and at least 16 GiB RAM.
3. Provision the VM with the selected Linux image.
4. Build the Arch runtime and install the `utilyze` package.
5. Run idle, steady-load, and changing-load smokes.
6. Record exact commands, observed behavior, costs, and teardown evidence.
