# arch-pkgs

Personal Arch Linux packaging workspace for packages I install through a local
pacman repository.

It collects a small set of packages and service defaults that are useful for a
local AI application stack: Qdrant for vector storage, Haystack for pipeline
code, Hayhooks for serving those pipelines, and an experimental `utilyze`
package for NVIDIA GPU utilization inspection.

## What Lives Here

| Package | Version | Purpose |
| --- | ---: | --- |
| [`qdrant`](packages/qdrant/) | `1.17.1` | Vector database with packaged config and `systemd` service assets. |
| [`hayhooks`](packages/hayhooks/) | `1.17.0` | Haystack pipeline server with local service defaults. |
| [`utilyze`](packages/utilyze/) | `0.1.1` | Experimental NVIDIA GPU utilization TUI package with Arch-specific runtime and packaging patches. |
| [`python-haystack-ai`](packages/haystack-ai/) | `2.28.0` | Haystack framework package used by `hayhooks`. |
| [`python-haystack-experimental`](packages/python-haystack-experimental/) | `0.19.0` | Experimental Haystack components. |
| [`python-fastapi-openai-compat`](packages/python-fastapi-openai-compat/) | `1.2.0` | OpenAI-compatible FastAPI router dependency. |
| [`python-posthog`](packages/python-posthog/) | `7.13.0` | Python PostHog client dependency. |
| [`python-docstring-parser`](packages/python-docstring-parser/) | `0.18.0` | Python docstring parser dependency. |
| [`python-lazy-imports`](packages/python-lazy-imports/) | `1.2.0` | Lazy import helper dependency. |
| [`python-backoff`](packages/python-backoff/) | `2.2.1` | Retry/backoff helper dependency. |

Package-local docs live under `packages/<name>/`. Many packages use
`README.md` for repo-local notes, and some also ship an installed user-facing
doc such as `README.Arch.md`.

## Repository Layout

- `packages/<name>/` contains each package's build recipe and supporting files.
- `repo/x86_64/` is an ignored, rebuildable working tree for local pacman repo
  metadata.
- `tools/update_pacman_repo.zsh` stages built package archives into
  `repo/x86_64/` and refreshes the `nisavid` repo database.
- `docs/usage/local-repo.md` documents the repeatable local-repo workflow.

## Quick Start

Build a package from its package directory:

```bash
(cd packages/qdrant && makepkg --verifysource && makepkg -f)
```

Install a single package directly when you just need a one-off result:

```bash
(cd packages/qdrant && makepkg -si)
```

For the repeatable workflow, publish built archives into the local repo staging
area and install through pacman:

```bash
tools/update_pacman_repo.zsh packages/qdrant packages/hayhooks
sudo rsync -a --delete repo/x86_64/ /srv/pacman/nisavid/x86_64/
sudo pacman -Sy
sudo pacman -S qdrant hayhooks
```

See [Local Repo Usage](docs/usage/local-repo.md) for the full setup, including
the pacman repo stanza.

## Local Repo Workflow

The intended install path is a pacman repo named `nisavid`, published from the
ignored working tree in `repo/x86_64/`.

The helper is authoritative for the package names you pass to it: it removes the
old archives and repo entries for those package names, stages the current
archives reported by `makepkg --packagelist`, and refreshes the repo database.
Unrelated packages already present in the repo are left alone.

```bash
tools/update_pacman_repo.zsh packages/<pkgname>
```

The published repo path is intentionally outside the checkout:

```bash
sudo install -d /srv/pacman/nisavid/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/nisavid/x86_64/
```

## Using Services

The service packages install their `systemd` units and default config files, but
they do not start automatically.

- `qdrant` installs `/etc/qdrant/config.yaml` and `qdrant.service`. See
  [packages/qdrant](packages/qdrant/).
- `hayhooks` installs `/etc/hayhooks/hayhooks.env` and `hayhooks.service`. See
  [packages/hayhooks](packages/hayhooks/).

Enable services explicitly after install:

```bash
sudo systemctl enable --now qdrant.service
sudo systemctl enable --now hayhooks.service
```

## How This Repo Is Operated

This is a personal packaging repo maintained mostly through agent-assisted
workflows. The user-facing setup lives here and in `docs/usage/`; the maintainer
instructions live in `AGENTS.md` and the repo-local skills under
`.agents/skills/`.
