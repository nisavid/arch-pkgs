# Backlog

This doc tracks active follow-up work for this repo.

The current focus is the experimental `utilyze` package. The package is built,
documented, and partially verified. The remaining work is to validate it on a
supported NVIDIA host and to build a maintainable acceptance story for its TUI.

## utilyze

### 1. Choose a supported NVIDIA validation rig

Status: selected. Use a short-lived TensorDock on-demand GPU VM with one NVIDIA
RTX 4090 24 GB GPU, SSH/root access, and an Arch Linux package-runtime
container or chroot. See
[docs/maintainers/utilyze-nvidia-validation-rig.md](maintainers/utilyze-nvidia-validation-rig.md)
for the option survey, rationale, fallback order, and cost guardrails.

Deliverables:

- Short option survey for NVIDIA-capable test environments.
- One chosen environment with a clear reason for the choice.
- Exact host shape, image, region, access model, cost guardrails, and teardown
  procedure.

Exit criteria:

- One test-rig approach is selected.
- The selected approach is specified well enough that another maintainer can
  provision the same environment without chat history.

### 2. Materialize the chosen NVIDIA test fixture

Provision the selected environment and turn it into a repeatable package-test
fixture.

Deliverables:

- Provisioning steps for the chosen host.
- Arch package installation steps for `utilyze` and its runtime dependencies.
- One smoke-tested fixture definition, including setup, first-run, and cleanup
  commands.

Exit criteria:

- The fixture can be created from scratch.
- The fixture can run the packaged `utilyze` binary on supported NVIDIA
  hardware.
- The fixture has at least one recorded smoke test.

### 3. Define representative GPU workloads for validation

Choose workloads that create useful, varied GPU activity while `utilyze` is
running. The goal is to exercise the package under conditions that are easy to
repeat and easy to observe.

Deliverables:

- A small workload set that covers idle, steady load, and changing load.
- Launch commands and expected high-level behavior for each workload.
- Guidance on running workloads in parallel with the `utilyze` TUI.

Exit criteria:

- At least one workload produces clear, sustained GPU activity.
- At least one workload changes over time in a way that should be visible in the
  TUI.

### 4. Specify the TUI's acceptance contract

Write stable, behavior-oriented acceptance criteria for the `utilyze` TUI. The
spec should describe what the operator must be able to do and observe, not the
exact layout, styling, or implementation details of one version.

Deliverables:

- A behavioral spec for the TUI's essential contract.
- Coverage for startup, degraded states, live updates, navigation,
  responsiveness, and exit behavior.
- Clear boundaries for what the spec intentionally does not lock down.

Exit criteria:

- The spec is precise enough that two maintainers can evaluate the same build
  against it.
- The spec avoids brittle requirements about exact presentation details.

### 5. Design an agent-in-the-loop TUI test harness

Define the harness that will present prompts to a human operator, collect
pass/fail decisions, and record notes from nondeterministic interactive runs.

Deliverables:

- Research notes on viable harness shapes.
- A chosen harness design and operator workflow.
- A durable format for test prompts, operator responses, and run artifacts.

Exit criteria:

- The harness design is specific enough to implement without re-opening basic
  workflow questions.
- The operator workflow is explicit about what to do, what to look for, and how
  to record the result.

### 6. Implement the harness and its first docs

Build the first usable version of the harness and document how to use it.

Deliverables:

- Initial harness implementation.
- Setup and usage docs.
- One smoke test that proves the harness can run an operator-guided case and
  record the outcome.

Exit criteria:

- A maintainer can run the harness end to end.
- The harness records a pass/fail result plus operator notes.

### 7. Author the first `utilyze` acceptance stories

Use the harness to express the `utilyze` TUI's first real acceptance suite.

Deliverables:

- A first set of `utilyze` user stories expressed in the new harness format.
- Coverage for the core operator journey on a supported NVIDIA host.
- Clear failure reporting for unmet expectations or ambiguous observations.

Exit criteria:

- The suite covers the primary interactive behaviors of the current package.
- The stories are concrete enough to run without additional interpretation.

### 8. Drive the harness and the `utilyze` suite to a first comprehensive release

Iterate on both the harness and the package-specific suite until they are ready
for regular use.

Deliverables:

- Revisions driven by real operator runs.
- Stable documentation for maintainers.
- A release-ready first comprehensive version of the `utilyze` acceptance suite.

Exit criteria:

- The harness is usable for repeated package-maintenance work.
- The `utilyze` suite is comprehensive enough to support future package updates
  and validation passes.
