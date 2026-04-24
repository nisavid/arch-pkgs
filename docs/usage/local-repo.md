# Local Repo Usage

Use a local pacman repo named `nisavid` when you want these packages to behave
like normal Arch packages during install, repair, and upgrade.

The workflow has four parts:

1. Build package archives with `makepkg`.
2. Refresh checkout-local repo metadata under `repo/x86_64/`.
3. Publish that repo to a pacman-visible path.
4. Install with `pacman` or an AUR helper.

## Before You Start

Install the usual Arch packaging tools on the build host:

```bash
sudo pacman -S --needed base-devel
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

When publishing an application package with local dependencies, such as
`hayhooks`, build and refresh the dependency package directories too.

## Publish A Pacman-Visible Copy

Create the published path once:

```bash
sudo install -d /srv/pacman/nisavid/x86_64
```

Then publish the current staging repo whenever it changes:

```bash
sudo rsync -a --delete repo/x86_64/ /srv/pacman/nisavid/x86_64/
```

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
sudo rsync -a --delete repo/x86_64/ /srv/pacman/nisavid/x86_64/
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
