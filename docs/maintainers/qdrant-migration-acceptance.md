# Qdrant Migration Acceptance

This runbook defines the disposable acceptance evidence required before the
Qdrant 1.19 package set may be published or deployed. It is an execution
contract, not evidence that a gate has passed.

Disposition: deferred. Publication eligible: no.

The earlier `final-e` runtime record is superseded. It is non-authoritative and
cannot satisfy this strengthened G3 contract or appear as accepted evidence in
the final acceptance index.

The supported retained-data route is exactly:

`1.17.1 → 1.18.3 → 1.19.0`

Qdrant storage migrations are irreversible. Never open storage migrated by a
newer minor with an older binary. Rollback always pairs a retained binary and
configuration with its matching untouched state, cold copy, or compatible
snapshot.

## Accepted Artifact Set

Pin and record these independent identities before running a fixture:

| Artifact | Release and built-artifact identity | SHA-256 |
| --- | --- | --- |
| Qdrant final | 1.19.0; tag object `af875b4bfd98103f7c0ee34fe4f25c5099893ca9`; commit `74f3e85b9473c62560006c043e13737ce6b48412`; package `qdrant-1.19.0-1-x86_64.pkg.tar.zst`, size `28018464`; executable size `72134360` | source `e0c9a030ae47d95f7c739598343bd2529c817fe262c4e7b2a4f1070ff82a024e`; package `15f15fe2c0c774691bf3193bc8fc7883fa530c89db697f7c0bcc2720d231b011`; executable `bf24efd92208fab1a8f4769a56158280b458b7a42850095ac875824571005f8c` |
| Qdrant migration intermediate | 1.18.3; tag object `3ea8cf7ce633256fb1b2a75b0de9d9ce60b22254`; commit `db8fa43fcb6aedec1e739487e17a99731b74590a`; package `qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst`, size `26721008`; executable size `72145432` | source `c5f918b4f37279ec00b22b718ca54bca7b43c9d17628b28b8eba363beceb0c96`; package `591f16328fcff0fc0193353a65f4c783afc1d24258ae251d3a8927283276ce9e`; executable `97c16f4582cc0b9f86c7b451d88f7ea8ca56a1e45582168241de7487d31546a7` |
| Retained Qdrant baseline package | `qdrant` 1.17.1-1, x86_64; archive size `25531392`; embedded binary `1d9e300802fe1588c6b6aef5167c32f8d215b5d79c07eaf6699ea1a80d92bf72`; embedded configuration `23f9b7628f8886edf1d6dbd45216a3755eb28bcf00c1e38d391087de58c81bde` | package archive `d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb` |
| Qdrant Web UI | 0.2.16; tag object `018e83a869a3d2b831e92664e8d33f51ec7981b1`; commit `d3f7a1174933ab637d9711ea45456d32b878b50e` | source `be85d9cffc5d5ad8122c4fe332cd6731cddcd508a61d77ee918626fc4d977577`; `dist-qdrant.zip` `4446f0cea024078011c78cd24a592c9b563656d15205818563fa6b22d394dd29`; license `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |

The G3 harness rejects any 1.18.3 or 1.19.0 executable whose SHA-256 differs
from this table, even when its reported version matches. The G0/G1 manifest
must independently bind each executable to the matching package payload and
package archive.

Pass the retained package archive as a first-class input. The harness verifies
its regular non-symlink identity, filename, size, SHA-256, exact `.PKGINFO`
name/version/architecture, embedded configuration digest, and byte equality
between its `usr/bin/qdrant` and the supplied 1.17.1 binary. Public evidence
records only those safe fields; it never copies `.BUILDINFO` paths. The G3
manifest also binds every generated runtime configuration digest and the
versioned storage-seed identity, specification digest, point-set digest,
ordered-ID digest, and payload-schema digest. Do not select any input by
version text alone.

## Accepted 1.19 Surface

The 1.19 single-file mmap storage default is accepted only after the exact
consecutive-minor migration and recovery matrix in G3 passes against the
reviewed binary. TurboQuant, explicit memory-placement tuning, and speculative prefix
indexes remain disabled; enabling any of them requires a separate measured
workload, design decision, and acceptance route.

The canonical application surface is `/points/query` and its batch and group
forms. Removed legacy search, recommend, and discover APIs are not restored,
shimmed, or treated as a compatibility requirement.

The global `GET /quotas` API is the maintained quota authority. The strict-mode
`max_resident_memory_percent` setting is deprecated and is not preserved; the
maintained setting is `storage.quotas.max_resident_memory_percent`, verified
through the authenticated global quota response and the threshold and release
tests below.

The 1.19 snapshot-recovery changes are accepted only through the G3 collection
and full-storage, corruption rejection, retry, and restart matrix. URL snapshot
recovery remains disabled and snapshot storage remains local.

Web UI 0.2.16 Usage Quotas is accepted as a read-only view of the authenticated
global quota state. Usage Quotas does not relax API authentication or grant
users direct dashboard or API access.

## Safety Boundary

- Run G0–G3 only in disposable storage and an isolated Arch environment.
- Give every version a distinct configuration, storage root, snapshot root,
  logs, and evidence directory. Instances run strictly one at a time and may
  reuse the one reviewed loopback HTTP/gRPC pair only after the harness proves
  the preceding listener has stopped.
- Keep the application and all other writers disconnected throughout G3.
- Provision the test admin/HMAC secret at runtime. Never commit it, copy it into
  package artifacts, print it, or enter it in the dashboard.
- Deny non-loopback egress and capture attempted connections during G2 and G3.
- Do not use `--force_snapshot`, `priority=no_sync`, compatibility-check
  suppression, or an older binary against a newer storage tree.
- Host inspection, package installation, service changes, live-state copying,
  and cleanup require their own authorization. This runbook grants none.

## Plan-Only Preflight

Review the complete fixture plan before creating storage or starting a server:

```bash
tools/validate_qdrant_migration.zsh --plan \
  --qdrant-1.17.1-package <retained-qdrant-1.17.1-1-package> \
  --qdrant-1.17.1 <retained-1.17.1-binary> \
  --qdrant-1.18.3 <built-1.18.3-binary> \
  --qdrant-1.19.0 <built-1.19.0-binary>
