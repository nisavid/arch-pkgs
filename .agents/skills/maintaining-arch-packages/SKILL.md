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
3. Review upstream installation and release documentation.
4. Check Arch/AUR naming, dependency naming, split-package layout, and `systemd` asset placement when the package shape changed.
5. Identify any supporting assets that need to move with the package, such as service files, config defaults, or patches.

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
