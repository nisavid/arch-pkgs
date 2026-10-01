# Hatchery PQ Sequoia build procedure

This controller produces a new, unsigned release-4 build candidate and binds
its evidence without granting acceptance, installation, signing, publication,
or deployment authority. A candidate is an inert output until all later gates
are independently completed.

## Trust boundary

The controller owns `control/`, `setup-evidence/`,
`attempts/*/controller-source/`, `attempts/*/receipts/`,
`attempts/*/logs/`, `attempts/*/extracted/`, and `output/`. Build phases never
mount those paths. They receive only these paths:

- read-only: `procedure/`, the selected `recipes/<package>/`,
  `inputs/rustup/`, `inputs/gnupg-public/`, and system build dependencies;
- writable: the current attempt's directories below `attempts/<name>/work/`;
- networked: `verifysource` and `prefetch` only;
- unshared network: `boundary` and `checked-build`;
- controller-local: source-view capture and post-build verification, followed
  by candidate runtime checks in a separate offline namespace.

`prefetch` runs `makepkg --nobuild`; `checked-build` reuses that prepared tree
with `--noextract --holdver` and Cargo offline mode. The trusted controller
first admits the staged procedure, recipes, and tests against an externally
provided `review-admission/` bundle, then replays the frozen admission bundle,
maintained source, public key material, and complete Rust toolchain after every
phase. The bundle contains one reviewed revision and a sorted mapping from each
repository path to its staged path, object type, mode, byte count, and SHA-256.
The run consumes this bundle without regenerating it from staged bytes.
Procedure, recipe, and test inputs must remain regular files below their frozen
canonical paths. Admission and replay compare file type, mode, size, content,
mapping, and canonical location. The self-test checks that
boundary before and after execution and records both its test inputs and the
copied wrapper bytes that actually ran. Its inert wrapper cases prove early and
late failure non-admission and the complete successful archive-admission path,
including immediate and copied-output digests. The controller alone writes
receipts and admission markers. A successful self-test creates the fixed
`control/lifecycle-admission.txt` record. It lists the canonical prebuild,
common-setup, frozen-boundary, and self-test receipts in that order, binds each
receipt's exact bytes and SHA-256 to the preceding chain digest, and terminates
with one success field. Each real attempt revalidates the prerequisite schemas,
unique success fields, frozen-boundary receipt, exact digests, and complete
closed-world chain before it creates attempt state, then records the lifecycle
admission SHA-256 in its launcher receipt.

Attempt initialization is a separate controller seam. Before it creates a
staging tree, the controller installs failure handling. It claims the package,
three-digit attempt ID, and lifecycle digest in
`attempts/.initializing-<package>-attempt-<ID>/`, builds the complete attempt
tree there, atomically publishes and validates the regular version-3 launcher
receipt, then atomically renames the tree to its canonical
`attempts/<package>-attempt-<ID>/` path. Canonical prior attempts must have one
matching schema, package, attempt ID, initialization-claim digest, and lifecycle
digest. A missing, malformed, duplicated, identity-mismatched, or
lifecycle-mismatched field rejects the next invocation. The shared
`validate-canonical-attempt.sh` interface checks the staged and canonical paths,
requires the fixed regular `initialization-claim.txt`, matches its exact
schema-1 bytes to the expected package, attempt, and lifecycle values, and binds
its SHA-256 to the unique version-3 launcher field. `initialize-attempt.sh`
invokes that interface before and after publication and when admitting every
canonical prior attempt.

A failed initialization remains in its hidden staging path and prevents reuse
of that ID without entering the canonical prior-attempt set. A later unused ID
may proceed with the same lifecycle digest. This recovery contract covers one
controller and ordinary filesystem failures, catchable signals, and abrupt
interruption. It excludes concurrent same-account writers, catastrophic
storage loss, and guaranteed retained evidence when no write can succeed.

Outside `inputs/rustup/`, frozen inputs admit only regular files and actual
directories. Freeze and every replay reject FIFOs, sockets, symlinks, and any
other object type in those input trees. The `inputs/rustup/` root itself must
be an actual directory; its descendants use the separate Rust toolchain
inventory below.

The retained Rust toolchain supports regular files, directories, and confined
relative symlinks. Every symlink hop and its final regular-file or directory
target must remain beneath the canonical `inputs/rustup/` root. Setup and every
later inventory replay reject absolute, escaping, broken, or cyclic symlink
chains and all other filesystem object types.

After prefetch and before checked build, the controller copies only the Git
object and reference data for the expected tag into an unmounted, read-only
bare repository. It rejects alternates, linked worktree metadata, symlinks,
and special files rather than processing repository-local configuration or
hooks, then binds every source-view file plus the expected tag object and
commit. Post-build verification replays that view,
disables replacement objects, forces OpenPGP and `/usr/bin/gpg` at command
scope, and verifies the tag from the controller-owned view. Later changes to
the writable build source cannot select the verifier or replace the objects
used by the controller.

Post-build verification rejects absolute paths, parent traversal, duplicate
archive members, and member types other than directories and regular files
before data-only extraction. It scans every payload file, including decompressed
gzip manpages, for execution paths. Candidate `ldd`, dependency resolution,
identity, and lifecycle checks run in a separate offline namespace with the
extracted tree read-only and only disposable runtime state writable. The
namespace resolves, hashes, and queries ownership for reported runtime objects;
candidate-derived text never selects a controller-host file operation. Runtime
closure parsing normalizes leading whitespace, rejects every `not found` entry,
deduplicates reported absolute paths, and emits one ownership and digest record
for each resolved object, including a directly reported loader.

