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
replays the frozen procedure, recipes, tests, public key material, and complete
Rust toolchain after every phase. Procedure, recipe, and test inputs must remain
regular files below their frozen canonical paths. The replay compares file
type, mode, size, content, and canonical location. The self-test checks that
boundary before and after execution and records both its test inputs and the
copied wrapper bytes that actually ran. The controller alone writes receipts
and admission markers.

Outside `inputs/rustup/`, frozen inputs admit only regular files and actual
directories. Freeze and every replay reject FIFOs, sockets, symlinks, and any
other object type in those input trees. The `inputs/rustup/` root itself must
be an actual directory; its descendants use the separate Rust toolchain
inventory below.

The retained Rust toolchain supports regular files, directories, and symlinks.
Setup and every later inventory replay reject all other filesystem object
types.

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
candidate-derived text never selects a controller-host file operation.

Every attempt directory is append-only by convention and is never reused.
Failures preserve the attempt's public source cache, package archive, logs, and
controller evidence. Secret-capable home, temporary, runtime, build, and XDG
directories are cleaned without inspecting their contents. No failed archive
is copied to `output/archives/`.

Final cleanup first admits every fixed `setup-scratch/` cache and every cache
for an accepted attempt. Each container and cache must be an actual directory
whose canonical path is its fixed path beneath the current run; symlinked
attempts and acceptance markers are rejected. Deletion begins only after the
complete selected set passes those checks. These checks prove containment at
their checkpoints, not atomic immutability against a concurrent same-account
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
`recipes/`, and `tests/` trees. Run each command with no inherited credentials:

```bash
cd NEW_RUN_DIRECTORY
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
  /usr/bin/bash procedure/final-cleanup.sh
env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  /usr/bin/bash procedure/assemble-evidence.sh \
  sequoia-sq-pqc=001 sequoia-sqv-pqc=001
```

If an invocation fails, retain its directory unchanged, diagnose from the
controller logs, and use the next unused three-digit attempt ID. Substitute
only the accepted IDs in `assemble-evidence.sh`. Never rename a failed attempt,
copy its archive into `output/`, or reuse its caches in another attempt.

Final assembly requires exactly one cleanup receipt with schema
`arch-pq-final-public-cache-cleanup-v2`, `toolchain_preserved=true`, and
`cleanup_exit=0`. It binds that receipt into provenance before inventory and
records operation, macOS interoperability, installation, rollback
authenticity, acceptance, and deployment as open gates.

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