```

Plan mode must verify that all three exact inputs are present, describe both
routes below, and make no service, storage, or network mutation. The executable
runtime harness may be run only after its work root, ports, artifacts, and
cleanup boundary have been reviewed.

## Disposable Execution

After the plan and exact artifact inputs are accepted, run the fixture with a
new direct or descendant path under `/tmp`:

```bash
tools/validate_qdrant_migration.zsh --execute \
  --work-root /tmp/qdrant-migration-<run-id> \
  --http-port 16333 \
  --grpc-port 16334 \
  --int-receipt /tmp/qdrant-migration-interrupt-INT.json \
  --term-receipt /tmp/qdrant-migration-interrupt-TERM.json \
  --qdrant-1.17.1-package <retained-qdrant-1.17.1-1-package> \
  --qdrant-1.17.1 <retained-1.17.1-binary> \
  --qdrant-1.18.3 <built-1.18.3-binary> \
  --qdrant-1.19.0 <built-1.19.0-binary>
```

The work root must not exist before execution. Ports must be distinct integers
from 1024 through 65535 and must be free on loopback; 16333 and 16334 are the
defaults. Before creating the work root or invoking any candidate, the harness
must bind 1.17.1 to the exact retained package payload and verify the accepted
1.18.3 and 1.19.0 binary digests. Plan mode never invokes those binaries. The
isolated execution records each accepted binary's exact reported version and
rejects a runtime record that does not match the expected versions. Preserve
the completed work root until its evidence has been reviewed; cleanup is a
separate authorized step.

`--execute` must enter a fresh Bubblewrap network namespace through a bounded
transient user service. The boundary clears the inherited environment, exposes
only the loopback interface, and gives the disposable run a 512 MiB cgroup
memory ceiling with a 480 MiB high watermark. The harness must prove loopback binding succeeds, the network
namespace differs from its parent, and a non-loopback connection is denied
before starting Qdrant. If `systemd-run`, Bubblewrap, the user namespace, the
mount namespace, the cgroup limit, or either network probe is unavailable,
execution fails closed before an acceptance manifest can be written.

The mount namespace exposes only `/usr` with Arch's usr-merge symlinks, a new
`/proc` and `/dev`, read-only cgroup metadata, the read-only system CA bundle,
the one bound work root, and the script plus three bound binaries under the
private `/run`. It does not bind the host root, `/home`, `/root`,
`/etc/qdrant`, or `/var/lib/qdrant`; the inner harness proves those sensitive
roots are absent before starting a binary.

The transient user unit has `RuntimeMaxSec=900`, `TimeoutStopSec=30`,
`KillMode=control-group`, and `SendSIGKILL=yes`. A harness-owned supervisor is
the direct parent of Bubblewrap. It watches a FIFO whose sole writer belongs to
the outer process, explicitly stops and reaps its owned Bubblewrap child when
that writer closes, and leaves systemd's control-group policy as the bounded
fallback. INT, TERM, HUP, an error, or an abrupt outer-process exit closes the
keepalive. The outer process then waits for and reaps the exact background
`systemd-run --wait --collect` client. It captures the supervisor's exact
cgroup identity before payload launch. Collection passes only when that exact
client was waited and reaped with the mode-specific expected status for the same
unit and the captured cgroup no longer exists. This receipt is the
unit-collection authority; it does not infer ownership from a separate
user-manager query that may be unavailable across PID namespaces.

Inner runtime success writes only a `runtime_validated` candidate. The outer
harness may promote it to `accepted` only when that exact client exits
successfully after the payload, which is the collection authority for this
boundary. Before an accepted run, create two fresh work roots and run:

```bash
tools/validate_qdrant_migration.zsh --probe-interrupt INT \
  --receipt /tmp/qdrant-migration-interrupt-INT.json \
  --work-root /tmp/qdrant-migration-interrupt-INT-<run-id> \
  --qdrant-1.17.1-package <retained-qdrant-1.17.1-1-package> \
  --qdrant-1.17.1 <retained-1.17.1-binary> \
  --qdrant-1.18.3 <built-1.18.3-binary> \
  --qdrant-1.19.0 <built-1.19.0-binary>

