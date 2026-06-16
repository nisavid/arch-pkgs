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

- `authoritative_reference`: AUR `thorium-browser-updated`
- `advisory_references`: AUR `thorium-browser-bin`,
  `thorium-browser-avx-bin`, `thorium-browser-avx2-bin`, upstream Thorium
  release notes, and Chromium source release/build notes
- `divergence_notes`:
  - This package tracks the fixed local AUR working recipe for
    `149.0.7827.114-4`.
  - This package uses the reachable Thorium tag
    `M149.0.7827.114-updated`.
  - This package uses the official Chromium source tarball instead of a full
    Chromium git checkout.
  - This package keeps the build-time compatibility patches needed for the
    Thorium setup scripts, Chromium media defaults, GN args, and RPM staging
    assumptions.
- `update_notes`:
  - Diff AUR `thorium-browser-updated` before changing the source, dependency,
    or install behavior.
  - Recheck Thorium tag reachability and Chromium source tarball availability
    before updating `.SRCINFO`.
  - Keep source download, full build, and package payload inspection as explicit
    validation work because Chromium/Thorium builds are expensive.

## Verification

Metadata-only verification for this ingest:

```bash
env -u 'BASH_FUNC_ml%%' -u 'BASH_FUNC_module%%' makepkg --printsrcinfo > .SRCINFO
git ls-remote --tags https://github.com/brauliobo/thorium.git refs/tags/M149.0.7827.114-updated
curl -L -I --fail --max-time 20 https://commondatastorage.googleapis.com/chromium-browser-official/chromium-149.0.7827.114.tar.xz
```

Full package validation requires `makepkg --verifysource`, `makepkg -f` or
`makepkg -si`, and package payload inspection.
