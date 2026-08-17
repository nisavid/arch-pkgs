# qdrant

Native Arch package for the Qdrant vector database.

Use this package when you want a local vector store managed by pacman and
`systemd`, with conservative localhost defaults.

## Maintenance Baseline

- `authoritative_reference`: AUR
  [`qdrant`](https://aur.archlinux.org/packages/qdrant) at the selected `1.18.3`
  migration baseline.
- `advisory_references`: upstream Qdrant
  [releases](https://github.com/qdrant/qdrant/releases),
  [upgrade guidance](https://qdrant.tech/documentation/upgrades/), and the
  [`qdrant-web-ui` releases](https://github.com/qdrant/qdrant-web-ui/releases).
- `divergence_notes`: the current `1.18.1-2` recipe adds a dedicated user,
  loopback-only hardened service, pacman-managed configuration and state paths,
  and telemetry-disabled defaults. The selected route uses `1.18.3` as a
  mandatory migration intermediate before `1.19.0`, then adds a separately
  packaged Web UI plus fail-closed scoped authentication and response headers;
  that destination has not yet been accepted.
- `update_notes`: verify pinned release identities and hashes, clean-build and
  inspect the server, intermediate, and Web UI packages, then pass disposable
  fresh-runtime, authentication, consecutive-minor migration, snapshot and
  cold-copy recovery, corruption-rejection, rollback, and complete
  Haystack/Hayhooks HTTP and gRPC composition gates before publication.

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
| Usage telemetry | disabled |
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
