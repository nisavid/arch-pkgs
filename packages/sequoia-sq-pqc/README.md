# sequoia-sq-pqc

This opt-in recipe builds Sequoia `sq` 1.4.0 with the OpenSSL PQC backend and
an exact `sequoia-openpgp` 2.4.1 lock. It provides `sequoia-sq=1.4.0`, conflicts
with `sequoia-sq`, and is not co-installable with the classical package.

The recipe remains a deferred Hatchery qualification input tracked in
[dotfiles issue #148](https://github.com/nisavid/dotfiles/issues/148). It does
not authorize installation, signing, publication, or production key use.

## Maintenance Baseline

- `authoritative_reference`: [Official Arch sequoia-sq 1.4.0-2 recipe](https://gitlab.archlinux.org/archlinux/packaging/packages/sequoia-sq/-/blob/29aecd6968d1395a60fb95d0c21febf0ec1b7155/PKGBUILD), packaging commit `29aecd6968d1395a60fb95d0c21febf0ec1b7155`: the matching x86_64 signed-tag Cargo source-build reference for upstream v1.4.0 at `558e1461d4f277924b0710f17a5bb56469f74ff2`. This opt-in lane selects OpenSSL instead of the reference backend.

- `advisory_references`: [CachyOS sequoia-sq rebuild metadata](https://packages.cachyos.org/package/cachyos-extra-v3/x86_64_v3/sequoia-sq); [upstream target manifest and source](https://gitlab.com/sequoia-pgp/sequoia-sq/-/tree/558e1461d4f277924b0710f17a5bb56469f74ff2); and [Sequoia OpenPGP 2.4.1 backend documentation](https://gitlab.com/sequoia-pgp/sequoia/-/blob/0b0c8c7f038b829de2da0d28a822941d8600f3ee/openpgp/README.md). The 2026-09-19 AUR search and named queries returned no corresponding SQ/SQV stable, git, or pqc package; sequoia-wot and sequoia-octopus-librnp variants were inspected as other application lanes. [Arch SQ 1.4.1-1](https://gitlab.archlinux.org/archlinux/packaging/packages/sequoia-sq/-/blob/b5a9fb614e1bb37d83cb1c2403013f61768bb598/PKGBUILD) now uses OpenSSL and is newer-version advisory material; it does not change this fixed 1.4.0 target.

- `divergence_notes`: Opt-in sequoia-sq-pqc provides sequoia-sq=1.4.0 and conflicts with the classical package. The recipe asserts the reviewed application commit, applies the checked-in exact OpenPGP 2.4.1 lock patch, disables default Nettle features, selects crypto-openssl, and requires openssl>=3.5 with libcrypto.so=3-64 and libssl.so=3-64. It retains the ordinary Arch executable/completion payload and uses build-path remapping. Package release 4 is deferred source with no new archive identity. SQ retains disabled LTO and manpages, uses isolated asset HOME/XDG directories, and omits the historical sequoia replacement declaration.

- `update_notes`: Keep this release-4 source lane deferred and publication-ineligible. Before changing its target, recheck Arch, CachyOS, AUR, and upstream manifests/release notes; preserve or explicitly review the pinned source commit, lock patch, backend, dependencies, and package relationship. Regenerate and compare .SRCINFO, run repository source checks, then use the maintained Hatchery procedure in a fresh staged run for separately authorized source verification, full checked build, payload/path inspection, and new archive/executable identities. Operation, macOS interoperability, installation, rollback-authenticity, and independent acceptance remain separate gates; see the [maintained procedure and gates](../../docs/maintainers/sequoia-pqc-variants.md).

Stage a clean reviewed revision using the
[maintainer guide](../../docs/maintainers/sequoia-pqc-variants.md), then follow
the complete maintained
[successor invocation](../../scripts/hatchery/sequoia-pqc-build/procedure/PROCEDURE.md#successor-invocation).
The maintained sequence performs prebuild capture, separately authorized setup, boundary freeze, and the
failure-boundary self-test before invoking either package attempt. Staging alone neither prepares nor authorizes an attempt.

The historical 1.4.0-3 reviewed archive had SHA-256
`b65f117f77a81989c2bb265f078ea975d7fe69229d58669b2a610bc10170586f`,
and its packaged `sq` had SHA-256
`7a76783cc34ce89008966c88079609184b1f84a4a7154ea07b3d8a8d47aa81db`.
Those identities describe the rejected historical candidate only: four shipped
manpages contained attempt-specific paths. They are not identities for release
4. The successor archive and executable hashes must be computed from a real
new build and recorded in its external evidence.

Downstream cryptographic-operation, macOS interoperability, installation,
rollback-authenticity, and independent-acceptance gates remain separate and
open after a successful build.
