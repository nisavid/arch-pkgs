# Packages

Hand-maintained Arch packages live under `packages/<name>/`.

Each package directory should contain the build recipe and any supporting assets required to reproduce the package, such as:

- `PKGBUILD`
- `.SRCINFO`
- patches
- `systemd` unit files
- config defaults
- package-specific notes when the recipe needs extra context

For now this repo targets direct local builds and installs rather than a managed local pacman repository.
