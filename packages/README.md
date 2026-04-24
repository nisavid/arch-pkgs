# Package Catalog

Each directory under `packages/` is a self-contained Arch package. Open a package
directory when you want its build recipe, service assets, patches, and local
notes.

## Primary Packages

| Directory | Package | Use it when |
| --- | --- | --- |
| [`qdrant`](qdrant/) | `qdrant` | You need a local vector database with packaged service defaults. |
| [`hayhooks`](hayhooks/) | `hayhooks` | You want to serve Haystack pipelines over HTTP from a system-managed service. |
| [`haystack-ai`](haystack-ai/) | `python-haystack-ai` | You need the Haystack Python framework installed from pacman. |
| [`utilyze`](utilyze/) | `utilyze` | You want to inspect NVIDIA GPU utilization with the experimental Arch-patched TUI. |

## Supporting Python Packages

These packages exist because the primary stack depends on versions that are not
available locally in the desired shape:

- [`python-backoff`](python-backoff/)
- [`python-docstring-parser`](python-docstring-parser/)
- [`python-fastapi-openai-compat`](python-fastapi-openai-compat/)
- [`python-haystack-experimental`](python-haystack-experimental/)
- [`python-lazy-imports`](python-lazy-imports/)
- [`python-posthog`](python-posthog/)

## Build And Publish

Build a package archive from its package directory:

```bash
(cd packages/<name> && makepkg --verifysource && makepkg -f)
```

Publish one or more built package outputs into the local repo staging area:

```bash
tools/update_pacman_repo.zsh packages/<name>
```

For the complete install workflow, including the pacman repo stanza, see
[`docs/usage/local-repo.md`](../docs/usage/local-repo.md).
