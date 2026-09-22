# Backlog

This doc points to where follow-up work for this repo is tracked. The GitHub
tracker owns plans, status, and acceptance; this page is only an index.

## Package refresh

Active package-lane work lives in the refresh map
[Execute the accepted Arch package refresh](https://github.com/nisavid/arch-pkgs/issues/46).
Each package's current disposition and next gate are in the checked
[refresh index](../packages/README.md#refresh-index).

## utilyze

`utilyze` is packaged and partially verified but deferred. It is NVIDIA-only
and cannot be validated on the host, so its lane waits behind
[Resume the utilyze lane when NVIDIA validation is available](https://github.com/nisavid/arch-pkgs/issues/84).

The selected validation rig stays documented in
[`docs/maintainers/utilyze-nvidia-validation-rig.md`](maintainers/utilyze-nvidia-validation-rig.md).
See [`packages/utilyze/README.Arch.md`](../packages/utilyze/README.Arch.md) for
the installed user-facing status and first-run guidance.

## Repo workflow tooling

`amerge` is not part of this repo workflow yet. The current install path is the
explicit build, refresh, publish, and install sequence in
[`docs/usage/local-repo.md`](usage/local-repo.md).

Adopting a shared `amerge` package and declarative package maintenance is
seeded in
[Chart declarative package maintenance and amerge adoption](https://github.com/nisavid/arch-pkgs/issues/17).
