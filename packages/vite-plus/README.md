# vite-plus

Vite+ 1.0.0 combines a Rust global launcher with the JavaScript web toolchain.
This package builds the launcher from the release tag and installs the published
npm CLI, its dependencies, and platform-native addons alongside it under
`/usr/lib/vite-plus/`. `/usr/bin/vp` points to that launcher. It is not a full
source build of the bundled JavaScript tools or native addons.

## Build And Install

From the repository root:

```bash
(cd packages/vite-plus && makepkg --verifysource && makepkg -si)
```

To build without installing, use `makepkg -f` instead of `makepkg -si`.
The build needs network access for npm dependencies, the pinned Rolldown
checkout, the release's Rust toolchain, and Cargo dependencies. It installs
the Rust toolchain in the builder's rustup state, not in the package payload.

Verify the installed package and bypass any older user-managed `vp` on PATH:

```bash
pacman -Q vite-plus
/usr/bin/vp --version
```

The first `vp` invocation can initialize user-owned managed-runtime shims.
Follow its setup output if you want those shims in your shell. Package
installation does not rewrite shell configuration or migrate projects.

Vite+ 1.0 requires Node.js `^22.18.0 || ^24.11.0 || >=26.0.0`.
The development build was verified with system Node 24.21.0 and npm 12.2.0.
See the [1.0.0 release notes](https://github.com/voidzero-dev/vite-plus/releases/tag/v1.0.0)
and [migration guide](https://viteplus.dev/guide/migrate) before upgrading
existing project dependencies; the global CLI upgrade is not a project migration.

## Managed npm Build Failure

The AUR 1.0.0-2 recipe calls bare `npm` in `prepare()`. When a managed `vp`
shim precedes `/usr/bin` on PATH, that call can use a project-selected runtime
instead of the declared distribution dependency. A clean build failed with
managed Node 22.18.0 / npm 10.9.3:

```text
TypeError: Cannot read properties of null (reading 'edgesOut')
at #loadPeerSet (.../@npmcli/arborist/lib/arborist/build-ideal-tree.js:1289:38)
```

Arborist dereferenced a null `node.parent` while resolving browser/Vitest peers.
The log did not establish which dependency detached the parent.
This recipe scopes that invocation to `PATH="/usr/bin:$PATH" /usr/bin/npm`.
That selects system npm and system Node for its shebang and child processes,
without changing the rest of the build environment.

The corrected recipe built successfully without `--legacy-peer-deps`,
`--force` on npm, checksum bypasses, or a global npm upgrade. Optional
dependencies remain enabled for platform-native addons.
The report and onboarding scope are tracked in
[issue #127](https://github.com/nisavid/arch-pkgs/issues/127).

## Maintenance Baseline

- `authoritative_reference`: [AUR vite-plus](https://aur.archlinux.org/packages/vite-plus)
  release recipe 1.0.0-2 at `a0837aecf917ce328badbfcc9950115bb69d4768`.
  The configured Arch/CachyOS repositories had no exact package match when
  scouted on 2026-10-05; the AUR recipe matches this release-launcher lane.
- `advisory_references`: [Upstream installation](https://viteplus.dev/guide/),
  [1.0.0 release](https://github.com/voidzero-dev/vite-plus/releases/tag/v1.0.0),
  and [migration guide](https://viteplus.dev/guide/migrate). AUR `vite-plus-bin`
  1.0.0-1 and `vite-plus-git` 0.2.9.r7.97d7b62675-1 were scouted but not
  selected: they use binary and VCS lanes respectively.
- `divergence_notes`: Release 1.0.0-3 isolates npm's Node/runtime selection
  from managed PATH shims. Sources, checksums, dependencies, upgrade warning,
  and payload layout follow the reference. No peer-resolution bypass is added.
- `update_notes`: Diff the AUR release recipe first, review upstream release
  and installation docs, refresh both source checksums and `.SRCINFO`, and
  verify the upstream Node requirement against the supported host runtime.
  Run `makepkg --verifysource`, `makepkg --force --cleanbuild`, inspect the
  launcher and JS/native payload, and run the repository consistency gate.
  Exercise builds with managed shims before `/usr/bin`, and verify
  `/usr/bin/vp --version` plus representative project commands after install.

## Validation Boundaries

The x86_64 1.0.0-2 development install passed package-integrity and global
CLI-version checks. The repository's 1.0.0-3 recipe passed fresh source
verification, a clean build, and payload inspection; it has not been installed.
These checks do not establish aarch64 support, compatibility with every managed
runtime, or migration correctness for existing projects.
The npm dependency closure is resolved during `prepare()` without a checked-in
lockfile, so source checksums alone do not guarantee a reproducible JS payload.

This standalone onboarding does not promote the package into the repository's
accepted refresh manifest. A representative project smoke and explicit
artifact acceptance remain gates before refresh publication.
