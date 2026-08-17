# utilyze

Package-local maintainer notes for the Arch `utilyze` package.

Use [`README.Arch.md`](README.Arch.md) for user-facing behavior, first-run
guidance, telemetry consent, and the current verified/not-verified boundary.
That file is installed as `/usr/share/doc/utilyze/README.Arch.md`.

## Maintenance Baseline

- `authoritative_reference`: upstream
  [`utilyze` v0.1.3 source and release metadata](https://github.com/systalyze/utilyze/releases/tag/v0.1.3);
  no same-name Arch or AUR recipe was available at the 2026-08 refresh.
- `advisory_references`: Arch CUDA and NVIDIA package layouts, NVIDIA profiling
  and CUPTI documentation, and this repository's
  [selected validation rig](../../docs/maintainers/utilyze-nvidia-validation-rig.md).
- `divergence_notes`: the current `0.1.1-2` recipe carries Arch CUDA-path,
  profiling-policy, package-update, configuration, and telemetry-consent
  patches. The selected `0.1.3` destination must rederive those behaviors for
  upstream's client/server and JSON-config architecture, drop the obsolete
  generic-config patch, and build the native sampler explicitly; it has not
  passed the required acceptance gate.
- `update_notes`: verify the pinned source and patch intent, clean-build and
  inspect the package and embedded native sampler without runtime bootstrap or
  update traffic, then pass config migration, fail-closed telemetry, service
  ownership, and live Ampere-or-newer NVIDIA/CUPTI TUI acceptance before this
  deferred lane becomes publication-eligible.

## What This Directory Adds

- Arch package recipe in `PKGBUILD`
- `.SRCINFO` metadata
- Arch runtime/config/telemetry patches
- `utilyze.install` post-install and post-upgrade reminders
- Installed user doc in `README.Arch.md`

## Current Maintenance State

The package builds and its package-level tests cover the Arch config and
telemetry-consent patches. Runtime validation on supported NVIDIA hardware is
still active follow-up work.

See [`docs/backlog.md`](../../docs/backlog.md) for the current acceptance and
validation plan. The selected first NVIDIA validation rig is documented in
[`docs/maintainers/utilyze-nvidia-validation-rig.md`](../../docs/maintainers/utilyze-nvidia-validation-rig.md).

Keep host-specific commands, credentials, provider state, and private runtime
paths out of tracked docs. Prefer package defaults and reproducible validation
notes.
