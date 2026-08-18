---
name: deploying-local-arch-packages
description: Use when package changes in this repo need a host handoff, rebuild, install, reinstall, or post-change verification.
---

# Deploying Local Arch Packages

Use this skill when a package in this repo has changed and the user needs the exact command to build or install it locally.

## Completion rule

For a standalone development install, if package files changed and the package
was not installed during the session, the final response must include the exact
command needed to build and install the changed package from this repo. For an
orchestrated acceptance or production deployment, include the assigned
digest-bound artifact handoff and installation command instead; do not
substitute a rebuild command.

## Default workflow

Use this workflow only for a standalone development build or install. For a
repository-wide or multi-lane refresh, enter
`orchestrating-arch-package-refreshes` first and use this skill only after that
lifecycle assigns the package mechanics; do not use `makepkg -si` to bypass
candidate acceptance or promotion.

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

Before hashing or installing at either boundary, use
`handling-privileged-steps` to copy or reflink the archive into a fresh
transaction directory under a root-owned staging root that the invoking UID
cannot write. The transaction directory must be owned by `root:root` with mode
`0700`. The staged archive must be a regular, non-symlink file owned by
`root:root`, have mode `0400`, and have a link count of exactly one. Never hand
pacman a user-owned path or a path whose directory or archive the invoking UID
can rename, replace, link, or modify.

After materialization, record the archive's canonical path, device, inode,
size, UID, GID, mode, link count, and SHA-256. Immediately before invoking
pacman, require that complete tuple and digest to match, then install the same
literal path without rebuilding or yielding the privileged transaction. Keep
the directory and archive ownership and modes unchanged until the package
transaction and lane verifier finish, then recheck the tuple and SHA-256. Any
mismatch preserves the current lifecycle milestone and fails the handoff
closed.

At acceptance, require the handoff SHA-256 to equal the candidate record. At
production, materialize the archive served by the verified published
repository into a new handoff and require its SHA-256 to equal the promotion
record. Pass that expected and observed digest to the lane's installed-payload
and runtime verifier so its evidence binds to the same archive identity. A
repository manifest, package name, or version alone does not prove installed
identity.

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
