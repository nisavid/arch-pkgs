# Local Repo Usage

Use a local pacman repo named `nisavid` when you want these packages to behave
like normal Arch packages during install, repair, and upgrade.

The workflow has four parts:

1. Build package archives with `makepkg`.
2. Refresh checkout-local repo metadata under `repo/x86_64/`.
3. Publish that repo to a pacman-visible path.
4. Install with `pacman` or an AUR helper.

## Before You Start

Install the Arch packaging tools on the build host:

```bash
sudo pacman -S --needed base-devel git jq libarchive python rsync zsh zstd
```

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

The ordinary updater and publisher share one repository-writer lock. They fail
closed instead of snapshotting or promoting staging while another writer is
active.

`tools/retire_chatgpt.zsh` holds the candidate writer lock at
`${repo_dir}.writer.lock` through candidate construction and promotion. The
lock serializes cooperating repository tools. The invoking UID is trusted, and
observed identity drift fails closed. This does not provide strict inode-bound
deletion: a malicious same-UID process can race final pathname removal, just as
it can replace a checkout-local tool.

When publishing an application package with local dependencies, such as
`hayhooks`, build and refresh the dependency package directories too.

Never publish a partial staging directory: the publisher mirrors staging and
removes destination files that are absent from it.

For a lifecycle-managed terminal accepted-only publication, first follow the
[`package refresh lifecycle`](../policies/package-refresh-lifecycle.md).
Reconstruct staging from empty against the explicit accepted-artifact manifest
and reconcile every staged entry before running the publisher. The updater and
publisher preserve and promote repository contents; they do not decide whether
an artifact passed its lane's acceptance and promotion gates.

The former ChatGPT fallback lane is retired. Do not reconstruct it through the
ordinary updater. To withdraw a retained ChatGPT producer from a complete
repository, follow
[`docs/maintainers/chatgpt-retirement.md`](../maintainers/chatgpt-retirement.md)
and construct a separate reviewed candidate with `tools/retire_chatgpt.zsh`
before publication.

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
repository as a timestamped previous copy after success. Installed acceptance
is the minimum retention point for ordinary use. For a lifecycle-managed
publication, keep that copy through the lane's stability condition, rollback
proof, and explicit target-local cleanup authorization. The verification
manifest covers each entry's content or symlink target together with its mode,
UID, and GID.
If the new repository is verified but retaining the previous copy fails, the
publisher keeps the new repository live and preserves both transaction locks
and any candidate or previous path that remains as explicit recovery state. In
these patterns,
`PUBLISH_LEAF` is the final component of the published repository path, such as
`x86_64`, and `REPO_DIR` is checkout-local staging, such as `repo/x86_64`. The
recovery paths are `.PUBLISH_LEAF.candidate.*`,
`.PUBLISH_LEAF.failed.*`, and `.PUBLISH_LEAF.publish.lock` beside the published
repository, `REPO_DIR.writer.lock` beside staging, and the manifest directory
printed by the publisher. Before retrying, verify the live repository against
the preserved staging manifest, reconcile the old candidate into a retained
`PUBLISH_LEAF.previous.*` copy, and release both locks only after those
identities are coherent. Preserve every path and stop when the identities are
ambiguous.
If the candidate path is absent while a `PUBLISH_LEAF.previous.*` copy exists,
inspect and explicitly accept that retained path as the rollback copy instead.
A retained `.PUBLISH_LEAF.failed.*` directory together with both transaction
locks means the publisher could not prove the failed or rollback-copy identity.
Keep the failed directory and both locks until fresh identities establish its
role; do not treat it as disposable merely because its name contains `failed`.
If the pacman-visible repository remains populated after the publisher reports
that post-promotion identity is indeterminate, label that live repository
unverified. Do not refresh package metadata or install from it until a freshly
computed manifest proves whether it is the staged candidate or the prior
repository.
For the verified-but-unretained state, the preserved `staging.json`,
`candidate.json`, and `published.json` manifests are complete snapshots of the
new repository before and after promotion. In any other recovery state, one or
more manifests may be absent, incomplete, or intentionally different; treat
them as evidence to reconcile with freshly computed identities, not as proof.
None of these manifests authenticates the old rollback copy. Keep both locks
and all recovery paths when that rollback copy cannot be established safely.

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
  'SigLevel = Optional TrustedOnly' \
  'Server = file:///srv/pacman/nisavid/x86_64' \
  | sudo tee /etc/pacman.d/nisavid.conf >/dev/null
```

If an existing configuration still carries the former trust relaxation,
replace it explicitly and verify the result before refreshing metadata:

```bash
sudo sed -i \
  's/^SigLevel = Optional TrustAll$/SigLevel = Optional TrustedOnly/' \
  /etc/pacman.d/nisavid.conf
grep -qxF 'SigLevel = Optional TrustedOnly' /etc/pacman.d/nisavid.conf
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

This section is a development refresh path. Once a lifecycle candidate has been
accepted, do not rebuild it here. Stage and install the exact accepted identity,
or open an implementation ticket when the current tooling cannot do so without
rebuilding.

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

Package replacement also owns an adjacent detached package signature. A helper
must remove `<archive>.sig` together with the archive it replaces, or reject the
replacement while that stale signature remains; otherwise `repo-add` can bind
old signature data to new package bytes. This rule does not authorize deleting
repository database signatures such as `nisavid.db.tar.zst.sig` or
`nisavid.files.tar.zst.sig`. Those authenticate database files, not package
archives, and require their own configured verify-and-regenerate workflow.

## Notes

- In the development workflow, `repo/x86_64/` is disposable staging output and
  may be rebuilt from package directories. Terminal lifecycle staging is
  reconstructed from empty using only digest-bound promoted archives in the
  explicit manifest. Stop and open an implementation ticket when current
  tooling cannot stage those exact identities without rebuilding.
- The repo uses `SigLevel = Optional TrustedOnly` to accept unsigned local
  packages while requiring any present signature to come from a fully trusted
  key.
- `amerge` is not part of this repo workflow yet. The current path is the
  explicit build, refresh, publish, and install sequence above.
