# qdrant

Native Arch package for the Qdrant vector database.

Use this package when you want a local vector store managed by pacman and
`systemd`, with conservative localhost defaults.

## Package Contents

- `qdrant` binary
- `/etc/qdrant/config.yaml`
- `qdrant.service`
- `sysusers.d` entry for the `qdrant` service user
- `tmpfiles.d` entry for `/var/lib/qdrant`

## Defaults

| Setting | Value |
| --- | --- |
| HTTP bind | `127.0.0.1:6333` |
| gRPC bind | `127.0.0.1:6334` |
| Storage | `/var/lib/qdrant/storage` |
| Snapshots | `/var/lib/qdrant/snapshots` |

## Install And Run

For a one-off local install:

```bash
makepkg --verifysource
makepkg -si
sudo systemctl enable --now qdrant.service
```

For the repeatable local-repo workflow, build this package, refresh the `nisavid`
repo, and install `qdrant` through pacman. See
[`docs/usage/local-repo.md`](../../docs/usage/local-repo.md).
