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
    `149.0.7827.155-4`.
  - This package uses the reachable Thorium tag
    `M149.0.7827.155-updated`.
  - This package uses the official Chromium source tarball instead of a full
    Chromium git checkout.
  - This package keeps the build-time compatibility patches needed for the
    Thorium setup scripts, Chromium media defaults, GN args, and RPM staging
    assumptions.
  - This package disables Chrome PGO and V8 builtins PGO for source-tarball
    builds instead of requiring unavailable Chromium profile artifacts.
  - The intermediate Thorium RPM build uses package-local RPM temp and database
    paths and avoids ownership preservation so `makepkg` can run without
    `/var` writes or host-specific ownership restoration.
- `update_notes`:
  - Diff AUR `thorium-browser-updated` before changing the source, dependency,
    or install behavior.
  - Recheck Thorium tag reachability and Chromium source tarball availability
    before updating `.SRCINFO`.
  - Keep source download, full build, and package payload inspection as explicit
    validation work because Chromium/Thorium builds are expensive.

## Verification

Thorium updates require full package validation before merge:

```bash
makepkg --verifysource
makepkg -f
bsdtar -tf thorium-browser-updated-*.pkg.tar.*
```

After building, run a bounded browser smoke with the packaged
`/usr/bin/thorium-browser` wrapper or the built `/opt/thorium-browser` payload.
