# Qdrant Production Cutover

This is the route for
[Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58)
on a host that runs `qdrant` 1.17.1-1 with no collections. Qdrant is promoted
together with the Open WebUI household stack through
[Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90)
and deployed before Open WebUI writes. Every privileged step belongs to the
operator. The handoff script
[`tools/qdrant_production_cutover.zsh`](../../tools/qdrant_production_cutover.zsh)
does nothing to the host without `--apply`, and `--apply` requires root.

## Candidate Identities

| Package | Archive | Size (bytes) | SHA-256 |
| --- | --- | ---: | --- |
| `qdrant-migration` | `qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst` | 26721008 | `591f16328fcff0fc0193353a65f4c783afc1d24258ae251d3a8927283276ce9e` |
| `qdrant` | `qdrant-1.19.0-1-x86_64.pkg.tar.zst` | 28018464 | `15f15fe2c0c774691bf3193bc8fc7883fa530c89db697f7c0bcc2720d231b011` |
| `qdrant-web-ui` | `qdrant-web-ui-0.2.16-1-any.pkg.tar.zst` | 5719063 | `f3d46e6ff09b8eb87b1465ee6a17a7cc35c574596b7fbf30518d3bc1d42fe10a` |

The retained baseline is `qdrant-1.17.1-1-x86_64.pkg.tar.zst`, 25531392
bytes, SHA-256
`d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb`.

**Identity is the digest.** The accepted final3 archives were not retained, so
all three were rebuilt with the runbook's reconstruction procedure. Every
rebuilt archive is byte-identical to its accepted final3 digest. These copies
are therefore the accepted artifacts. The accepted G0–G3 evidence in
[`evidence/qdrant-1.19.0-1/`](evidence/qdrant-1.19.0-1/) binds them, with no
G2 redo and no further G3 rerun. The rebuild record is
[`g0-g1-rebuild.json`](evidence/qdrant-1.19.0-1-rebind-2026-09-22/g0-g1-rebuild.json).
[`g3-attempt-1.json`](evidence/qdrant-1.19.0-1-rebind-2026-09-22/g3-attempt-1.json)
records an informational, non-gating harness run. It stopped on a host disk
precondition, not on a failure of the candidate.

## Disk Quota

The 85% threshold comes from the packaged production configuration:
`storage.quotas.max_disk_usage_percent: 85` with `release_margin_percent: 10`
in [`packages/qdrant/qdrant.config.yaml`](../../packages/qdrant/qdrant.config.yaml).
The G3 harness writes the same value into its disposable config, so production
enforces the same quota the harness hit. Above it, Qdrant answers writes with
HTTP 507.

The quota applies to the filesystem that holds `storage_path`
(`/var/lib/qdrant/storage`). On 2026-09-22 that filesystem on the host was
about 17% used. The filesystem that was about 92% used is the separate one
that holds `/tmp` and `/var/tmp`, where the harness work root lived. Production
Qdrant is not blocked today. The preflight still checks the storage filesystem
against the packaged threshold, including the rollback copy, and refuses to
proceed at or above it.

## Starting Point

A read-only probe of the host found:

- `qdrant` 1.17.1-1, installed from the `nisavid` repository
- loopback-only listeners on 6333 and 6334, no authentication, zero collections
- storage at `/var/lib/qdrant/storage`, mode 0750, owned by `qdrant:qdrant`
- the 1.17.1 unit, with no `EnvironmentFile` and no drop-ins
- `/etc/qdrant/config.yaml` unmodified from the 1.17.1 package

The pacman log shows the host ran 1.18.1 for a week in May 2026 before it was
downgraded to the current 1.17.1-1. Storage holds no collections, so the
empty-state route still applies. The rollback set captures the storage exactly
as it is now.

The 1.17.1 configuration does not disable telemetry. The 1.18.3 step therefore
runs with telemetry disabled and loopback-only egress.

## Route

### 1. Preflight

