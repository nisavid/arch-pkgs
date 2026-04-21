# Local Repo Usage

The intended installation story for this repo is a local pacman repo named
`nisavid`.

That keeps installs, repairs, and upgrades inside normal package-manager
transactions instead of long `pacman -U` command lists.

## Build Packages

Build any package directory with normal `makepkg` usage:

```bash
(cd packages/<pkgname> && makepkg -f)
```

Do that for each package you want to publish into the local repo.

## Refresh The Working Repo

The checkout-local repo lives in `repo/x86_64/`. It is intentionally ignored and
rebuildable on each machine, so do not treat it as canonical until you refresh
it from current package outputs.

Refresh it from one or more built package directories:

```bash
tools/update_pacman_repo.zsh packages/qdrant packages/hayhooks
```

That command publishes only the archives named by each current `PKGBUILD` and
replaces those package names authoritatively in `repo/x86_64/`, while leaving
unrelated packages already present in the repo alone.

## Publish A Pacman-Visible Copy

Pacman should read a world-traversable published path rather than a repo checkout
inside a private home directory.

Recommended published path:

- `/srv/pacman/nisavid/x86_64`

Publish the current working repo like this:

```bash
sudo install -d /srv/pacman/nisavid/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/nisavid/x86_64/
```

## Enable The Repo In Pacman

Create the pacman repo stanza:

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

Once the repo is enabled, use normal package-manager commands:

```bash
paru -S qdrant hayhooks
```

Or with pacman directly:

```bash
sudo pacman -S qdrant hayhooks python-haystack-ai
```

## Refresh After A Rebuild

After rebuilding a package, refresh the working repo, republish it, and reload
pacman's package lists:

```bash
tools/update_pacman_repo.zsh packages/<pkgname>
sudo rsync -a --delete repo/x86_64/ /srv/pacman/nisavid/x86_64/
sudo pacman -Sy
```

## Future Repo Management

`amerge` is not part of this repo workflow yet.

The intent is to later extract `amerge` from `arch-strix-halo-pkgs` into its own
package and use that shared tool as the local-repo package manager for both
repos. Until then, this repo uses the explicit build, refresh, publish, and
install steps documented here.
