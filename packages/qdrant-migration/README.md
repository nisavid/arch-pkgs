# qdrant-migration

Retained Qdrant `1.18.3` binary for the mandatory consecutive-minor migration
between an observed `1.17.1` deployment and the maintained `1.19.0` service.
This package is a preservation tool, not a second active Qdrant producer.

## Maintenance Baseline

- `authoritative_reference`: AUR
  [`qdrant` commit `51762d7`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=qdrant&id=51762d7ed828dfc25be633b4f0ca336d546ec81f)
  `1.18.3-1` source-build recipe.
- `advisory_references`: upstream Qdrant
  [`1.18.3` release](https://github.com/qdrant/qdrant/releases/tag/v1.18.3),
  [upgrade guidance](https://qdrant.tech/documentation/upgrades/), and
  [migration and recovery guidance](https://qdrant.tech/documentation/migration-recovery-options/).
- `divergence_notes`: the package installs only the versioned binary at
  `/usr/lib/qdrant/migration/qdrant-1.18.3`, its generated SPDX manifest, and
  its license. It deliberately ships no service, configuration, state
  directories, or `/usr/bin/qdrant`.
- `update_notes`: this identity is immutable while the `1.17.1 -> 1.18.3 ->
  1.19.0` recovery route remains supported. Verify the pinned tag, commit, and
  archive hash; regenerate `.SRCINFO`; clean-build and inspect the artifact;
  then rerun the disposable migration, corruption-rejection, restore, and
  rollback gates before replacing or retiring it.

Relative to the AUR `1.18.3-1` recipe, this package adds `jq` and pinned
`cargo-sbom` source to the build, uses locked Cargo fetches and builds, applies
the AWS-LC jitter workaround, remaps build paths, retains upstream's Rust fat
LTO while disabling makepkg-added native GCC LTO, and emits a canonical SPDX
manifest. It relocates the binary to the versioned migration path and installs
only that binary, the manifest, and the upstream license.

## Pinned Identity

- version: `1.18.3`
- annotated tag object: `3ea8cf7ce633256fb1b2a75b0de9d9ce60b22254`
- GitHub-verified commit: `db8fa43fcb6aedec1e739487e17a99731b74590a`
- source archive SHA-256:
  `c5f918b4f37279ec00b22b718ca54bca7b43c9d17628b28b8eba363beceb0c96`
- SBOM generator: `cargo-sbom` `0.10.0`, source SHA-256
  `4ffe4b49660f4f4331fb5efcf7074a318b10f5f8fd75e42351a7ca32c58c2723`

The recipe canonicalizes the generated SPDX document and derives its timestamp
and namespace from the exact Qdrant source identity, so the installed manifest
is reproducible across fresh build roots.

The annotated tag carries a valid PGP signature verified by GitHub, and the
release commit is also GitHub-verified. The independently reproduced archive
hash recorded above remains the exact source-byte boundary.

## Build And Inspect

```bash
makepkg --verifysource
makepkg -f
bsdtar -tf qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst
bsdtar -xOf qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst \
  usr/share/qdrant/migration/qdrant-1.18.3.spdx.json | jq -e \
  '.spdxVersion == "SPDX-2.3" and any(.packages[]; .name == "qdrant" and .versionInfo == "1.18.3")'
```

The payload must contain only the versioned migration binary, SPDX manifest,
license, and normal pacman metadata. It must not install an unversioned
executable, service, configuration, secret, or state path.

## Use And Retention Boundary

Never run this binary concurrently with another Qdrant binary against the same
storage. Never use it to open storage already migrated by `1.19.0`. Rollback
pairs a retained binary and configuration with its matching untouched state,
cold copy, or compatible snapshot; binary downgrade alone is not rollback.

Before any live use, freeze every writer and follow the repository's Qdrant
migration runbook. Retain the `1.17.1`, `1.18.3`, and `1.19.0` artifacts plus
their matching recovery evidence until a post-cutover `1.19` snapshot restores
successfully and the deployment has run cleanly for seven days. Removing those
anchors requires separate explicit approval.
