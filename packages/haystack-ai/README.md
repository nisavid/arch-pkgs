# haystack-ai

Arch package for the Haystack Python framework.

The package name is `python-haystack-ai`. It exists mainly to support
`hayhooks`, but it is also useful when local Python applications should depend on
Haystack through pacman instead of a virtual environment.

## Maintenance Baseline

- `authoritative_reference`: upstream
  [`haystack-ai` PyPI source and metadata](https://pypi.org/project/haystack-ai/3.0.0/);
  no `python-haystack-ai` Arch or AUR recipe was available at the 2026-08
  refresh.
- `advisory_references`: upstream
  [Haystack releases](https://github.com/deepset-ai/haystack/releases) and the
  [Haystack migration guide](https://docs.haystack.deepset.ai/docs/migration).
- `divergence_notes`: the current recipe packages `2.29.0` from its source
  distribution and still depends on `python-haystack-experimental`. The
  selected `3.0.0` destination retires that archived dependency and adds the
  separately packaged Qdrant integration lane; the major-version migration has
  not yet been accepted.
- `update_notes`: freeze the selected source and Python 3.14 dependency closure,
  clean-build and inspect the package without runtime downloads, then prove
  offline sync and async behavior, serialization, lifecycle, rejected unsafe
  deserialization, v2-to-v3 pipeline and persisted-ID migration, Qdrant service
  composition, and a real rollback drill before publication.

## What It Installs

- Haystack Python framework files
- Pacman-managed Python dependencies declared by the package

It does not install a service unit. Use [`../hayhooks/`](../hayhooks/) when you
want a system-managed Haystack HTTP service.

## Build

```bash
makepkg --verifysource
makepkg -f
```

For installation with the rest of the stack, publish this package through the
local repo workflow in
[`docs/usage/local-repo.md`](../../docs/usage/local-repo.md).
