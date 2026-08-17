# thorium-browser-updated

Arch source-build package for Thorium Browser.

Use this package when you want Thorium built from source with the fixed
Chromium tarball and Thorium release tag recipe.

## Package Contents

- `thorium-browser-updated` package recipe
- `.SRCINFO` metadata
- `thorium-browser-updated.install` post-install and post-upgrade reminder
- `/usr/bin/thorium-browser` wrapper reading `~/.config/thorium-flags.conf`

## Maintenance Baseline

- `authoritative_reference`: AUR `alacrium-browser`, the primary Arch-facing
  reference for the selected source-built Alacrium successor lane
- `advisory_references`: upstream Alacrium release and build documentation, AUR
  `alacrium-browser-bin`, and same-version Arch Chromium packaging
- `divergence_notes`:
  - The current package is Thorium `149.0.7827.114-4` at tag
    `M149.0.7827.114-updated`. The selected maintained lane is the independent
    Alacrium fork, researched at `M151.0.7922.108`; implementation must still
    freeze the newest eligible release aligned with current Chromium stable and
    its security fixes.
  - The successor package and executable are `alacrium-browser`, with AVX as an
    explicit minimum. It replaces and conflicts with
    `thorium-browser-updated` only after acceptance, provides no Thorium alias,
    and never automatically reads, moves, converts, or deletes the Thorium
    profile.
  - Re-derive named, context-checked patches against the frozen Alacrium and
    Chromium sources rather than wholesale-porting the current Thorium patch
    set. Capture every build input in an immutable offline source bundle.
  - Ship separate normal and experimental launch contracts over the same
    browser with isolated profiles, caches, flags, and desktop identities, plus
    the selected privacy and security defaults and no package-owned updater.
- `update_notes`:
  - Keep this lane deferred and excluded from publication, and preserve the
    Thorium source/profile evidence, until the Alacrium successor passes all
    G0-G4 gates. The researched release cursor is not acceptance.
  - G0 must freeze the newest eligible release, verify Chromium security
    alignment with no known missing critical or high fix, and complete the
    immutable source manifest, dependency/license review, patch review, and
    offline bundle.
  - G1 must produce two clean networking-disabled builds from that bundle in
    the specified Arch x86_64 AVX environment and explain their structural
    differences while staying within the build resource ceilings.
  - G2 must inspect payload, ownership, modes, licenses, SBOM, privileges,
    update behavior, sandbox layers, the single expected mode-4755
    `chrome-sandbox`, and absence of undeclared services, downloads, forced
    extensions, capabilities, and host mutation.
  - G3 must prove isolated normal and experimental launchers on Wayland and
    X11, profile separation, sandbox health, media/PDF/WebRTC/VA-API behavior,
    downloads, desktop/MIME integration, extension installation, and clean
    removal.
  - G4 must pass egress and privacy checks, package and runtime resource
    ceilings, profile/cache growth checks, replacement behavior, Thorium-profile
    preservation, deployment recovery, and package rollback before Thorium is
    retired.

## Verification

Metadata-only verification for this ingest:

```bash
env -u 'BASH_FUNC_ml%%' -u 'BASH_FUNC_module%%' makepkg --printsrcinfo > .SRCINFO
git ls-remote --tags https://github.com/brauliobo/thorium.git refs/tags/M149.0.7827.114-updated
curl -L -I --fail --max-time 20 https://commondatastorage.googleapis.com/chromium-browser-official/chromium-149.0.7827.114.tar.xz
```

Full package validation requires `makepkg --verifysource`, `makepkg -f` or
`makepkg -si`, and package payload inspection.
