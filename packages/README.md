# Package Catalog

Each directory under `packages/` is a self-contained Arch package. Open a package
directory when you want its build recipe, service assets, patches, and local
notes.

## Inventory

Package freshness is checked per maintenance task. The package catalog was last
checked against upstream releases on 2026-05-23.

| Directory | Package | Packaged version | Upstream status | Use it when |
| --- | --- | --- | --- | --- |
| [`codex-app`](codex-app/) | `codex-app` | Ingested artifact | Source repo policy-managed | You want the unofficial Linux build of OpenAI Codex's desktop app packaged for pacman. |
| [`open-webui`](open-webui/) | `open-webui` | 0.9.5-1 | Current | You want Open WebUI managed by pacman and `systemd` with local-only service defaults. |
| [`ctranslate2`](ctranslate2/) | `ctranslate2`, `python-ctranslate2` | 4.7.2-1 | Current | You need a generic CPU/OpenBLAS CTranslate2 provider for Python applications. |
| [`qdrant`](qdrant/) | `qdrant` | 1.18.1-2 | Current | You need a local vector database with packaged service defaults. |
| [`hayhooks`](hayhooks/) | `hayhooks` | 1.19.1-1 | Current | You want to serve Haystack pipelines over HTTP from a system-managed service. |
| [`haystack-ai`](haystack-ai/) | `python-haystack-ai` | 2.29.0-1 | Current | You need the Haystack Python framework installed from pacman. |
| [`thorium-browser-updated`](thorium-browser-updated/) | `thorium-browser-updated` | 149.0.7827.114-4 | Metadata-only ingest | You want Thorium Browser built from source using the fixed tarball/tag recipe. |
| [`utilyze`](utilyze/) | `utilyze` | 0.1.1-2 | 0.1.3 available; focused patch-refresh lane | You want to inspect NVIDIA GPU utilization with the experimental Arch-patched TUI. |

## Supporting Python Packages

These packages exist because the primary stack depends on versions that are not
available locally in the desired shape:

| Directory | Package | Packaged version | Upstream status |
| --- | --- | --- | --- |
| [`python-backoff`](python-backoff/) | `python-backoff` | 2.2.1-1 | Current |
| [`python-docstring-parser`](python-docstring-parser/) | `python-docstring-parser` | 0.18.0-1 | Current |
| [`python-fastapi-openai-compat`](python-fastapi-openai-compat/) | `python-fastapi-openai-compat` | 1.2.0-1 | Current |
| [`python-haystack-experimental`](python-haystack-experimental/) | `python-haystack-experimental` | 0.19.0-1 | Current |
| [`python-lazy-imports`](python-lazy-imports/) | `python-lazy-imports` | 1.2.0-1 | Current |
| [`python-posthog`](python-posthog/) | `python-posthog` | 7.15.3-1 | Current |
| [`python-faster-whisper`](python-faster-whisper/) | `python-faster-whisper` | 1.2.1-1 | Current |
| [`python-rapidocr-onnxruntime`](python-rapidocr-onnxruntime/) | `python-rapidocr-onnxruntime` | 1.4.4-1 | Current |
| [`python-sentence-transformers`](python-sentence-transformers/) | `python-sentence-transformers` | 5.5.1-1 | Current |

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

Read a package's README first when it has package-local setup, service, or
verification notes.
