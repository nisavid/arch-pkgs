# utilyze on Arch

> [!WARNING]
> This is an experimental first release. The package builds and the Arch-specific
> patches have targeted tests, but a supported NVIDIA host has not completed the
> full runtime validation pass yet.

This package installs `utilyze`, an NVIDIA GPU utilization TUI, for local Arch
systems. It also carries Arch-specific patches for CUDA paths, startup behavior,
configuration, upstream update messaging, and telemetry consent.

## Who Should Use It

Use this package if you have:

- Linux `x86_64`
- An NVIDIA Ampere-or-newer GPU
- A working CUDA/NVIDIA runtime stack
- Permission to run the TUI with `sudo` or an explicit host capability policy

Do not treat this release as fully accepted for unattended monitoring yet. In
the source repository, the remaining validation work is tracked in
`docs/backlog.md`.

## Current Status

Verified for this package release:

- Source verification completed.
- Package build completed.
- Package payload shape checked.
- `utlz --version` works.
- Startup reaches the patched runtime checks in a sanitized environment without
  relying on `/usr/local/cuda*` fallbacks.
- XDG-style system and user config loading/saving is covered by package
  `check()` tests.
- Telemetry consent state, reporter gating, and consent-row key handling are
  covered by package `check()` tests.

Still pending:

- Dependency-satisfied sampling on a supported NVIDIA host.
- Runtime validation under representative GPU workloads.
- Interactive validation of the live telemetry consent row.
- Long-running validation of telemetry consent persistence across root and
  non-root sessions.
- Repeatable TUI acceptance coverage.

## First Run

The safe default is:

```bash
sudo utlz
```

Package installation does not relax NVIDIA profiling permissions or grant Linux
capabilities. Those choices belong to the local administrator.

If you intentionally want to run without `sudo`, you may grant the binary
`CAP_SYS_ADMIN`:

```bash
sudo setcap cap_sys_admin+ep /usr/bin/utlz
```

Package upgrades replace the binary, so reapply `setcap` after each upgrade.

If your host also needs driver-side profiling permissions, review local policy
before adding an NVIDIA module override:

```bash
echo 'options nvidia NVreg_RestrictProfilingToAdminUsers=0' | sudo tee /etc/modprobe.d/nvidia-profiling.conf
```

That module setting usually needs a reboot. NVIDIA also documents a no-reboot
path, but it unloads and reloads the driver stack:

```bash
sudo modprobe -rf nvidia_uvm nvidia_drm nvidia_modeset nvidia && sudo modprobe nvidia
```

## Arch-Specific Behavior

- Upstream self-update messaging is disabled in the Arch build.
- Outbound telemetry is disabled until the effective user explicitly accepts it
  in the TUI.
- `UTLZ_DISABLE_METRICS=1` remains a hard disable for the current session and
  suppresses the consent row.
- `UTLZ_BACKEND_URL` only overrides the backend URL. It never enables telemetry
  by itself.
- Utilyze reads system and user config from XDG-style config locations.

## Telemetry Consent

On the first undecided run, Utilyze shows a one-line consent row in the second
SOL header row:

- `a` accepts telemetry and persists `telemetry.enabled = true`
- `x` rejects telemetry and persists `telemetry.enabled = false`
- `esc` dismisses the prompt for the current session only

If saving the choice fails, Utilyze applies the choice for the current session
and shows a timed inline warning. The next launch falls back to the last
persisted state.

The current flow does not include an in-app reversal control. To change or clear
the stored preference, edit or remove the effective user's config file, then
start `utlz` again.

## Config Files

Utilyze reads config from:

```text
/etc/xdg/utilyze/config.toml
${XDG_CONFIG_HOME:-~/.config}/utilyze/config.toml
```

If `XDG_CONFIG_DIRS` is set, Utilyze reads `utilyze/config.toml` under each
listed system config directory instead of only `/etc/xdg`.

System config sets host-wide defaults. User config overrides system config.
Utilyze writes only the effective user's config file. If you launch `utlz` with
`sudo`, the consent file is usually stored under root's config directory.

Admins can set a host-wide default in `/etc/xdg/utilyze/config.toml`:

```toml
[telemetry]
enabled = false
```

## Reference

This document is installed to `/usr/share/doc/utilyze/README.Arch.md`.
