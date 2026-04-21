---
name: maintaining-arch-packages
description: Use when updating, auditing, or extending this repo's package set.
---

# Maintaining Arch Packages

Use this skill when changing packages in this repo.

## Start discovery

For the package you are touching:

1. Read the package directory contents.
2. Review upstream installation and release documentation.
3. Compare against Arch or AUR conventions where helpful.
4. Identify any supporting assets that need to move with the package, such as service files, config defaults, or patches.

## Default package-update loop

1. Update the package sources and metadata.
2. Update package assets and defaults.
3. Regenerate `.SRCINFO`.
4. Run `makepkg --verifysource`.
5. Run `makepkg -f`.
6. Inspect the produced package contents if the install payload changed.
7. Document the install command for the operator if the package was not installed during the session.

## Guardrails

- Prefer packaged defaults that are safe on a generic local system.
- Do not bake machine-local secrets or paths into committed files.
- Keep commits scoped to one logical package or policy change when possible.
