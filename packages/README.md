# Packages

Hand-maintained Arch packages live under `packages/<name>/`.

Each package directory should contain the build recipe and any supporting assets required to reproduce the package, such as:

- `PKGBUILD`
- `.SRCINFO`
- patches
- `systemd` unit files
- config defaults
- package-specific notes when the recipe needs extra context

Build package archives from these directories with normal `makepkg` usage.

Use `tools/update_pacman_repo.zsh` to publish built outputs into the local repo
staging area under `repo/x86_64/`, then install them through pacman once the
published repo is enabled.
