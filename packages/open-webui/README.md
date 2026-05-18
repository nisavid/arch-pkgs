# open-webui

Arch package for Open WebUI, a self-hosted AI web interface for Ollama and
OpenAI-compatible APIs.

Use this package when you want Open WebUI managed by pacman and `systemd`, with
local-only service defaults and persistent application data under
`/var/lib/open-webui`.

## Package Contents

- `open-webui` launcher
- private Python 3.14 application dependency tree under `/opt/open-webui`
- system-provided ML and native scientific dependencies
- `/etc/open-webui/open-webui.env`
- `open-webui.service`
- `sysusers.d` entry for the `open-webui` service user
- `tmpfiles.d` entries for `/var/lib/open-webui`

## Defaults

| Setting | Value |
| --- | --- |
| HTTP bind | `127.0.0.1:8080` |
| Ollama URL | `http://127.0.0.1:11434` |
| Data directory | `/var/lib/open-webui/data` |
| Cache directory | `/var/lib/open-webui/cache` |
| Environment file | `/etc/open-webui/open-webui.env` |

The packaged defaults disable Open WebUI's anonymous telemetry-related
environment flags. Users can still configure API keys, external model providers,
database settings, and feature flags in `/etc/open-webui/open-webui.env`.

## Maintenance Baseline

- `authoritative_reference`: `aur/open-webui`
- `advisory_references`: upstream `open-webui/open-webui` release notes and
  installation docs
- `divergence_notes`:
  - This package follows the latest stable upstream release instead of the
    older AUR package version.
  - This package installs service assets, config defaults, user creation, and
    state directories through normal package payloads instead of a networked
    post-install bootstrap.
  - This package carries a Python 3.14 compatibility patch for upstream
    metadata and pinned dependencies whose upstream versions do not have usable
    CPython 3.14 wheels or builds on this host.
  - This package externalizes the ML and native scientific stack to pacman
    packages instead of bundling PyPI's CUDA-oriented PyTorch closure.
- `update_notes`:
  - Diff the AUR PKGBUILD, `.install`, service unit, and config file before
    changing package layout or dependencies.
  - Recheck upstream `pyproject.toml`, release notes, and frontend build
    requirements before adopting a new upstream tag.
  - Treat Python interpreter compatibility and dependency unpinning as
    validation gates, not metadata-only edits.
  - Keep the private dependency tree free of `torch`, `triton`, `nvidia`,
    `transformers`, `sentence-transformers`, ONNX Runtime, OpenCV, NumPy,
    SciPy, pandas, PyArrow, and Pillow payloads.

## System ML Stack

This package expects ML and native scientific imports to come from pacman
packages. Install compatible platform-specific providers for PyTorch,
Transformers, ONNX Runtime, NumPy, Pillow, tokenizers, SentencePiece, and the
other generic dependency names listed in `depends`.

The generic package names remain in `depends` so optimized providers can satisfy
the same imports without changing this package.

## Install And Run

For a one-off local install:

```bash
makepkg --verifysource
makepkg -si
sudo systemctl enable --now open-webui.service
```

The service listens on `http://127.0.0.1:8080` by default. Edit
`/etc/open-webui/open-webui.env` before starting the service when you need a
different bind address, Ollama endpoint, or provider credentials.

For the repeatable local-repo workflow, build this package, refresh the `nisavid`
repo, and install `open-webui` through pacman. See
[`docs/usage/local-repo.md`](../../docs/usage/local-repo.md).
