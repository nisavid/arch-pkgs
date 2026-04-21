# arch-pkgs

Personal Arch package repository for locally maintained packages.

## Layout

- `packages/<name>/` contains each package's build files and supporting assets.
- `repo/x86_64/` is the rebuildable working tree for the local pacman repo metadata.
- `tools/update_pacman_repo.zsh` refreshes `repo/x86_64/` from built package archives.

## Usage

Build a package from its directory with `makepkg -f`.

For a one-off install, you can still use `makepkg -si` or `pacman -U`.

For a repeatable local-repo workflow, see `docs/usage/local-repo.md`.
