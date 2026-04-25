# electron41

Source-built Arch package for Electron 41.

Use this package when a local application needs the Electron 41 runtime from
pacman rather than the prebuilt upstream zip packages.

## Package Contents

- `electron41` launcher in `/usr/bin`
- Electron runtime under `/usr/lib/electron41`
- Electron and Chromium license files under `/usr/share/licenses/electron41`

## Source Policy

The package tracks Electron stable `41.x` releases. The current package is
`41.3.0-1`, prepared from the upstream `v41.3.0` tag and generated Chromium
dependency pins for Chromium `146.0.7680.188` and Node.js `24.15.0`.

The source recipe is based on the current Arch/CachyOS `electron39` package
shape, with the generated dependency list refreshed for Electron 41. Advisory
binary-package context comes from the AUR `electron41-bin` package, but this
package is intentionally source-built.

## Install

This is a heavyweight source package. Source verification checks the Electron
tag archive plus the local patch and helper inputs. Chromium and Electron
dependency pins come from upstream `DEPS` and are fetched shallowly during
`prepare()`, so the build still needs substantial disk, network, and time even
though it avoids a full Chromium mirror clone. CIPD, npm, and yarn inputs are
also resolved during `prepare()`, so this is not an offline build from the
declared `source=()` array alone. `prepare()` installs the Rust toolchain pinned
by the package into package-local `RUSTUP_HOME` and `CARGO_HOME` directories
under `$srcdir`; air-gapped builders must provide those runtime inputs ahead of
time.

For a one-off local install:

```bash
makepkg --verifysource
makepkg -si
```

For the repeatable local-repo workflow, build this package, refresh the `nisavid`
repo, and install `electron41` through pacman. See
[`docs/usage/local-repo.md`](../../docs/usage/local-repo.md).

## Validation Status

The package metadata, generated `.SRCINFO`, source verification, source build,
and package payload inspection have been checked locally for `41.3.0-1`.
Electron source builds download a large Chromium dependency graph and need a
long-running build environment.
