# hayhooks

Arch package for the Hayhooks service layer on top of Haystack.

Use this package when you want to serve Haystack pipelines from a local,
system-managed HTTP service.

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
