---
name: maintaining-arch-packages
description: Use when modifying package contents or package-local service/config assets under `packages/*`.
---

# Maintaining Arch Packages

Use this skill when package files under `packages/*` will change.

Do not use it for repo-policy-only, README-only, backlog-only, or review-only turns unless package files will also change.

## Start discovery

For the package you are touching:

1. Read the package directory contents.
2. Read any package-local notes, `README`, or patch comments first.
3. When adding a new package or changing a package baseline, follow
   `docs/policies/reference-packages.md` before writing local package files.
4. Review upstream installation and release documentation.
5. Check Arch/AUR naming, dependency naming, split-package layout, and `systemd` asset placement when the package shape changed.
6. Identify any supporting assets that need to move with the package, such as service files, config defaults, or patches.

## New Package Onboarding

When adding a package under `packages/<name>/`, do the reference-package work
before implementing the local package:

1. Scout Arch, CachyOS, and AUR for same-lane and nearby package recipes.
2. Select an authoritative reference and any advisory references using
   `docs/policies/reference-packages.md`.
3. Inspect selected references for dependency choices, `.install` behavior,
   service units, config defaults, conflicts, optdepends, and maintenance
   comments.
4. Record `authoritative_reference`, `advisory_references`,
   `divergence_notes`, and `update_notes` in `packages/<name>/README.md`.
5. Build the local package around normal Arch package payloads. Avoid networked
   post-install dependency bootstraps.

## Verification workflow

- When build inputs or sources change, regenerate `.SRCINFO`, run `makepkg --verifysource`, then build.
- When the session includes local install verification, prefer `makepkg -si`; otherwise `makepkg -f` is sufficient.
- When the install payload changes, inspect the produced package contents.
- When install or service behavior changes, document the operator command needed to use it.

## Telemetry And Outbound Reporting

When a package includes telemetry, metrics, or other outbound reporting:

- Preserve a privacy-respecting default for distro users.
- Prefer discoverable, reversible consent in the normal UX over package-only environment variables or doc-only instructions when that can be done with a small, maintainable patch.
- Persist the user's choice in the tool's normal config system when one exists. If the tool has no config yet, prefer an XDG-aligned config location under `${XDG_CONFIG_HOME:-~/.config}/<app>/`.
- Keep the patch aligned with upstream config, UI, and code patterns so it remains a plausible upstream PR if the authors later want an opt-in posture too.
- If that is not practical within the current patch surface, document the tradeoff explicitly and choose the least invasive temporary behavior.
