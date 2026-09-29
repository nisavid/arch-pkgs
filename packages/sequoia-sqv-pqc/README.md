# sequoia-sqv-pqc

This opt-in recipe builds Sequoia `sqv` 1.5.0 with the OpenSSL PQC backend and
an exact `sequoia-openpgp` 2.4.1 lock. It provides `sequoia-sqv=1.5.0`,
conflicts with `sequoia-sqv`, and is not co-installable with the classical
package.

The recipe remains a deferred Hatchery qualification input tracked in
[dotfiles issue #148](https://github.com/nisavid/dotfiles/issues/148). It does
not authorize installation, signing, publication, or production key use.

## Maintenance Baseline

- `authoritative_reference`: [Official Arch sequoia-sqv 1.5.0-1 recipe](https://gitlab.archlinux.org/archlinux/packaging/packages/sequoia-sqv/-/blob/eb5a3879721caa3a52ae80ff055c0324640340c0/PKGBUILD), packaging commit `eb5a3879721caa3a52ae80ff055c0324640340c0`: the matching x86_64 signed-tag Cargo source-build reference for upstream v1.5.0 at `e0dbf9133a1bf605eb2ead3869d9722d8dfc8252`. This opt-in lane selects OpenSSL instead of the reference backend.

- `advisory_references`: [CachyOS sequoia-sqv rebuild metadata](https://packages.cachyos.org/package/cachyos-extra-v3/x86_64_v3/sequoia-sqv); [upstream target manifest and source](https://gitlab.com/sequoia-pgp/sequoia-sqv/-/tree/e0dbf9133a1bf605eb2ead3869d9722d8dfc8252); and [Sequoia OpenPGP 2.4.1 backend documentation](https://gitlab.com/sequoia-pgp/sequoia/-/blob/0b0c8c7f038b829de2da0d28a822941d8600f3ee/openpgp/README.md). The 2026-09-19 AUR search and named queries returned no corresponding SQ/SQV stable, git, or pqc package; sequoia-wot and sequoia-octopus-librnp variants were inspected as other application lanes.

- `divergence_notes`: Opt-in sequoia-sqv-pqc provides sequoia-sqv=1.5.0 and conflicts with the classical package. The recipe asserts the reviewed application commit, applies the checked-in exact OpenPGP 2.4.1 lock patch, disables default Nettle features, selects crypto-openssl, and requires openssl>=3.5 with libcrypto.so=3-64 and libssl.so=3-64. It retains the ordinary Arch executable/completion payload and uses build-path remapping. Package release 4 is deferred source with no new archive identity. SQV fixes the completion output location, installs the upstream README, and records LGPL-2.0-or-later from the target manifest rather than Arch/CachyOS GPL metadata.

- `update_notes`: Keep this release-4 source lane deferred and publication-ineligible. Before changing its target, recheck Arch, CachyOS, AUR, and upstream manifests/release notes; preserve or explicitly review the pinned source commit, lock patch, backend, dependencies, and package relationship. Regenerate and compare .SRCINFO, run repository source checks, then use the maintained Hatchery procedure in a fresh staged run for separately authorized source verification, full checked build, payload/path inspection, and new archive/executable identities. Operation, macOS interoperability, installation, rollback-authenticity, and independent acceptance remain separate gates; see the [maintained procedure and gates](../../docs/maintainers/sequoia-pqc-variants.md).

Stage a clean reviewed revision using the
[maintainer guide](../../docs/maintainers/sequoia-pqc-variants.md), then follow
the complete maintained
[successor invocation](../../scripts/hatchery/sequoia-pqc-build/procedure/PROCEDURE.md#successor-invocation).
The maintained sequence performs prebuild capture, separately authorized setup, boundary freeze, and the
failure-boundary self-test before invoking either package attempt. Staging alone neither prepares nor authorizes an attempt.

The historical 1.5.0-3 reviewed archive had SHA-256
`c58a0c5c1748c0efca26a831a0294bb0830a664209a8f419451c4ee9950c2265`,
and its packaged `sqv` had SHA-256
`9f897f07cb6abe1919a4d87e9f8308aacb48bde338046eab2b4f1cfd1c782d74`.
Those identities describe the historical reviewed candidate only. They are not
identities for release 4. The successor archive and executable hashes must be
computed from a real new build and recorded in its external evidence. This
recipe README is maintenance documentation; `package()` installs the upstream
checkout's `README.md`, not this file.

Downstream cryptographic-operation, macOS interoperability, installation,
rollback-authenticity, and independent-acceptance gates remain separate and
open after a successful build. Chameleon compatibility remains a separate
interoperability lane.
