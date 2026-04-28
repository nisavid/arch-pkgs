# arch-pkgs

Personal Arch Linux packages for a local AI application stack.

This repository collects packages that are useful enough to keep close, patched,
and installable through a local pacman repository. It is not a public distro or a
general AUR mirror. It is a small workspace for reproducible local packages:
Codex desktop app packaging, vector storage, Haystack services, their Python
dependencies, and an experimental GPU inspection tool.

## What You Can Install

The full package catalog lives in [`packages/README.md`](packages/README.md).
Use it when you need all packages, package names, categories, and package-local
notes.

Start with the package family that matches what you want to install:

- [`codex-app`](packages/codex-app/) packages the unofficial Linux build of
  OpenAI Codex's desktop app for pacman.
- [`qdrant`](packages/qdrant/) and [`hayhooks`](packages/hayhooks/) provide the
  local service layer for vector storage and Haystack pipeline serving.
- [`python-haystack-ai`](packages/haystack-ai/) and its companion Python
  packages support local Haystack work where the desired versions are not
  available in the right shape.
- [`electron41`](packages/electron41/) provides a source-built Electron runtime
  for packages that need that major line.
- [`utilyze`](packages/utilyze/) is an experimental NVIDIA GPU utilization TUI
  with Arch runtime, config, update, and telemetry-consent patches.

> [!NOTE]
> `utilyze` is packaged and partially verified, but it still needs runtime
> validation on supported NVIDIA hardware. Read
> [`packages/utilyze/README.Arch.md`](packages/utilyze/README.Arch.md) before
> first use.

## Start Here

If you want one package quickly, build and install it from its package directory:

```bash
(cd packages/qdrant && makepkg --verifysource && makepkg -si)
```

If you want the normal workflow, build a package, refresh the local repo staging
area, publish it to a pacman-visible path, and install through pacman:

```bash
(cd packages/qdrant && makepkg --verifysource && makepkg -f)
tools/update_pacman_repo.zsh packages/qdrant
sudo rsync -a --delete repo/x86_64/ /srv/pacman/nisavid/x86_64/
sudo pacman -Sy
sudo pacman -S qdrant
```

The full local-repo setup, including the pacman stanza, is in
[`docs/usage/local-repo.md`](docs/usage/local-repo.md).

## Choose Your Path

- **I want to browse packages.** Start with the
  [`packages/`](packages/) catalog, then open the package directory you care
  about.
- **I want to install from a local repo.** Follow
  [`docs/usage/local-repo.md`](docs/usage/local-repo.md).
- **I want to run services.** Read the package docs for
  [`qdrant`](packages/qdrant/) and [`hayhooks`](packages/hayhooks/); their units
  install disabled and must be enabled explicitly.
- **I want to try `utilyze`.** Read
  [`packages/utilyze/README.Arch.md`](packages/utilyze/README.Arch.md), then
  check the active validation work in [`docs/backlog.md`](docs/backlog.md).
- **I am maintaining the repo.** Read `AGENTS.md` and the repo-local skills in
  `.agents/skills/`.

## Repository Map

- `packages/<name>/` contains each Arch package: `PKGBUILD`, `.SRCINFO`, patches,
  service files, config defaults, and package-local notes.
- `repo/x86_64/` is ignored, rebuildable local-repo staging output.
- `tools/update_pacman_repo.zsh` refreshes `repo/x86_64/` from the current
  package archives reported by `makepkg --packagelist`.
- `docs/usage/` contains user and operator how-to guides.
- `docs/maintainers/` contains decision notes for package-maintenance work.
  The Arch CUDA container image is documented in
  [`docs/maintainers/arch-cuda-image.md`](docs/maintainers/arch-cuda-image.md).

## Services

Service packages install their units and default config files, but they do not
start automatically.

```bash
sudo systemctl enable --now qdrant.service
sudo systemctl enable --now hayhooks.service
```

Defaults are intentionally local:

- `qdrant`: `/etc/qdrant/config.yaml`, `127.0.0.1:6333`, storage under
  `/var/lib/qdrant/`.
- `hayhooks`: `/etc/hayhooks/hayhooks.env`, `127.0.0.1:1416`, pipelines under
  `/var/lib/hayhooks/pipelines/`.

## How This Repo Is Operated

This is a personal packaging repo maintained mostly through agent-assisted
workflows. Human-facing usage docs stay in this README, `docs/usage/`, and
package READMEs. Maintainer policy and agent instructions live in `AGENTS.md`
and `.agents/skills/`.