tools/validate_qdrant_migration.zsh --probe-interrupt TERM \
  --receipt /tmp/qdrant-migration-interrupt-TERM.json \
  --work-root /tmp/qdrant-migration-interrupt-TERM-<run-id> \
  --qdrant-1.17.1-package <retained-qdrant-1.17.1-1-package> \
  --qdrant-1.17.1 <retained-1.17.1-binary> \
  --qdrant-1.18.3 <built-1.18.3-binary> \
  --qdrant-1.19.0 <built-1.19.0-binary>
```

The INT probe must exit 130 and the TERM probe must exit 143. Each writes its
receipt only after the inner process has synchronized on a ready Qdrant child
with both loopback listeners observed inside the isolated network namespace.
Ordinary completion requires status zero from the exact waited transient client.
For either signal probe, closing the owned keepalive deliberately terminates the
Bubblewrap payload with TERM, so the exact `systemd-run --wait --collect` client
must instead return 143. The receipt records that actual and expected wait status,
the same-unit match, client reap, cgroup-identity match, and exact collection
result without publishing the unit or cgroup value.
The public-safe receipt SHA-256-binds that private readiness marker without
publishing its process, cgroup, unit, or namespace identity. After interruption,
exact owned-process and cgroup disappearance—not an outer-host port query—must
prove zero owned process, listener, transient-unit, and cgroup residue, with
both the runtime candidate and accepted manifest absent. Cleanup failure writes a rejected receipt and
uses a separate non-success status rather than claiming the conventional
signal result. `--execute` accepts only current-tool, current-fixture,
package-and-binary-bound accepted receipts; any mismatch fails before the work
root is created.

## Fixture Seed

Build one deterministic 1.17.1 fixture with exactly 1001 points. The first two
stable IDs are the `target` set; their predefined dense, sparse, and hybrid
ordering is identical and is checked against their complete deterministic
payloads, including `label`, `generation`, `ordinal`, `indexed_group`,
`unindexed_group`, and `limit_bucket`. The other points are
a deliberately dissimilar background set. The fixture contract also requires:

- a versioned collection addressed through a stable alias;
- stable explicit IDs reused at every verification step;
- a keyword index only for `indexed_group`, while `unindexed_group` and
  `limit_bucket` remain deliberately absent from the payload schema; no other
  payload-schema key is accepted, and every later verification must match the
  initial seed schema digest exactly;
- exact two-ID results for both the indexed `indexed_group` filter and the
  allowed but deliberately unindexed `unindexed_group` filter;
- a page size of 128 that traverses all 1001 unique IDs across exactly eight pages;
- a ready-server query at limit 1000 that returns the exact 1000-point boundary
  set, followed by a limit 1001 query that the configured maximum rejects
  without stopping the server;
- one collection snapshot and one full-storage snapshot or cold backup;
- recorded collection configuration, schema, point count, alias mapping,
  snapshot metadata, and query-result digest.

Clone the seed before exercising either route. Fixture generation must be
repeatable from a tracked specification; generated storage, snapshots, and
secrets remain untracked run artifacts.

## G0 — Provenance And Contract

1. Verify every tag object, commit, archive, Web UI distribution, and license
   digest against the accepted artifact set.
2. Compare the 1.18.3 AUR `qdrant` reference and record every local dependency,
   service, configuration, authentication, dashboard, and hardening divergence.
3. Regenerate all three `.SRCINFO` files and prove each matches its `PKGBUILD`.
4. Confirm the final package hard-depends on `qdrant-web-ui` and the migration
   package cannot replace the active `/usr/bin/qdrant` producer.
5. Inspect the source patch and generated SBOM inputs. Record the exact builder
   image, toolchain, source tree status, commands, and output digests.

For this refresh, build all three package candidates from the tracked
`containers/qdrant-builder/Containerfile`. Its Arch base is pinned to
`sha256:ee205c220399524a683cf495d411691b921baed8ab47cdc6d732efa782fae484`.
The reviewed builder has repository digest
`sha256:876d4b2bfe03167c6d29f368def3050d4b1d16b3f89deead8379b61ccada10b0`
and image ID
`e4c00aadeb4a4d52f48ebd3d2ea32ae9433a02761e925589b0a6d619a837166f`.
Run every package build with the container network disabled. A build from a
different base, builder digest, image ID, or network boundary is not the
accepted G0 artifact set and requires a new recorded G0 review.

The accepted final3 artifact set predates the reconstruction procedure below.
Its G0/G1 record truthfully discloses that the historical Cargo-cache population
command and canonical cache manifests were not retained. Acceptance rests on
the issue #28 G0/G1 boundary: pinned sources and release metadata, exact
`.SRCINFO`, verified source and lock checksums, a fully reconciled consumed
Cargo graph, network-disabled final builds in the exact builder, and complete
package and payload inspection. It does not claim clean-cache replayability.

Every reconstruction and future candidate must use the stricter procedure
below. Start from empty `SRCDEST` and `CARGO_HOME` caches. Use the
network-enabled prefetch only to populate those explicit, per-lane caches: in
the pinned image, run `makepkg --verifysource` to enforce the PKGBUILD checksums,
then `makepkg --nodeps -o` so each locked Cargo graph is fetched by `prepare()`.
For the final pass, copy the package inputs into fresh neutral package, build,
and artifact roots and reuse only the verified source and Cargo caches. Pin the
package archive timestamps to the values recorded by the accepted image builds:

- qdrant-web-ui: `SOURCE_DATE_EPOCH=1786983811`
- qdrant-migration: `SOURCE_DATE_EPOCH=1786981596`
- qdrant: `SOURCE_DATE_EPOCH=1786981317`

These package-build epochs are distinct from the native recipes'
`_source_date_epoch` values: `_source_date_epoch` canonicalizes SBOM content and
does not set the package archive build date.

For each of `qdrant-web-ui`, `qdrant-migration`, and `qdrant`, prepare a fresh
neutral root and a fresh copy of that package directory. Mount the lane's five
explicit roots at the generic `/build/package`, `/build/build`,
`/build/artifacts`, `/build/sources`, and `/build/cargo` paths. First run this
checksum-bound network-enabled prefetch, starting with empty source and Cargo
caches:

```bash
podman run --rm --pull=never --network=slirp4netns \
  --env BUILDDIR=/build/build \
  --env PKGDEST=/build/artifacts \
  --env SRCDEST=/build/sources \
  --env CARGO_HOME=/build/cargo \
  --env "SOURCE_DATE_EPOCH=<lane-epoch-above>" \
  --volume "<prefetch-package-root>:/build/package:Z" \
  --volume "<prefetch-build-root>:/build/build:Z" \
  --volume "<prefetch-artifact-root>:/build/artifacts:Z" \
  --volume "<source-cache-root>:/build/sources:Z" \
  --volume "<cargo-cache-root>:/build/cargo:Z" \
  'localhost/arch-pkgs-qdrant-builder@sha256:876d4b2bfe03167c6d29f368def3050d4b1d16b3f89deead8379b61ccada10b0' \
  zsh -fc 'cd /build/package && makepkg --verifysource && makepkg --nodeps -o'
