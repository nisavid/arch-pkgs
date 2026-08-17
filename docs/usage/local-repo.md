# Local Repo Usage

Use a local pacman repo named `nisavid` when you want these packages to behave
like normal Arch packages during install, repair, and upgrade.

The workflow has four parts:

1. Build package archives with `makepkg`, or verify an artifact-ingest lane.
2. Refresh checkout-local repo metadata under `repo/x86_64/`.
3. Publish that repo to a pacman-visible path.
4. Install with `pacman` or an AUR helper.

## Before You Start

Install the Arch packaging tools and artifact-ingest prerequisites on the build
host:

```bash
sudo pacman -S --needed base-devel git jq libarchive python zsh zstd
```

The ChatGPT artifact-ingest lane uses GNU `cp` with `--reflink` support and
`bsdtar` from `libarchive`. Its `repo-add` and `repo-remove` commands come from
`pacman`, which `base-devel` installs.

The examples below use `/srv/pacman/nisavid/x86_64` as the published repo path.
That path is outside the checkout so pacman can read it without depending on a
private home directory.

## Build Packages

Build each package from its package directory:

```bash
(cd packages/<pkgname> && makepkg --verifysource && makepkg -f)
```

For a one-off install, you can still use `makepkg -si` from the package
directory. Use the local repo path when you want pacman to resolve and upgrade a
set of packages together.

## Refresh The Checkout-Local Repo

The staging repo lives in `repo/x86_64/`. It is ignored, rebuildable output, not
the durable source of package truth.

Refresh it from one or more built package directories:

```bash
tools/update_pacman_repo.zsh packages/qdrant
```

The helper asks each package directory for its current `makepkg --packagelist`
output, stages those archives, removes older repo entries for the same package
names, and leaves unrelated packages alone.

The ordinary updater, exact-artifact ingest, and publisher share one
repository-writer lock. They fail closed instead of snapshotting or promoting
staging while another writer is active.

When publishing an application package with local dependencies, such as
`hayhooks`, build and refresh the dependency package directories too.

Artifact-ingest lanes have their own verifier. For the ChatGPT fallback, pass
the complete published repository as the seed so unrelated packages remain
present, then run the exact ingest command documented in
[`packages/chatgpt/README.md`](../../packages/chatgpt/README.md):

```bash
tools/ingest_chatgpt.zsh \
  --artifact /path/to/chatgpt.pkg.tar.zst \
  --verification-record /path/to/verification-record.json \
  --record-sha256 RECORD_SHA256 \
  --source-dir /path/to/chatgpt-linux \
  --seed-repo-dir /srv/pacman/nisavid/x86_64
```

Run the staged verification in the package-local README before publication.

The helper reads the seed while holding the shared repository-writer lock and
accepts it only when checkout-local staging is otherwise empty. An existing
seed supplies the complete repository. A supplied seed path must exist; omit
the option to initialize the first repository. This keeps seeding and ingest in
one guarded transaction.

Never publish a partial staging directory: the publisher mirrors staging and
removes destination files that are absent from it.

## Publish A Pacman-Visible Copy

Create the published path once:

```bash
sudo install -d /srv/pacman/nisavid/x86_64
```

Then publish the current staging repo whenever it changes:

```bash
tools/publish_pacman_repo.zsh
```

The publisher locks the destination, hashes staging, copies it into a candidate
directory, verifies the candidate, atomically exchanges it with the current
destination, and compares the promoted destination with staging. It restores the
old repository on any post-promotion verification failure and retains the old
repository as a timestamped previous copy after success. Keep that copy until
the installed package passes acceptance. The verification manifest covers each
entry's content or symlink target together with its mode, UID, and GID.
If the new repository is verified but retaining the previous copy fails, the
publisher keeps the new repository live and preserves both transaction locks
and the old candidate path as explicit recovery state. In these patterns,
`PUBLISH_LEAF` is the final component of the published repository path, such as
`x86_64`, and `REPO_DIR` is checkout-local staging, such as `repo/x86_64`. The
recovery paths are `.PUBLISH_LEAF.candidate.*` and
`.PUBLISH_LEAF.publish.lock` beside the published repository,
`REPO_DIR.writer.lock` beside staging, and the manifest directory printed by
the publisher. Before retrying, verify the live repository against the
preserved staging manifest, reconcile the old candidate into a retained
`PUBLISH_LEAF.previous.*` copy, and release both locks only after those
identities are coherent. Preserve every path and stop when the identities are
ambiguous.
If the candidate path is absent while a `PUBLISH_LEAF.previous.*` copy exists,
inspect and explicitly accept that retained path as the rollback copy instead.
The preserved `staging.json`, `candidate.json`, and `published.json` manifests
all describe the new repository and prove its staged, candidate, and live
coherence; they do not authenticate the old rollback copy. Keep both locks and
all recovery paths when that rollback copy cannot be established safely.

Publication requires GNU coreutils 9.5 or newer and probes the target filesystem
for atomic-exchange support before promotion. By default it permits at most two
retained previous repositories. Set `ARCH_PKGS_PUBLISH_RETENTION` to another
positive bound when needed; reaching the bound fails closed and never deletes a
rollback copy automatically.

## Enable The Repo In Pacman

Create a small repo config file:

```bash
printf '%s\n' \
  '[nisavid]' \
  'SigLevel = Optional TrustAll' \
  'Server = file:///srv/pacman/nisavid/x86_64' \
  | sudo tee /etc/pacman.d/nisavid.conf >/dev/null
```

Include it from `/etc/pacman.conf` if it is not already included:

```bash
grep -qxF 'Include = /etc/pacman.d/nisavid.conf' /etc/pacman.conf \
  || echo 'Include = /etc/pacman.d/nisavid.conf' \
  | sudo tee -a /etc/pacman.conf >/dev/null
```

Refresh package metadata:

```bash
sudo pacman -Sy
```

## Install Packages

Use the package manager normally once the repo is enabled:

```bash
sudo pacman -S qdrant
```

Or with an AUR helper:

```bash
paru -S qdrant
```

## Refresh After A Rebuild

After rebuilding a package, refresh staging, publish it, and reload pacman's
package lists:

```bash
tools/update_pacman_repo.zsh packages/<pkgname>
tools/publish_pacman_repo.zsh
sudo pacman -Sy
```

Then upgrade or reinstall the package with normal pacman commands:

```bash
sudo pacman -S <pkgname>
```

## Notes

- `repo/x86_64/` is disposable staging output. Rebuild it from package
  directories when in doubt.
- The repo uses `SigLevel = Optional TrustAll` for a local, personal package
  source. Do not reuse that setting for an untrusted or shared repository.
- `amerge` is not part of this repo workflow yet. The current path is the
  explicit build, refresh, publish, and install sequence above.
