# utilyze on Arch

> [!WARNING]
> Experimental first release. This package is intentionally documented as a narrow, partially verified first cut. The sections below separate what has been verified for the package itself from what still needs supported-host runtime validation.

This Arch build packages `utilyze` for local use on NVIDIA systems.

## Current state

### Implemented and verified

- Source verification completed.
- Package build completed.
- Package payload shape checked.
- `utlz --version` works.
- Startup reached the patched runtime checks in a sanitized environment without relying on `/usr/local/cuda*` fallbacks.
- XDG-style system and user config loading/saving is covered by package `check()` tests.
- Telemetry consent state, reporter gating, and consent-row key handling are covered by package `check()` tests.

### Implemented but not fully verified

- No supported NVIDIA host has completed a dependency-satisfied sampling session for this package release yet.
- No real workload validation has been completed for this package release yet.
- No supported-host interactive validation has been completed for the live telemetry consent row yet.
- No long-running host validation has been completed for telemetry consent persistence across root and non-root sessions yet.

### Planned but not implemented

- Supported NVIDIA-host validation for the packaged runtime.
- Repeatable interactive acceptance coverage for the TUI.
- Richer runtime validation against representative workloads.

## Floor

- Linux `x86_64`
- NVIDIA Ampere or newer
- CUDA / NVIDIA runtime stack available on the host

## Safe default

Use the packaged binary through `sudo utlz` unless you have explicitly chosen another privilege model.

## Optional admin choices

This package does not auto-configure NVIDIA profiling permissions.

If you want to avoid `sudo`, an admin may choose to grant the binary capabilities with `setcap`.
That is a deliberate host policy choice, not a package default.

```sh
sudo setcap cap_sys_admin+ep /usr/bin/utlz
```

If your host needs driver-side profiling permissions, an admin may also choose to add a matching `modprobe.d` override.
That is separate from package installation and should be reviewed against local policy.

```sh
echo 'options nvidia NVreg_RestrictProfilingToAdminUsers=0' | sudo tee /etc/modprobe.d/nvidia-profiling.conf
```

That module setting may require a reboot to take effect. NVIDIA also documents a no-reboot path, but it is disruptive because it unloads and reloads the driver stack:

```sh
sudo modprobe -rf nvidia_uvm nvidia_drm nvidia_modeset nvidia && sudo modprobe nvidia
```

Package upgrades replace the binary, so capability-based setups may need `setcap` to be applied again after each upgrade.

## Arch-specific behavior

- Upstream self-update messaging is disabled in the Arch build.
- Outbound telemetry is disabled until the effective user explicitly accepts it in the Utilyze TUI.
- `UTLZ_DISABLE_METRICS=1` is still a hard disable for that session and suppresses the consent row.
- `UTLZ_BACKEND_URL` remains a backend override only. It never enables telemetry by itself.
- Utilyze reads system and user config from XDG-style config locations.

## Config files

Utilyze reads config from:

```text
/etc/xdg/utilyze/config.toml
${XDG_CONFIG_HOME:-~/.config}/utilyze/config.toml
```

If `XDG_CONFIG_DIRS` is set, Utilyze reads `utilyze/config.toml` under each listed system config directory instead of only `/etc/xdg`.

System config sets host-wide defaults. User config overrides system config. Utilyze writes only the effective user's config file.

## First run

Start with:

```sh
sudo utlz
```

On the first undecided run, Utilyze shows a one-line inline consent row in the second SOL header row:

- `a` accepts telemetry and persists `telemetry.enabled = true`
- `x` rejects telemetry and persists `telemetry.enabled = false`
- `esc` dismisses the prompt for the current session only

If saving the choice fails, Utilyze still applies that choice for the current session and shows a timed inline warning. The next launch falls back to the last persisted state.

If you have chosen capability-based access, reapply your `setcap` command after upgrades before running `utlz` without `sudo`.

## Telemetry preference storage

The Arch patch stores telemetry consent per effective user in:

```text
${XDG_CONFIG_HOME:-~/.config}/utilyze/config.toml
```

If you launch `utlz` with `sudo`, the consent file is stored for the effective user running the process, which is usually `root`.

Admins can set a default in `/etc/xdg/utilyze/config.toml`:

```toml
[telemetry]
enabled = false
```

The current v1 flow does not provide an in-app reversal control. To change or clear the stored preference, edit or remove the user's config file above, then start `utlz` again.

## Reference

This doc is installed to `/usr/share/doc/utilyze/README.Arch.md`.
