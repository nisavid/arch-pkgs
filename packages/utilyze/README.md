# utilyze

Package-local maintainer notes for the Arch `utilyze` package.

Use [`README.Arch.md`](README.Arch.md) for user-facing behavior, first-run
guidance, telemetry consent, and the current verified/not-verified boundary.
That file is installed as `/usr/share/doc/utilyze/README.Arch.md`.

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
