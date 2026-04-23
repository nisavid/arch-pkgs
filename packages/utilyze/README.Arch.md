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

### Implemented but not fully verified

- No supported NVIDIA host has completed a dependency-satisfied sampling session for this package release yet.
- No real workload validation has been completed for this package release yet.
- No interactive TUI acceptance validation has been completed for this package release yet.

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
- Outbound metrics are disabled by default in the Arch build.
- Opt in to metrics only by setting `UTLZ_ENABLE_METRICS=1` in the environment.

```sh
UTLZ_ENABLE_METRICS=1 sudo utlz
```

## First run

Start with:

```sh
sudo utlz
```

If you have chosen capability-based access, reapply your `setcap` command after upgrades before running `utlz` without `sudo`.

## Reference

This doc is installed to `/usr/share/doc/utilyze/README.Arch.md`.
