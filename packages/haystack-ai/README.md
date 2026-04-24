# haystack-ai

Arch package for the Haystack Python framework.

The package name is `python-haystack-ai`. It exists mainly to support
`hayhooks`, but it is also useful when local Python applications should depend on
Haystack through pacman instead of a virtual environment.

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
