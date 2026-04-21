# qdrant

Native Arch package for the Qdrant vector database.

## Package contents

- `qdrant` binary
- packaged config at `/etc/qdrant/config.yaml`
- `systemd` service
- `sysusers.d` entry for the `qdrant` service user
- `tmpfiles.d` entry for `/var/lib/qdrant`

## Defaults

- HTTP bind: `127.0.0.1:6333`
- gRPC bind: `127.0.0.1:6334`
- storage: `/var/lib/qdrant/storage`
- snapshots: `/var/lib/qdrant/snapshots`

## Local install

```sh
makepkg -si
sudo systemctl enable --now qdrant.service
```