```

Discard the prefetch package, build, and artifact roots. Create new empty roots,
copy in the same reviewed package inputs, and run the candidate build with the
same lane epoch and cache roots:

```bash
podman run --rm --pull=never --network=none \
  --env BUILDDIR=/build/build \
  --env PKGDEST=/build/artifacts \
  --env SRCDEST=/build/sources \
  --env CARGO_HOME=/build/cargo \
  --env CARGO_NET_OFFLINE=true \
  --env "SOURCE_DATE_EPOCH=<lane-epoch-above>" \
  --volume "<fresh-package-root>:/build/package:Z" \
  --volume "<fresh-build-root>:/build/build:Z" \
  --volume "<fresh-artifact-root>:/build/artifacts:Z" \
  --volume "<source-cache-root>:/build/sources:Z" \
  --volume "<cargo-cache-root>:/build/cargo:Z" \
  'localhost/arch-pkgs-qdrant-builder@sha256:876d4b2bfe03167c6d29f368def3050d4b1d16b3f89deead8379b61ccada10b0' \
  zsh -fc 'cd /build/package && makepkg --verifysource && makepkg --nodeps --cleanbuild --force'
```

Before either invocation, inspect that repository digest and require image ID
`e4c00aadeb4a4d52f48ebd3d2ea32ae9433a02761e925589b0a6d619a837166f`;
`--pull=never` prevents tag or registry drift. Prefetch outputs are not
publication candidates and must not enter the artifact manifest. Only package
archives produced by the network-disabled final builds may enter G0.

The prefetch package, build, and artifact roots are never reused. In particular,
never reuse the extracted prefetch source tree, `pkgdir`, or output directory.
Copy only the verified `SRCDEST` and `CARGO_HOME` caches into fresh per-lane
final cache roots, then record path-neutral, sorted manifests before the final
invocation. Each lane's evidence must bind:

- the `PKGBUILD SHA-256`, `.SRCINFO` SHA-256, and a `package-input manifest
  SHA-256` covering every reviewed package-directory input;
- the prepared source's `Cargo.lock SHA-256` for each native lane, with an
  explicit not-applicable value for the static Web UI lane;
- a `source-cache manifest SHA-256` covering relative path, file type, mode,
  size, and content digest for every source-cache entry;
- a `Cargo-cache manifest SHA-256` with the same fields for every Cargo-cache
  entry used by a native build; and
- the final archive name, size, SHA-256, `.PKGINFO` identity, and a sorted
  output-set manifest digest.

A reconstruction or future-candidate G0/G1 artifact manifest must bind the
builder image ID and repository digest, prefetch and final network mode, fixed
lane epoch, exact prefetch and final commands, and all cache, input, and output
manifest digests. A digest without its canonical manifest is insufficient
evidence. These requirements do not retroactively describe evidence absent
from the accepted final3 record.

Aggregate only the three reviewed offline outputs in a new candidate directory.
The exact output-set validator must accept exactly the three declared archives:

```zsh
expected_outputs=$'f qdrant-1.19.0-1-x86_64.pkg.tar.zst\n'\
$'f qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst\n'\
$'f qdrant-web-ui-0.2.16-1-any.pkg.tar.zst'
actual_outputs=$(find <candidate-output-root> -mindepth 1 -maxdepth 1 -printf '%y %f\n' \
  | LC_ALL=C sort)
