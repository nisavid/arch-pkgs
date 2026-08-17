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

- `authoritative_reference`: upstream `open-webui/open-webui` tag `v0.11.0` at
  commit `f9590b8017199e56d5e953657e6498e3cef1d246`, with PyPI source archive
  SHA-256 `e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9`
  and wheel SHA-256
  `71c266be87d0fb2cd79d9172d0e86a3b1b59d550d7054622b831344df07d361b`
- `advisory_references`: AUR `open-webui` packaging, including its PKGBUILD,
  `.install`, service, and config files; upstream release, installation,
  frontend-build, and `pyproject.toml` material
- `divergence_notes`:
  - The current recipe packages `0.9.5-1`; the selected source target is
    `0.11.0`, so the current recipe and its patches are not the accepted target.
  - The target uses Arch Python 3.14, a repository-owned private non-ML
    application closure, and system-owned ML and native providers. This
    deliberately diverges from upstream's Python `<3.13` constraint and exact
    dependency pins.
  - Re-derive the Python 3.14 and system-ML patches against `0.11.0`: retain the
    `<3.15` and PyArrow divergences, remove obsolete Pydantic and Psycopg
    changes, account for the RapidOCR successor, and assert that no
    externalized module, native library, distribution metadata, or console
    entry remains under `/opt/open-webui`.
  - Install service assets, secure defaults, user creation, and state
    directories as package payloads without a networked bootstrap. The target
    service has no Open WebUI TCP listener; it uses the normal Open WebUI
    `serve` path over `/run/open-webui/open-webui.sock` behind same-host HTTPS
    while preserving existing administrator choices and state.
- `update_notes`:
  - Keep this lane deferred and excluded from publication until the complete
    Open WebUI G0-G4 contract passes; a source update or successful build is not
    acceptance.
  - G0 must verify immutable sources and hashes, regenerated `.SRCINFO`, the
    exact Python 3.14/provider matrix and intentional upstream-pin divergences,
    patch intent, baseline metadata, and absence of secret or host-specific
    material.
  - G1 must produce clean packages with the declared Python and Node toolchains,
    build the frontend, inspect the full payload and service assets, and enforce
    the externalized-payload denylist.
  - G2 must install the exact CPU-forced provider set and pass offline RapidOCR,
    deterministic Sentence Transformers save/load, CTranslate2 model and
    malformed-model, Faster Whisper `int8` transcription and word-timestamp,
    Open WebUI import/version, and `pacman -Qo` ownership checks.
  - G3 must prove Unix-socket-only application service behind HTTPS `:443`,
    service hardening and identity, state/config/secret modes, effective
    persisted household access and privacy behavior, provider integration, and
    no unexpected egress.
  - G4 must pass browser workflows, cross-user privacy negatives, resource
    limits, both required migration fixtures, state preservation, and
    whole-runtime backup/restore rollback.

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