Hold `qdrant` at 1.17.1-1 until cutover. Once the `nisavid` repository offers
1.19.0-1, an ordinary `pacman -Syu` would jump straight from 1.17.1 to 1.19.0
and skip the accepted 1.18.3 step. Until cutover, refresh with
`sudo pacman -Syu --ignore qdrant`. `pacman(8)` documents `--ignore` as
ignoring upgrades of the named package, and it applies only to that one
command. Do not put `IgnorePkg = qdrant` in `/etc/pacman.conf` for this. If
it is already there, remove it before `cutover --apply` or `rollback --apply`:
both run `pacman --noconfirm` on `qdrant`, and the route does not rely on how
`--noconfirm` answers pacman's ignored-package prompt.

Preflight is read-only. Run it as root so it can size the state directory.

```bash
sudo tools/qdrant_production_cutover.zsh preflight
```

It refuses when any of these fails:

- **Installed identity.** `pacman -Q qdrant` is 1.17.1-1, and `pacman -Qii`
  reports `/etc/qdrant/config.yaml` unmodified.
- **Repository origin.** `pacman -Si nisavid/<name>` offers the accepted
  versions. The `nisavid` sync database lists each archive's accepted file
  name, size, and SHA-256. This holds only after
  [Publish the accepted-only package repository](https://github.com/nisavid/arch-pkgs/issues/57).
- **Baseline.** The pacman cache holds the 1.17.1-1 archive with the digest
  above.
- **Disk.** The storage filesystem is below the 85% quota, and stays below it
  after the rollback copy. If `--rollback-root` is on another filesystem, that
  filesystem must have room for the copy.
- **State.** The running server reports 1.17.1 and holds zero collections. A
  non-empty host must take the runbook's full migration route instead.
- **Consumers.** No client connection to 6333 or 6334 is open, and both
  `open-webui.service` and `hayhooks.service` are inactive or failed. Any other
  state, such as activating or reloading, refuses. Keep them stopped until
  verify passes.
- **HMAC secret.** If `/etc/qdrant/qdrant.env` exists, it already has the form
  that `qdrant-secret-preflight` requires: a regular file, owned by root, group
  `qdrant`, mode 0640, holding exactly one `QDRANT__SERVICE__API_KEY=` line of
  at least 64 lowercase hex characters. Cutover keeps a valid file. It
  provisions one only when the file is absent.
- **Fresh names.** The rollback set does not exist yet. The runtime credential
  does not exist yet either, unless `--reuse-credential` is passed and the
  credential matches the HMAC secret (see [Re-entry](#re-entry-after-a-failed-cutover)).

### 2. Cutover

```bash
sudo tools/qdrant_production_cutover.zsh cutover          # dry run
sudo tools/qdrant_production_cutover.zsh cutover --apply
```

`cutover --apply` reruns preflight and then:

1. Stops `qdrant.service`.
2. Saves the rollback set in `/var/lib/qdrant-rollback/qdrant-1.17.1-1-pre-1.19.0/`:
   - a copy of `/var/lib/qdrant`, checked against a SHA-256 listing
   - a copy of `/etc/qdrant`
   - the 1.17.1-1 archive
   - a `MANIFEST` of the installed `qdrant`, `qdrant-migration`, and
     `qdrant-web-ui` versions, and of the `qdrant.service` `EnvironmentFiles`
     and `DropInPaths` properties

   The archive also stays in the pacman cache and the `nisavid` repository.
3. Installs `nisavid/qdrant-migration`. It runs
   `/usr/lib/qdrant/migration/qdrant-1.18.3` once over the stopped storage, as
   the `qdrant` user in a transient unit with loopback-only egress. It waits
   for version 1.18.3, confirms zero collections, and stops the unit.
4. If it is absent, provisions `/etc/qdrant/qdrant.env` in the form that
   `qdrant-secret-preflight` requires: root-owned, group `qdrant`, mode 0640,
   and one `QDRANT__SERVICE__API_KEY=` line of 64 lowercase hex characters.
   It writes a temporary file in `/etc/qdrant`, checks it, and renames it into
   place, so a failed write never leaves an empty or partial `qdrant.env`.
5. Installs `nisavid/qdrant` and `nisavid/qdrant-web-ui`. It requires no
   `config.yaml.pacnew`, and `/etc/qdrant/config.yaml` must match the packaged
   1.19.0 file. It then reloads systemd and starts `qdrant.service`.
6. With the admin key, creates the five `open-webui-rag-v1` collections
   (`_memories`, `_knowledge`, `_files`, `_web-search`, `_hash-based`). Each
   has 2560 dimensions, cosine distance, `hnsw_config` `m: 0` and
   `payload_m: 16`, and keyword payload indexes on `tenant_id` (tenant),
   `metadata.hash`, and `metadata.file_id`. This matches Open WebUI 0.11's own
   multitenant schema.
7. Snapshots the still-empty `_memories` collection, restores it by upload,
   and removes both snapshot files.
8. Mints the runtime JWT: HS256 over the HMAC secret, with
   `{"access":[{"collection":"open-webui-rag-v1_<suffix>","access":"prw"}, …]}`
   for the five collections and no expiry. It encrypts the JWT with
   `systemd-creds encrypt --name=qdrant-runtime-api-key` to a temporary file
   and renames it to
   `/etc/credstore.encrypted/open-webui.qdrant-runtime-api-key`. Under
   `--reuse-credential`, it keeps the existing file that preflight matched
   instead. That is where
   the household `open-webui.service` loads it with `LoadCredentialEncrypted=`.
   The admin key and the JWT never appear in argv, in the environment, or in
   the repository. To rotate, re-provision the HMAC secret and re-mint the JWT.
   The credential name and path match the `LoadCredentialEncrypted=` line of
   the staged Open WebUI 0.11 candidate unit.
9. Restarts `qdrant.service` and waits for 1.19.0, so verify also proves the
   collections persist across a restart.
10. Runs verify.

The last output line starts with `HAND-BACK:`. It reports completion, or the
failing stage and the next commands to run. For a failure after the rollback
set is saved, it names both the rollback command and the re-entry command.

### Re-entry After a Failed Cutover

A cutover that fails after the rollback set is saved leaves behind the
provisioned `qdrant.env`. It may also leave the runtime credential, if the
failure came after delivery. Rollback keeps both. To try again after the cause
is fixed:

1. Run the rollback command from the `HAND-BACK:` line, and wait for
   `qdrant rollback COMPLETE`.
2. Run the re-entry command from either `HAND-BACK:` line. It has this form:

   ```bash
   sudo tools/qdrant_production_cutover.zsh cutover --apply \
     --rollback-set qdrant-1.17.1-1-pre-1.19.0-reentry-<UTC time> \
     [--reuse-credential]
   ```

The first rollback set stays in place, and the re-entry saves a fresh one from
the restored state. `--reuse-credential` appears only when the credential
exists. With it, preflight decrypts the credential and compares its SHA-256
with a token minted from the current `qdrant.env`. The runtime token has no
expiry and no issue time, so the same HMAC secret always mints the same bytes.
Preflight refuses on any mismatch. In that case, move the credential aside and
re-enter without the flag, so cutover mints a new one. Without the flag, an
existing credential always refuses, because rotation is a separate act.

### 3. Verify (post-install smoke)

```bash
sudo tools/qdrant_production_cutover.zsh verify
```

Verify checks that:

- the installed packages are `qdrant` 1.19.0-1, `qdrant-migration` 1.18.3-1,
  and `qdrant-web-ui` 0.2.16-1
- `GET /` reports 1.19.0, and `/readyz` returns 200
- HTTP and gRPC listen on `127.0.0.1:6333` and `127.0.0.1:6334`, and nothing
  else listens on a Qdrant port
- an unauthenticated `GET /collections` is refused with 401
- the storage filesystem is below the disk quota
- each of the five collections has the expected shape: 2560 cosine vectors,
  `hnsw_config` `m: 0` and `payload_m: 16`, `tenant_id` as a tenant keyword
  index, and keyword indexes on `metadata.hash` and `metadata.file_id`
- the decrypted runtime `prw` JWT can write one fresh, previously absent point to
  `open-webui-rag-v1_knowledge`, can delete that point again, and is refused
  (403) when it tries to create a collection
- a five-minute read-only (`r`) JWT is refused (403) when it tries to write

Open WebUI may write only after verify prints `HAND-BACK: qdrant verify PASSED`.

### 4. Rollback

Roll back if any of these happens:

- cutover or verify fails
- 1.19.0 fails to start, or restarts without a deliberate restart
- Qdrant rejects writes on a quota
- the Open WebUI household deploy is rolled back before the stability
  condition holds

Never open storage migrated by 1.18.3 or 1.19.0 with 1.17.1. Rollback restores
the untouched copy.

```bash
sudo tools/qdrant_production_cutover.zsh rollback          # dry run
sudo tools/qdrant_production_cutover.zsh rollback --apply
```

`rollback --apply`:

1. Checks the rollback set, and refuses before touching anything if any check
   fails:
   - The saved 1.17.1-1 archive has the digest above.
   - Every regular file in the saved state matches the `state.sha256` listing.
     The listing covers regular-file contents only. `cp -a` preserved the
     directories, ownership, modes, and timestamps, but the listing does not
     prove them.
   - The saved `config.yaml` matches the retained 1.17.1 configuration digest
     `23f9b7628f8886edf1d6dbd45216a3755eb28bcf00c1e38d391087de58c81bde`.
   - The filesystem that holds `/var/lib/qdrant` has more free space than the
     saved state. Moving the failed state aside frees nothing there.
   - For `qdrant-web-ui` or `qdrant-migration` that the manifest records as
     installed at a different version, the pacman cache holds that version's
     archive.
2. Stops `qdrant.service`.
3. Moves `/var/lib/qdrant` aside to `/var/lib/qdrant.failed-<UTC time>`, which
   is kept for inspection.
4. Copies the saved state back.
5. Runs `pacman -U` on the saved 1.17.1-1 archive.
6. Returns `qdrant-web-ui` and `qdrant-migration` to their manifest state. It
   removes a package that was not installed before, and reinstalls the
   recorded version from the pacman cache for one that was.
7. Restores `/etc/qdrant/config.yaml` from the set, owned by root:root with
   mode 0644 like the packaged file. It restores no other configuration file.
   It then reloads systemd, starts the service, and waits for 1.17.1.
8. Verifies the result, and fails loudly if any check does not hold:
   - `pacman -Q qdrant` is 1.17.1-1.
   - `/etc/qdrant/config.yaml` matches the retained 1.17.1 configuration
     digest.
   - The `EnvironmentFiles` and `DropInPaths` of `qdrant.service` equal their
     pre-cutover values in the manifest. On the host, both are empty.
   - `qdrant-web-ui` and `qdrant-migration` match the manifest.

`/etc/qdrant/qdrant.env` and the encrypted Open WebUI credential stay in
place for re-entry. The 1.17.1 unit does not read them. The final `HAND-BACK:`
line names the re-entry command.

### 5. Stability Condition

The cutover is stable when both of these hold:

- A post-cutover 1.19 snapshot has restored successfully.
- The service has run cleanly for seven days: no unplanned restart, no quota
  rejection, and no rollback trigger.

This is the retention condition that the packaged README and the frozen
runbook already set.

### 6. Retained Until Anchor Release

Until [Release retained rollback anchors and clean target-local state](https://github.com/nisavid/arch-pkgs/issues/62)
separately approves removal, keep:

- the rollback set: the 1.17.1 state and configuration copies, the 1.17.1-1
  archive, and the manifest
- the 1.17.1-1 archive in the pacman cache and in the `nisavid` repository
- the accepted `qdrant-migration`, `qdrant`, and `qdrant-web-ui` archives in
  the candidate store and the repository
- any `/var/lib/qdrant.failed-*` tree

## G4 in the Open WebUI Household Acceptance

G4 now runs inside
[Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89).
It composes the accepted Qdrant 1.19.0 server with Open WebUI instead of
Haystack and Hayhooks. This supersedes the frozen runbook's closing Haystack
G4 clause in
[`qdrant-migration-acceptance.md`](qdrant-migration-acceptance.md). That
runbook's bytes stay unchanged because the accepted G0–G3 evidence pins them
by digest.

G4 passes when the acceptance environment shows all of these on the exact
accepted bytes:

- fresh 1.19 state
- the five `open-webui-rag-v1` collections: 2560 dimensions, cosine, with
  payload indexes `tenant_id`, `metadata.hash`, and `metadata.file_id`. Open
  WebUI writes them only through the scoped `prw` JWT.
- one negative probe: a read-only token cannot write, and the `prw` token
  cannot create or delete collections
- one snapshot and restore drill
- one rollback drill
- loopback-only listeners
- no egress beyond loopback

G4 adds no gate beyond that ticket's end-state criterion. It cannot waive
G0–G3.
