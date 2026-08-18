# qdrant

Native Arch package for the Qdrant vector database and its selected dashboard.
The retained consecutive-minor binary is maintained separately in
[`qdrant-migration`](../qdrant-migration/).

The active `qdrant` package is a single-node, loopback-only service. Household
users reach reviewed retrieval behavior through Hayhooks and Open WebUI; they
do not receive direct network access to the Qdrant API or dashboard.

## Maintenance Baseline

- `authoritative_reference`: AUR
  [`qdrant` commit `51762d7`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=qdrant&id=51762d7ed828dfc25be633b4f0ca336d546ec81f)
  at the retained `1.18.3-1` migration baseline.
- `advisory_references`: upstream Qdrant
  [releases](https://github.com/qdrant/qdrant/releases),
  [upgrade guidance](https://qdrant.tech/documentation/upgrades/),
  [security guidance](https://qdrant.tech/documentation/security/), and the
  [`qdrant-web-ui` releases](https://github.com/qdrant/qdrant-web-ui/releases).
- `divergence_notes`: the package adds a dedicated user, a fail-closed
  external HMAC secret, scoped JWT RBAC, a root-owned separately packaged Web
  UI, same-origin response headers, loopback-only networking and egress, local
  snapshot storage, privacy defaults, resource guardrails, and a hardened
  `systemd` service. The sibling migration package installs no active producer.
- `update_notes`: verify pinned tag, commit, and archive identities; regenerate
  `.SRCINFO`; clean-build and inspect the server, migration, and Web UI
  packages; then pass the disposable provenance, fresh-runtime, security,
  consecutive-minor migration, corruption-rejection, recovery, rollback, and
  Haystack/Hayhooks composition gates before publication or deployment.

Relative to the AUR `1.18.3-1` recipe, the active package adds runtime
dependencies on `bash`, `coreutils`, and `qdrant-web-ui`; it adds `jq` and
pinned `cargo-sbom` source to the build. Both local recipes use locked Cargo
fetches and builds, the AWS-LC jitter workaround, build-path remapping, and a
canonical SPDX manifest. They retain upstream's Rust fat LTO but disable
makepkg-added native GCC LTO so fresh build roots produce the same native
inputs. They also remove inherited `-march`, `-mcpu`, and `-mtune` selectors
from native C/C++ flags so Qdrant's per-file SSE and AVX selections cannot be
overridden by the builder defaults; all other optimization, hardening, and
path-remapping flags remain. The active package additionally installs the
managed configuration, service, sysusers, tmpfiles, secret preflight,
dashboard-header patch, and license.

## Pinned Identities

The active package is Qdrant `1.19.0`:

- annotated tag object: `af875b4bfd98103f7c0ee34fe4f25c5099893ca9`
- GitHub-verified commit: `74f3e85b9473c62560006c043e13737ce6b48412`
- source archive SHA-256:
  `e0c9a030ae47d95f7c739598343bd2529c817fe262c4e7b2a4f1070ff82a024e`

Both recipes generate SPDX 2.3 dependency manifests with pinned
`cargo-sbom` `0.10.0` source (SHA-256
`4ffe4b49660f4f4331fb5efcf7074a318b10f5f8fd75e42351a7ca32c58c2723`).
They canonicalize object keys and dependency arrays and replace the generator's
random document namespace and wall-clock timestamp with the exact Qdrant
source digest and source timestamp. The installed manifests are reproducible
across fresh build roots.

The separately maintained migration package is Qdrant `1.18.3`:

- annotated tag object: `3ea8cf7ce633256fb1b2a75b0de9d9ce60b22254`
- GitHub-verified commit: `db8fa43fcb6aedec1e739487e17a99731b74590a`
- source archive SHA-256:
  `c5f918b4f37279ec00b22b718ca54bca7b43c9d17628b28b8eba363beceb0c96`

The `1.19.0` annotated tag is not cryptographically signed. Its accepted
provenance is the GitHub-verified release commit plus the independently
reproduced archive hash recorded above. The `1.18.3` annotated tag carries a
valid PGP signature verified by GitHub, and its release commit is also
GitHub-verified; its pinned archive hash remains the exact source-byte boundary.

## Maintained 1.19 Surface

The single-file mmap storage default is accepted only after the disposable
consecutive-minor migration and recovery gate passes against the exact package
binary. TurboQuant, explicit memory-placement tuning, and speculative prefix
indexes remain disabled until a measured workload justifies a separate change.

The canonical application API is `/points/query` and its batch and group
forms. Removed legacy search, recommend, and discover APIs are not restored or
shimmed by this package.

The global `GET /quotas` API is the maintained quota authority. The deprecated
strict-mode `max_resident_memory_percent` setting is not preserved; use
`storage.quotas.max_resident_memory_percent`, verified through the
authenticated quota response and threshold/release tests. Qdrant 1.19
snapshot-recovery changes are accepted only through the collection and
full-storage, corruption-rejection, retry, and restart matrix; URL snapshot
recovery remains disabled and snapshot storage remains local. Web UI 0.2.16
Usage Quotas is accepted as a read-only view of authenticated global quota
state; it does not relax API authentication or grant users direct dashboard or
API access.

## Package Contents

The active package installs:

- `/usr/bin/qdrant`
- `/etc/qdrant/config.yaml`
- `/usr/lib/systemd/system/qdrant.service`
- `/usr/lib/qdrant/qdrant-secret-preflight`
- `/usr/share/qdrant/qdrant.spdx.json`
- the `qdrant` sysusers and tmpfiles entries
- the upstream license

It hard-depends on `qdrant-web-ui`, whose root-owned, read-only files live at
`/usr/share/qdrant/web-ui`. Qdrant serves that directory under `/dashboard` on
its existing loopback listener. The active package no longer creates
`/var/lib/qdrant/static`; upgrades do not delete a pre-existing directory.
The pacman dependency is deliberately unversioned for independent update
cadence. This refresh's accepted artifact manifest binds Web UI `0.2.16`; every
later UI revision must pass G0 through G2 independently before entering an
accepted manifest.

The sibling [`qdrant-migration`](../qdrant-migration/) package installs only
`/usr/lib/qdrant/migration/qdrant-1.18.3`, its SPDX manifest, and the upstream
license. It ships no service, configuration, or `/usr/bin/qdrant`, so it
cannot become a second active producer accidentally.

## Security And Resource Defaults

| Setting | Value |
| --- | --- |
| HTTP | `127.0.0.1:6333` |
| gRPC | `127.0.0.1:6334` |
| Cluster/p2p | disabled |
| Authentication | scoped JWT RBAC, fail-closed external HMAC secret |
| Browser secret | short-lived scoped JWT only; never the HMAC/admin secret |
| CORS | disabled |
| URL snapshot recovery | disabled |
| Snapshot storage | local only |
| External inference | disabled; no address is configured |
| Usage telemetry | disabled |
| Collections | maximum 64 |
| Query limit | 1000 |
| Query timeout | 120 seconds |
| Resident-memory quota | 80%, with a ten-point release margin |
| Disk quota | 85%, with a ten-point release margin |
| Service memory | `MemoryHigh=80%`, `MemoryMax=90%` |
| Service tasks | `TasksMax=2048` |

The service also denies all non-loopback IP traffic at the `systemd` boundary.
This makes the absent external-inference address, local snapshot storage, and
loopback binds defense in depth rather than the only egress controls.

Upstream leaves one narrow unauthenticated loopback banner: `GET /` returns
only `{"title":"qdrant - vector search engine","version":"1.19.0"}`.
Management and data endpoints are not public; for example, unauthenticated
`GET /collections` and `GET /quotas` are rejected.

The dashboard response patch applies CSP with same-origin connections,
anti-framing, no-referrer, and MIME-sniffing protections. The policy permits
the dashboard's packaged Monaco/WASM implementation without permitting remote
connections. Do not relax it until a disposable browser gate identifies a
specific required directive.

## Provision The HMAC Secret

`qdrant.service` requires `/etc/qdrant/qdrant.env`. A package-owned preflight
requires a regular, non-symlink file owned by UID 0 and the service's effective
group, with mode `0640` and exactly one valid key line. Missing, unreadable,
incorrectly permissioned, empty, or malformed secret material prevents startup.
The package intentionally does not create or back up this file.

Provision a 32-byte-or-longer lowercase hexadecimal secret as root:

```bash
sudo install -o root -g qdrant -m 0640 /dev/null /etc/qdrant/qdrant.env
secret="$(openssl rand -hex 32)"
printf 'QDRANT__SERVICE__API_KEY=%s\n' "$secret" \
  | sudo tee /etc/qdrant/qdrant.env >/dev/null
unset secret
```

The environment variable spelling is Qdrant's pinned configuration mapping
for `service.api_key`. `jwt_rbac: true` makes that value the HMAC secret for
scoped tokens. Give normal Hayhooks point read-write credentials the `prw`
role, and use `r` for read-only credentials. Upstream `rw` also permits
collection snapshot creation, so treat it as admin-adjacent and never make it
the Hayhooks or dashboard default. Hayhooks receives scoped collection
credentials, never the HMAC secret. Use a dedicated browser profile for the
dashboard, enter only a short-lived scoped JWT, and clear site data afterward.

## Build

The acceptance build uses the pinned Arch environment in
[`containers/qdrant-builder/Containerfile`](../../containers/qdrant-builder/Containerfile).
The G0/G1 evidence binds the resulting image digest, complete `.BUILDINFO`,
toolchain, command, and archive digests. Package builds run with networking
disabled after every source checksum passes.

Reconstruct each lane from empty, explicit `SRCDEST` and `CARGO_HOME` caches
in the exact pinned builder. Use a checksum-bound network-enabled
`makepkg --verifysource` plus `makepkg --nodeps -o` prefetch, then fresh neutral
package/build/artifact roots and `podman --pull=never --network=none` with only
those caches at `/build/{package,build,artifacts,sources,cargo}`. Pin
`SOURCE_DATE_EPOCH` to `1786983811` for `qdrant-web-ui`, `1786981596` for
`qdrant-migration`, and `1786981317` for `qdrant`. Prefetch outputs are never
candidates; only offline final archives may enter G0. The recipe
`_source_date_epoch` values separately canonicalize SBOM content.

Build the active package from this directory:

```bash
makepkg --verifysource
makepkg --nodeps -f
bsdtar -xOf qdrant-1.19.0-1-x86_64.pkg.tar.zst \
  usr/share/qdrant/qdrant.spdx.json | jq -e \
  '.spdxVersion == "SPDX-2.3" and any(.packages[]; .name == "qdrant" and .versionInfo == "1.19.0")'
```

`--nodeps` is appropriate only for the isolated compilation gate when the
validated `qdrant-web-ui` package is not installed in that build environment.
The accepted manifest must bind both exact artifacts, archive inspection must
confirm the hard dependency, and G2 must exercise them together. For
`makepkg -si`, first install the validated Web UI artifact or publish it in a
configured pacman repository; placing its package file nearby does not satisfy
dependency resolution.

Build the retained migration package independently:

```bash
cd ../qdrant-migration
makepkg --verifysource
makepkg -f
```

For a one-off active-package install, use `makepkg -si` from this directory.
`/etc/qdrant/config.yaml` is a pacman backup file: an upgrade preserves the
installed configuration and may write `config.yaml.pacnew`. Do not enable or
start the new unit until the accepted configuration and any `.pacnew` have been
reconciled deliberately, the external secret has been provisioned, and the
required migration route has completed. Never overwrite live configuration or
state opportunistically.

After those separately authorized steps complete, enable the service:

```bash
sudo systemctl enable --now qdrant.service
```

For the repeatable local-repository workflow, publish the validated package
artifacts and install them through pacman. See
[`docs/usage/local-repo.md`](../../docs/usage/local-repo.md).

## Migration And Rollback Boundary

The only supported retained-data upgrade route from the observed deployment is
`1.17.1 -> 1.18.3 -> 1.19.0`. The `qdrant-migration` binary exists solely to
make the intermediate step reproducible after the active recipe moves ahead.

Never run two Qdrant binaries against the same storage concurrently. Never
open storage migrated by `1.19.0` with `1.18.3` or `1.17.1`; a binary downgrade
is not rollback. Pair every retained binary and configuration with an untouched
matching state tree, cold copy, or version-compatible snapshot.

Before a live cutover, perform the separately authorized metadata-only
preflight. If the service is empty, start `1.19.0` on fresh empty storage and
retain the untouched `1.17.1` tree. If data exists, freeze writers and exercise
the full consecutive-minor route with verified cold copies and snapshot
restores. The disposable acceptance fixture must prove both paths regardless
of the live result.

Retain the old `1.17.1` state and package plus the tested `1.18.3` and `1.19.0`
artifacts until a post-cutover `1.19` snapshot has restored successfully and
the deployment has run cleanly for seven days. Removing those anchors requires
separate explicit approval.
