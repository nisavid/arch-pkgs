# Open WebUI 0.11.0 offline package checkpoint

## Disposition

The package-owned offline-input, source-verification, build, and payload-
inspection gate passed for `open-webui` `0.11.0-3`. The resulting package is
not accepted for installation, publication, promotion, or deployment. Issue
[#68](https://github.com/nisavid/arch-pkgs/issues/68) remains open, and #69
remains blocked.

## Reviewed source and build inputs

The build used `arch-pkgs` commit
`44223148ba1825c048e06865f458ddd58c05450c`. Its Open WebUI recipe binds 28
sources and 28 SHA-256 checksums.

The two large package-owned dependency graphs are immutable prerelease assets
at
[`open-webui-0.11.0-offline-closures-v1`](https://github.com/nisavid/arch-pkgs/releases/tag/open-webui-0.11.0-offline-closures-v1):

- the 1,233-tarball npm closure is `886706456` bytes, SHA-256
  `6238b436c6669a311623d97724c6b2ada0e77090d0e5219860acc38c53fb32b1`;
- the 222-wheel CPython 3.14/Linux x86_64 closure is `144877017` bytes,
  SHA-256
  `bcd3c5c651fc42e8e5a73a4c81f4b5760e82f6b39eb714caf999700bad4ed27c`.

Both archives were independently reproduced byte-for-byte. Their package
helpers verify the full member set, source-lock identity, digests, target wheel
names and tags, canonical archive metadata, and safe extraction shape.
The immutable input release targets the earlier source checkpoint
`54d8505614da17709cf99ffd7706ba9e957647da`; the later pkgrel-3 source commit
above consumes those unchanged assets.

## Cold verification and no-egress build

A cold Git archive of the reviewed commit began without local ignored source
files. `makepkg --verifysource` fetched the prerelease assets from their public
URLs and passed all 28 checksums.

The complete package then built with `makepkg -f --nodeps --cleanbuild` inside
a Bubblewrap network namespace with no network access. The frontend consumed
only the seeded npm cache, and the server closure consumed only the extracted
wheelhouse in offline/no-index mode.

The host filesystem was read-only. Only the disposable package root was
writable; device, process, runtime, temporary, and home paths were fresh
namespace mounts. The build and start directory recorded in `.BUILDINFO` is
the generic `/var/tmp`, not a host-specific path. A complete local review
transcript is `377082` bytes, SHA-256
`7de0c293c32b128449f1d60863638e2dbd69ae0f8bb99e7061f20e6475f7f636`;
its body is not part of the public record.

This was not a clean-chroot build. It used the host toolchain, an independently
extracted signed Node 22.23.2 package, and the exact built RapidOCR 3.9.2
package metadata required by the unchanged external-provider verifier. Because
dependency installation was deliberately skipped, this result does not prove
the complete Arch dependency environment or package byte reproducibility. Its
public-safe `.BUILDINFO` records the non-clean host package inventory and is
not minimal-chroot provenance.

## Package inspection

The resulting archive is
`open-webui-0.11.0-3-x86_64.pkg.tar.zst`, `240012544` bytes, SHA-256
`10c5ef31da980f9fcef7a8fd0ed9416b1ce21ac42f6df54eb65ea1eec836860f`.
Its installed-size declaration is `864287174` bytes. The archive contains
28,087 members, including 5,588 frontend entries and the exact 60-file Pyodide
payload.

Inspection confirmed:

- all 21 pacman-owned ML/native provider distributions are absent from the
  installed server-side private Python closure and its top-level import roots;
- the separate browser-side Pyodide payload contains 46 wheels, including the
  expected `numpy`, `pandas`, `pillow`, `scikit-learn`, and `scipy` WebAssembly
  wheels; those are not server provider distributions or an authority boundary;
- the provider-boundary verifier passes against the exact RapidOCR package
  metadata;
- the Unix-socket wrapper, hardened systemd unit, environment defaults,
  sysusers/tmpfiles assets, one-shot administrator helper, forward-only session
  epoch helper, fail-closed RAG gate, and license set are present with their
  declared modes and owners;
- npm caches, the wheelhouse, offline closure archives, materializers,
  `node_modules`, build homes, the uv install lock, and all dist-info
  `uv_cache.json` files are absent; and
- the archive has no symlinks, build-host paths in its package metadata,
  bundled server-side external-provider roots, or embedded credential values
  in the package-owned service and configuration assets.

The deterministic whole-archive inspection receipt is
[`evidence/open-webui-offline-package-inspection-2026-08-19.json`](evidence/open-webui-offline-package-inspection-2026-08-19.json),
SHA-256
`531d16e2097181ec8f93e01adac3d091519b94aaf9d267763289effe1777510d`.
It binds all 28,087 members through a sorted canonical manifest digest without
publishing the package itself or a redundant full path listing.

The package archive is not publicly retained. The prerelease contains only the
two immutable build-input closures.

## Provider frontier

The selected-logit reranking adapter is present in the current Lemonade fork,
but no coherent 11.6 Lemonade/llama.cpp five-package family has landed in
`arch-strix-halo-pkgs`. The current boundary and exact port failures are
recorded in
[`lemonade-provider-port-status-2026-08-19.md`](lemonade-provider-port-status-2026-08-19.md).
The remaining provider work is owned by
[`#105`](https://github.com/nisavid/arch-strix-halo-pkgs/issues/105),
[`#112`](https://github.com/nisavid/arch-strix-halo-pkgs/issues/112), and
[`#113`](https://github.com/nisavid/arch-strix-halo-pkgs/issues/113).

The integrated measurement was not run. Starting it against the historical
10.7/b9442 package family or an unpackaged moving fork would produce evidence
for the wrong subject.

## Next gate

Freeze and package one coherent Lemonade 11.6 and common llama.cpp family,
including the zembed role-aware input contract and zerank selected-logit
adapter. Then run the accepted disposable start, provider-failure, restore,
rollback, and generation trials against this exact Open WebUI package source.

No package was installed, activated, added to a pacman repository, promoted,
or deployed in this checkpoint.

## Machine-readable evidence

The public-safe record is
[`evidence/open-webui-offline-package-build-2026-08-19.json`](evidence/open-webui-offline-package-build-2026-08-19.json),
SHA-256
`731cae04ba482926f532b48c31177a223f17300b1582ba07f5c2b549733bf9a7`.