Every canonical or staged attempt directory is append-only by convention and
is never reused. Initialization failures preserve the staged claim and any
bytes written before failure. Later failures preserve the canonical attempt's
public source cache, package archive, logs, and controller evidence.
Secret-capable home, temporary, runtime, build, and XDG directories are cleaned
without inspecting their contents. No failed archive is copied to
`output/archives/`.

Final cleanup receives exactly one accepted attempt for each package. Before
deletion, it validates both acceptance markers, launcher results, output-archive
receipts, archive digests, fixed `setup-scratch/` caches, and the selected
attempt caches. Each container and cache must be an actual directory whose
canonical path is its fixed path beneath the current run; symlinked attempts
and acceptance markers are rejected. Its canonical receipt rows bind package,
attempt, archive digest, and empty Cargo/source-cache results. Assembly requires
that exact set and rechecks the selected caches. Before either cleanup deletion
or assembly output, `validate-canonical-attempt.sh accepted` binds the selected
canonical path to the current lifecycle admission, exact launcher identity and
success fields, retained initialization claim, acceptance marker, and exact
output archive receipt. Once the cleanup receipt exists, no later real attempt
is admitted. Final assembly reads each executable directly from the validated
selected archive, requires its digest to equal both the canonical post-build
executable receipt and the retained extraction, and publishes that
archive-derived digest. These checks prove containment, identity, and emptiness
at their checkpoints, not atomic immutability against a concurrent same-account
writer that can replace controller-owned paths between validation and use.

## Prerequisites

The successor operator must confirm these existing Arch packages before setup:
`base-devel`, `bubblewrap`, `curl`, `git`, `gnupg`, `libarchive`, `pacman`,
`rustup`, `zstd`, `capnproto`, `clang`, `openssl`, `glibc`, `libgcc`, `sqlite`,
`sequoia-sq`, and `sequoia-sqv`. The target architecture is `x86_64`; OpenSSL
must be 3.5 or later. `/run/systemd/resolve/` and its `stub-resolv.conf` must
exist for the two networked source phases and the prebuild evidence capture.
No procedure command installs a system package.

The setup phase is the only phase that installs a Rust toolchain, imports the
included public verification key into a dedicated keyring, or accesses their
public distribution endpoints. Those actions require successor authority not
granted by the correction task.

## Successor invocation

Start from a fresh run directory containing these maintained `procedure/`,
`recipes/`, and `tests/` trees plus the external `review-admission/` bundle
accepted for those exact bytes. The bundle must contain only
`source-revision.txt` (one lowercase 40-hex revision) and
`maintained-source.inventory.tsv` with this header:

```text
type	mode	bytes	sha256	repository_path	staged_path
```

Rows are sorted by staged path and cover every regular file in the three
maintained trees. Repository paths map `procedure/` and `tests/` below
`scripts/hatchery/sequoia-pqc-build/`; `recipes/` maps below `packages/`.
The source-review/coordinator boundary produces the bundle. The build operator
must not derive or replace it from the staged run. Run each command with no
inherited credentials:

```bash
cd NEW_RUN_DIRECTORY
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/verify-reviewed-source.sh
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/capture-prebuild.sh
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/setup-common.sh
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/freeze-boundary.sh
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/failure-boundary-self-test.sh
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/invoke-attempt.sh sequoia-sq-pqc 001
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/invoke-attempt.sh sequoia-sqv-pqc 001
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/final-cleanup.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001
```

`failure-boundary-self-test.sh` creates the lifecycle admission record only
after its own frozen-input replay and wrapper proof succeed. Do not create,
replace, reorder, or repair that record by hand. A changed prerequisite requires
a fresh run directory; every selected attempt must bind the one admission
digest created in that run.

If an invocation fails, retain its directory unchanged, diagnose from the
controller logs, and use the next unused three-digit attempt ID. Substitute the
same accepted IDs in `final-cleanup.sh` and `assemble-evidence.sh`. Never rename
a failed attempt, copy its archive into `output/`, reuse its caches in another
attempt, or invoke a later real attempt after finalization starts.

Final assembly requires exactly one cleanup receipt with schema
`arch-pq-final-public-cache-cleanup-v3`, exactly two canonical selection rows,
`toolchain_preserved=true`, and `cleanup_exit=0`. It matches those rows against
the selected attempts and archive digests, rechecks both cache pairs, revalidates
the same lifecycle record and all four prerequisite receipts, and requires both
selected launcher receipts to bind its current digest. It retains exact copies
of the lifecycle admission and prerequisite records plus source and retained
digests before inventory. It derives each final executable identity through a
fresh data-only read of the selected archive and requires equality with the
post-build receipt and retained executable before writing final evidence. Only
then does it record the candidates as built by a procedure-complete run.
Operation, macOS interoperability, installation, rollback authenticity,
acceptance, and deployment remain open gates.

## Gate separation

These states are distinct and must not be collapsed:

1. corrected maintained source;
2. independently accepted procedure revision;
3. newly built candidate and controller evidence;
4. downstream cryptographic-operation and macOS interoperability qualification;
5. installation and authenticated rollback qualification;
6. independent acceptance, then any separately authorized deployment.

A clean build closes none of the downstream operation, macOS interoperability,
installation, rollback-authenticity, acceptance, or deployment gates.
