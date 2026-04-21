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

## Examples

- `cd packages/qdrant && makepkg -si`
- `cd packages/hayhooks && makepkg -si`

## Notes

- Keep commands copy-pasteable.
- Do not assume a local pacman repo workflow unless the user asks for one.
