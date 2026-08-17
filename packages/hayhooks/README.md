# hayhooks

Arch package for the Hayhooks service layer on top of Haystack.

Use this package when you want to serve Haystack pipelines from a local,
system-managed HTTP service.

## Maintenance Baseline

- `authoritative_reference`: upstream
  [`hayhooks` PyPI source and metadata](https://pypi.org/project/hayhooks/1.23.0/);
  no same-name Arch or AUR recipe was available at the 2026-08 refresh.
- `advisory_references`: upstream
  [Hayhooks releases](https://github.com/deepset-ai/hayhooks/releases) and the
  [Haystack migration guide](https://docs.haystack.deepset.ai/docs/migration).
- `divergence_notes`: the current recipe packages the `1.19.2` source
  distribution with a loopback-only, hardened `systemd` service, dedicated
  service user, and pacman-managed pipeline state. The selected `1.23.0`
  destination must retain that service shape while disabling production
  runtime deployment, dashboard builds, and dependency bootstrap; it has not
  yet been accepted.
- `update_notes`: verify immutable source identity and the Python 3.14 closure,
  build cleanly without runtime downloads, inspect the payload, then exercise
  reviewed YAML and wrapper loading, readiness, REST and OpenAI-compatible
  behavior, safe deserialization, migration, rollback, and the supported
  Qdrant-backed composed lane before publication.

## Package Contents

- `hayhooks` command and Python package files
- `/etc/hayhooks/hayhooks.env`
- `hayhooks.service`
- `sysusers.d` entry for the `hayhooks` service user
- `tmpfiles.d` entry for `/var/lib/hayhooks/pipelines`

## Defaults

| Setting | Value |
| --- | --- |
| Bind address | `127.0.0.1:1416` |
| Pipelines directory | `/var/lib/hayhooks/pipelines` |
| Environment file | `/etc/hayhooks/hayhooks.env` |

## Install And Run

Build and install the dependency packages first, then install `hayhooks`:

```bash
makepkg --verifysource
makepkg -si
sudo systemctl enable --now hayhooks.service
```

For multi-package installs, use the local repo workflow so pacman resolves the
Haystack dependency stack together. See
[`docs/usage/local-repo.md`](../../docs/usage/local-repo.md).
