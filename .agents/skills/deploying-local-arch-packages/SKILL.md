---
name: deploying-local-arch-packages
description: Use when package changes in this repo need a host handoff, rebuild, install, reinstall, or post-change verification.
---

# Deploying Local Arch Packages

Use this skill when a package in this repo has changed and the user needs the exact command to build or install it locally.

## Completion rule

If package files changed and the package was not installed during the session, the final response must include the exact command needed to build and install the changed package from this repo.

## Default workflow

1. Verify the package with `makepkg --verifysource`.
2. Build it with `makepkg -f` or install it with `makepkg -si`.
3. If the install is handed off to the user, give the exact command using the package directory under `packages/`.
4. If the package ships a `systemd` service, include the enable/start command when relevant.

## Accepted artifact boundary

`makepkg -si` is a development install. When
`orchestrating-arch-package-refreshes` has advanced a lane to acceptance or
production deployment, install the digest-bound candidate archive at acceptance
or the exact promoted artifact identity served by the verified published
repository in production. A matching version is not identity evidence. Do not
rebuild at either boundary, and verify the resulting installed identity.

At acceptance, record the expected archive SHA-256 and literal archive path,
verify that digest immediately before the package transaction, install those
bytes without rebuilding, and run the lane's installed-payload and runtime
verifier against that accepted identity. At production, first materialize the
archive served by the verified published repository, prove that its SHA-256
matches the promotion record, install those exact bytes, and run the lane's
production verifier against the same identity. A repository manifest, package
name, or version alone does not prove installed identity.

Each lane or explicitly coupled deployment ticket must name the verifier and
the installed payload or runtime evidence it emits. If no verifier can bind the
installed state to the accepted archive digest, preserve the current state and
open a tooling ticket; do not advance the acceptance or production milestone.

Keep acceptance deployment and production deployment as separate handoffs. Use
`handling-privileged-steps` for package installation, service mutation, paid
providers, or live-host work, and verify the resulting installed identity after
the operator completes the authorized action.

## Examples

- `cd packages/qdrant && makepkg -si`
- `cd packages/hayhooks && makepkg -si`

## Notes

- Keep commands copy-pasteable.
- Do not assume a local pacman repo workflow unless the user asks for one.
