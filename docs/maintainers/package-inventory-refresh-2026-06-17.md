# Package Inventory Refresh: 2026-06-17

This refresh checked the package catalog against PyPI and GitHub releases on
2026-06-17.

## Auto-Upgrade Gate

For this repo, an agentic auto-upgrade is eligible when the candidate is a
stable release, keeps the same package source and install shape, does not need a
local patch refresh, does not introduce a new dependency/provider boundary, and
can be verified with package-local source and build checks in the current
workspace.

Candidates outside that gate stay tracked for manual package work.

## Adopted

| Package | From | To | Handling |
| --- | --- | --- | --- |
| `python-haystack-ai` | 2.29.0-1 | 2.30.1-1 | Adopted. Dependency metadata stays in the existing generic Python dependency set. Release notes call out `AzureOpenAIChatGenerator` accepting `Secret` values for endpoint and API version fields. |
| `hayhooks` | 1.19.2-1 | 1.20.0-1 | Adopted. Package service assets and defaults are unchanged. Release notes add real-time tracing dashboard updates over SSE with REST polling fallback. |
| `python-posthog` | 7.16.2-1 | 7.19.2-1 | Adopted. Runtime dependency metadata stays covered by the existing package dependencies. Build output now includes the expanded PostHog AI integration modules present in the upstream sdist. |
| `python-sentence-transformers` | 5.5.1-1 | 5.6.0-1 | Adopted. Dependency metadata remains within the existing system PyTorch/Transformers provider lane. Release notes focus on causal-LM reranker scoring fixes, hard-negative mining fixes, TSDAE restoration on Transformers 5, and MPS cached-loss support. |

Validation:

- `makepkg --verifysource` passed for all adopted packages.
- `makepkg -f` passed for all adopted packages.
- Built package payloads were inspected with `bsdtar -tf`.

## Tracked

| Package | Current | Candidate | Disposition |
| --- | --- | --- | --- |
| `open-webui` | 0.9.5-1 | 0.9.6 | Tracked. The release adds broad knowledge-base sync and filesystem-tool behavior, and this package carries Python 3.14 compatibility and system-ML-stack patching. Adopt through an explicit Open WebUI package lane with patch review. |
| `ctranslate2`, `python-ctranslate2` | 4.7.2-1 | 4.8.0 | Tracked. The release changes native C++ build inputs, including Thrust moving to CCCL 2.7.0 and Intel MKL behavior. Adopt through the split C++/Python package lane with submodule and ABI review. |
| `qdrant` | 1.18.1-2 | 1.18.2 | Tracked. The release is mostly bug fixes and service-runtime improvements, but the Rust service package needs a normal service-package build and smoke pass before adoption. |
| `thorium-browser-updated` | 149.0.7827.114-4 | 149.0.7827.155 | Tracked. This is a source-build browser lane with expensive full validation and metadata-only ingest rules; keep it out of the automatic package update path. |
| `utilyze` | 0.1.1-2 | 0.1.3 | Tracked. This package carries local Arch runtime/config/telemetry patches and still has an active NVIDIA validation lane. |

No candidates were rejected in this sweep.