[[ $actual_outputs == $expected_outputs ]]
```

Any debug or undeclared output, non-regular entry, missing archive, or duplicate
is a hard failure and leaves the artifact set unaccepted.

Run an incomplete-cache negative control in throwaway copies before accepting
the real output set. Remove one required source archive, and for a native lane
remove one locked crate archive, then repeat the exact fresh-root final command.
Each case must fail before any candidate archive or G0 artifact manifest exists;
the negative-control output root must remain empty. Never damage or reuse the
verified caches while performing this control.

For the accepted final3 evidence set, `--network=none` is the recorded offline
boundary; its invocation did not also set Cargo's offline flag. That
kernel-enforced isolation was verified directly and is not inferred from a
successful build. `CARGO_NET_OFFLINE=true` is required for every reconstruction
and future candidate build in addition to `--network=none`.

Stop on any mismatch. Do not substitute a same-version artifact.

## G1 — Package And Payload

Build the Web UI and migration packages independently, then compile the server
package without resolving its not-yet-installed local runtime dependency:

```bash
(cd packages/qdrant-web-ui && makepkg --verifysource && makepkg -f)
(cd packages/qdrant-migration && makepkg --verifysource && makepkg -f)
(cd packages/qdrant && makepkg --verifysource && makepkg --nodeps -f)
```

The server's `--nodeps` invocation is only a compilation gate. A Web UI archive
built nearby does not satisfy pacman's dependency resolution. The accepted
G0/G1 artifact manifest must bind both exact package archives, metadata and
payload inspection must confirm the server's hard dependency, and G2 must
install or otherwise compose those exact artifacts in one disposable runtime
before acceptance. A dependency-resolving clean builder is equally valid when
it installs the exact reviewed Web UI artifact first and records that builder
state.

Inspect package metadata, ownership, modes, licenses, SBOM inputs, binary
versions, service assets, configuration, sysusers, and tmpfiles. In particular:

- `qdrant-web-ui` is architecture-independent and installs root-owned,
  read-only assets under `/usr/share/qdrant/web-ui`;
- the Web UI package has no Node runtime, install hook, runtime bootstrap, or
  runtime download;
- the final server package depends on that exact Web UI package;
- the migration package installs only the retained 1.18.3 binary in its
  migration-only path;
- no package contains an admin/HMAC secret; and
- no payload creates `/var/lib/qdrant/static` or removes an existing legacy
  directory.

Record package and payload manifests plus SHA-256 digests. Passing G1 does not
make any catalog lane publication-eligible.

Build every publication candidate from a neutral build root whose spelling is
independent of a maintainer home directory or checkout. Inspect every archive's
metadata as well as its install payload, including `.BUILDINFO`. Reject a
candidate when any archive metadata contains a private or machine-local checkout path,
hostname, user identity, or equivalent local build-root detail;
removing such a path only from the public manifest does not make the package
acceptable. Rebuild from the neutral build root and re-run G1 instead.

The pacman dependency on `qdrant-web-ui` is deliberately unversioned so the UI
can follow its independent release cadence. This refresh's accepted artifact
manifest binds Web UI 0.2.16; every later UI revision must independently pass
G0–G2 before it can enter an accepted manifest.

## G2 — Fresh Runtime And Security

Start 1.19.0 on fresh disposable storage and verify:

1. The service refuses to start when the secret environment file is absent,
   empty, malformed, or incorrectly permissioned.
2. Only loopback HTTP 6333 and gRPC 6334 listeners exist. There is no p2p,
   LAN, Tailnet, or wildcard listener.
3. Telemetry, CORS, URL snapshot recovery, S3, and external inference are
   disabled. Capture zero unexpected egress.
4. The dashboard is contained under `/dashboard` and its static root resolves
   only to `/usr/share/qdrant/web-ui`.
5. Dashboard responses carry a same-origin CSP with `connect-src 'self'`,
   `base-uri 'none'`, `frame-ancestors 'none'`, and `object-src 'none'`, plus
   no-referrer, nosniff, and deny-framing headers. Monaco and WASM must work
   without weakening that boundary.
6. The admin secret is never sent to the browser. Collection-scoped `prw` JWTs
   pass point reads and writes, while collection-scoped `r` JWTs remain
   read-only. Record that upstream's generic `rw` role is rejected as the
   maintained default because it also permits collection snapshot creation.
   Both maintained roles must fail collection creation/deletion, alias,
   snapshot, quota, and configuration operations.
7. On the already loopback-only HTTP endpoint, the narrow upstream public root
   banner is accepted only when unauthenticated `GET /` returns exactly
   `{"title":"qdrant - vector search engine","version":"1.19.0"}`.
   Unauthenticated `GET /collections` and `GET /quotas` must return 401; both
   requests must pass with the admin secret.
8. The configured 64-collection, 80% resident-memory, 85% disk, ten-point
   release-margin, query-1000, timeout-120, `TasksMax=2048`, `MemoryHigh=80%`,
   and `MemoryMax=90%` limits are visible and effective.
9. Data and expected retrieval results survive a clean service restart.

Capture listener tables, response headers, authorization outcomes, egress logs,
resource-limit observations, server version, config digest, and restart result.

## G3 — Migration And Recovery

Run both routes even if the later live preflight reports an empty service.

### Empty-state route

1. Start from a pristine empty 1.17.1 storage tree and preserve an untouched,
   digest-recorded copy as the rollback anchor.
2. Prove the migration-only 1.18.3 binary and its matching empty state start and
   stop cleanly without becoming the active package producer.
3. Start 1.19.0 against a separate, fresh empty storage root.
4. Seed the final target, verify all retrieval cases, restart it, and verify
   restart persistence.
5. Snapshot 1.19.0, restore it into a separate empty target, and repeat the
   retrieval checks.

### Retained-data route

At each boundary, stop and freeze writers before copying state:

1. Create a verified 1.17.1 cold copy, collection snapshot, and full-storage
   recovery artifact.
2. Start 1.18.3 only on a copy that has never been opened by 1.19.0. Verify
   collection metadata, aliases, stable explicit IDs, point counts, and dense,
   sparse, and hybrid retrieval equivalence; then verify restart persistence.
3. Exercise a same-minor snapshot restore into a separate empty target.
4. Exercise a next-minor snapshot restore from 1.17.1 into 1.18.3 and verify the
   same externally visible state.
5. Restore the preserved 1.17.1 full-storage snapshot into a 1.18.3 target,
   then verify the complete fixture and a clean restart.
6. Preserve a verified 1.18.3 cold copy and snapshots before starting 1.19.0.
7. Start 1.19.0 only on the 1.18.3 copy. Repeat metadata, retrieval, restart,
   same-minor snapshot, and next-minor snapshot checks.
8. Restore the preserved 1.18.3 full-storage snapshot into a 1.19.0 target,
   then verify the complete fixture and a clean restart.
9. For collection snapshots, perform separate alias replay and prove the alias
   selects the restored collection atomically.

For each version boundary, deliberately present one truncated and one
checksum-mismatched snapshot. Recovery must reject both without altering the
last accepted target. Also prove failure leaves the matching source state and
the separate empty target recoverable for a clean retry.

The snapshot matrix is mandatory: restore the preserved 1.17.1 collection
snapshot with both 1.17.1 (same-minor) and 1.18.3 (next-minor), then restore the
preserved 1.18.3 collection snapshot with both 1.18.3 (same-minor) and 1.19.0
(next-minor). Each truncated and checksum-mismatched rejection at the two
version boundaries must be followed by a successful retry against the same
disposable recovery target. The 1.19.0 empty-state snapshot also requires a
separate same-minor restore. The full-storage matrix is independently
mandatory: consume the 1.17.1 full-storage artifact in a separate 1.18.3 target
and consume the 1.18.3 full-storage artifact in a separate 1.19.0 target. Each
full-storage restore must preserve the complete externally visible fixture and
survive a clean target restart.

Apply memory and disk pressure below and across the configured thresholds.
Record rejection, recovery-margin, query, restart, and storage-integrity
behavior; do not relax limits based on speculation.

The harness uses a bounded cgroup for memory pressure and a size-limited tmpfs
inside its private mount namespace for disk pressure. It records a successful
write below each threshold, rejection above it, recovery only after crossing
the configured release margin, a post-pressure query, a clean restart, and a
storage-integrity check. It must not infer pressure behavior from configuration
text or host-wide free-space figures. The pressure-only server configuration
pins two HTTP workers so the finite cgroup measures storage workload rather
than varying with the host's CPU count; the accepted 80%, 85%, and ten-point
release-margin values remain unchanged.

For memory, Qdrant's `GET /quotas` response is the threshold and release-margin
authority. Recovery requires
`result.usage.resident_memory_percent < 70` before the retry can succeed. The
manifest also records the process RSS and cgroup current/limit as secondary
observations; retained allocator pages do not replace or override the product
quota state.

If the 100-point load batch that crosses the memory threshold is itself
rejected, retrieve all 100 exact IDs immediately and require an empty result
before deleting the load collection. Bind the full ordered ID set, its digest,
the empty observed result and digest, and the absence decision into the memory
rejection obligation. A partial batch application is a hard failure.

Disk and memory pressure use separate collections and separate integrity
obligations. For each resource, capture an exact sorted point-ID, payload, and
count fingerprint at pre-pressure, post-rejection, post-release retry, and
post-restart. The post-rejection fingerprint must equal the pre-pressure
fingerprint and must prove every rejected ID or batch absent. Only after the
configured release margin is observed may the same rejected write be retried;
the post-release retry fingerprint must then equal the post-restart
fingerprint. Pressure collections cannot satisfy fixture filtering,
pagination, or query-boundary obligations unless those results are explicitly
bound into the accepted G3 evidence; this harness does not use them for those
contracts.

## Evidence And Exit

Retain one digest-linked evidence collection with all of these independently
reviewable records:

- the G0/G1 artifact manifest, containing package, source, tag, commit,
  archive, payload, builder, and Web UI identities and digests;
- the G2 unit-runtime record for service, listener, authentication, policy,
  restart, and no-egress checks;
- the G2 browser record for the dashboard, CSP, headers, Monaco, WASM, secret
  non-disclosure, and browser-visible no-egress checks;
- the G3 `evidence/manifest.runtime-validated.json` runtime candidate;
- the G3 accepted `evidence/manifest.json`, which binds the exact candidate
  SHA-256 and declares the complete promotion delta; and
- a top-level acceptance index that names and SHA-256-binds the G0/G1, both G2,
  and both G3 records without embedding private paths.

The executable harness writes the G3 candidate and accepted manifest using
schema `qdrant-migration-evidence/v1`; it neither accepts nor manufactures
G0/G1 or G2 provenance. Its accepted disposition is valid only when the
manifest contains every required G3 obligation and binds binary digests,
configs, query fingerprints, snapshots, cold-copy file manifests, restore and
rejection outcomes, resource-pressure observations, ports, namespace and
egress isolation, signal receipts, and final process/listener/unit/cgroup and
secret cleanup. Review must bind this runtime manifest's three binary digests
to the corresponding entries in the accepted G0/G1 artifact manifest. Missing
or unbound evidence is a hard failure, never an implicit pass.

The retained `manifest.runtime-validated.json` binds the exact tool SHA-256,
fixture specification and storage seed before the transient unit exits. The
candidate must reconcile its final tool and three binary digests exactly with
both prerequisite signal receipts and must bind the same payload-schema digest
recorded by the initial fixture event. Any byte or seed-identity mismatch
blocks candidate serialization. The
accepted `manifest.json` records that candidate's digest, its exact promotion
delta, the finite unit policy, closed outer keepalive, reaped client,
successful wait, collected-unit result, and separate accepted INT and TERM
receipt digests. Retain both public-safe receipt JSON files beside the durable
G3 records so each remains independently hash-verifiable. An interrupted run
must never create `manifest.json`.
The copy retained as durable public evidence uses only generic `/tmp` contract
paths and sanitized namespace, cgroup, and unit identities. Keep machine-local
paths, numeric user identities, host identifiers, and secrets only in the
separately retained raw work root, never in that public manifest.

Any failed or inconclusive item leaves all three Qdrant catalog lanes deferred
with Publication eligible: no. Complete G0–G3 evidence still does not change
that disposition: all three lanes remain deferred with Publication eligible:
no until G4 composes the accepted 1.19.0 server with the selected Haystack and
Hayhooks packages. G4 cannot retroactively waive G0–G3.

After a separately authorized live cutover, retain the untouched 1.17.1 anchor,
the tested 1.18.3 and 1.19.0 artifacts, and their matching recovery state until
a post-cutover 1.19 snapshot restores successfully and the deployment runs
cleanly for seven days. Removing any anchor requires separate explicit approval.
