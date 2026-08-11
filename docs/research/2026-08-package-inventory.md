# Package Inventory And Release Candidates

## Provenance

This inventory was researched on 2026-08-11 from immutable repository commit
`ca744c74ea8bca30c6ac3166b7e1006821c51dba` (`main` at the start of the
research) in a directly created isolated worktree on branch
`research/package-inventory-2026-08`.

The packaged versions come from the tracked package directories at that commit.
Candidate versions and dates come from upstream GitHub releases or PyPI release
metadata. Arch-facing baselines come from live AUR package metadata and recipes.
The AUR had no same-name result on the research date where this note says there
is no Arch-facing recipe. A candidate is an input to a later disposition
decision, not an instruction to update.

## Inventory

| Package directory | Packaged source version | Current candidate and release date | Authoritative baseline | Likely compatibility lane | Decision-relevant changes |
| --- | --- | --- | --- | --- | --- |
| [`codex-app`](../../packages/codex-app/README.md) | Ingested artifact; this repository tracks no version | [`nisavid/codex-app-linux` `main` at `98f2338`](https://github.com/nisavid/codex-app-linux/commit/98f2338d19fb148867d9fe64062694a3b870db0d), 2026-06-19; a fresh build determines the package version | [`openai-codex-desktop` in AUR](https://aur.archlinux.org/packages/openai-codex-desktop) for the Arch conversion shape; `nisavid/codex-app-linux` remains authoritative for this workspace's ingest artifact | Codex artifact ingestion and supply chain | There is no upstream release or immutable artifact in this repository to select directly. The source fork converts the official DMG, carries Linux patches, and has its own release gate; disposition must bind the input DMG, generated package version, fork commit, and build evidence rather than treating a Git commit as the package version. |
| [`ctranslate2`](../../packages/ctranslate2/PKGBUILD) | `4.7.2-1` | [`4.8.1`](https://github.com/OpenNMT/CTranslate2/releases/tag/v4.8.1), 2026-07-03 | [`ctranslate2` in AUR](https://aur.archlinux.org/packages/ctranslate2), currently `4.7.1-1`; preserve the local CPU/OpenBLAS split-package divergences | CTranslate2 and Faster Whisper runtime | `4.8.0` moved the Thrust submodule to CCCL 2.7.0; `4.8.1` hardens legacy checkpoint loading and fixes a model-load heap overflow and a Whisper alignment division-by-zero. The source/submodule set and runtime smoke tests matter more than a metadata-only bump. |
| [`hayhooks`](../../packages/hayhooks/PKGBUILD) | `1.19.2-1` | [`1.23.0`](https://github.com/deepset-ai/hayhooks/releases/tag/v1.23.0), 2026-07-30 | Upstream [PyPI metadata](https://pypi.org/project/hayhooks/1.23.0/) and source; [no same-name AUR recipe](https://aur.archlinux.org/packages?O=0&K=hayhooks) | Haystack and Hayhooks service stack | The `1.19.2...1.23.0` source comparison adds explicit Haystack 2/3 compatibility, A2A protocol support, a real-time tracing dashboard, and input coercion. Current metadata still allows Haystack 2 or 3, so the service can be tested across the framework migration rather than forcing the major upgrade by itself. |
| [`haystack-ai`](../../packages/haystack-ai/PKGBUILD) | `2.29.0-1` | [`3.0.0`](https://github.com/deepset-ai/haystack/releases/tag/v3.0.0), 2026-07-20 | Upstream [PyPI metadata](https://pypi.org/project/haystack-ai/3.0.0/) and source; [no `python-haystack-ai` AUR recipe](https://aur.archlinux.org/packages?O=0&K=python-haystack-ai) | Haystack and Hayhooks service stack | This is a migration, not a routine update. Haystack 3 removes legacy generators, `ToolInvoker`, and `AsyncPipeline`; moves many integrations out of core; changes agent hooks and resource lifecycle; makes tracing explicit; and no longer depends on `haystack-experimental`. Pipeline YAML and Hayhooks behavior require compatibility validation against the upstream migration guide. |
| [`open-webui`](../../packages/open-webui/PKGBUILD) | `0.9.5-1` | [`0.11.0`](https://github.com/open-webui/open-webui/releases/tag/v0.11.0), 2026-07-27 | [`open-webui` in AUR](https://aur.archlinux.org/packages/open-webui), currently `0.11.0-1` | Open WebUI and system ML stack | Upstream metadata still requires Python `>=3.11,<3.13`, while this package targets Python 3.14 through local patches. The dependency surface now includes `rapidocr==3.9.2`, `transformers==5.5.4`, `onnxruntime==1.26.0`, and many newly pinned application dependencies. New outward-facing capabilities include notification webhooks and optionally unauthenticated chat sharing; the latter remains administrator-gated and off by default. Rebase the system-ML and privacy defaults deliberately. |
| [`python-backoff`](../../packages/python-backoff/PKGBUILD) | `2.2.1-1` | [`2.2.1`](https://pypi.org/project/backoff/2.2.1/), 2022-10-05 | [`python-backoff` in AUR](https://aur.archlinux.org/packages/python-backoff), currently `2.2.1-4` | Haystack supporting Python packages | Upstream is unchanged. The AUR has four packaging revisions, so the disposition should diff packaging rather than change the source version. |
| [`python-docstring-parser`](../../packages/python-docstring-parser/PKGBUILD) | `0.18.0-1` | [`0.18.0`](https://pypi.org/project/docstring-parser/0.18.0/), 2026-04-14 | [`python-docstring-parser` in AUR](https://aur.archlinux.org/packages/python-docstring-parser), currently `0.18.0-1` | Haystack supporting Python packages | Source and AUR versions match. This is a verify-current disposition unless the Haystack 3 dependency audit changes the package's role. |
| [`python-fastapi-openai-compat`](../../packages/python-fastapi-openai-compat/PKGBUILD) | `1.2.0-1` | [`1.2.0`](https://pypi.org/project/fastapi-openai-compat/1.2.0/), 2026-04-03 | Upstream PyPI metadata and source; [no same-name AUR recipe](https://aur.archlinux.org/packages?O=0&K=python-fastapi-openai-compat) | Haystack and Hayhooks service stack | Source is current. The optional Haystack integration remains relevant to the Hayhooks 1.23/Haystack 3 compatibility test, but no source update is indicated. |
| [`python-faster-whisper`](../../packages/python-faster-whisper/PKGBUILD) | `1.2.1-1` | [`1.2.1`](https://github.com/SYSTRAN/faster-whisper/releases/tag/v1.2.1), 2025-10-31 | [`python-faster-whisper` in AUR](https://aur.archlinux.org/packages/python-faster-whisper), currently `1.2.1-1` | CTranslate2 and Faster Whisper runtime | Faster Whisper itself is current and accepts CTranslate2 `>=4,<5`. Its disposition is therefore coupled to validating CTranslate2 4.8.1, not to changing its own version. |
| [`python-haystack-experimental`](../../packages/python-haystack-experimental/PKGBUILD) | `0.19.0-1` | [`0.19.0.post1`](https://pypi.org/project/haystack-experimental/0.19.0.post1/), 2026-07-28 | Upstream PyPI metadata and source; [no same-name AUR recipe](https://aur.archlinux.org/packages?O=0&K=python-haystack-experimental) | Haystack supporting Python packages | PyPI provides a post-release without separate upstream release notes and with the same declared `haystack-ai` dependency. More importantly, Haystack 3 removes this package from its core dependency set, so later work must determine whether anything maintained here still imports it before updating or retiring it. |
| [`python-lazy-imports`](../../packages/python-lazy-imports/PKGBUILD) | `1.2.0-1` | [`1.2.0`](https://pypi.org/project/lazy-imports/1.2.0/), 2025-12-28 | Upstream PyPI metadata and source; [no same-name AUR recipe](https://aur.archlinux.org/packages?O=0&K=python-lazy-imports) | Haystack supporting Python packages | Source is current and remains a Haystack 3 dependency. No independent migration is indicated. |
| [`python-posthog`](../../packages/python-posthog/PKGBUILD) | `7.16.2-1` | [`7.38.4`](https://github.com/PostHog/posthog-python/releases/tag/posthog-v7.38.4), 2026-08-10 | [`python-posthog` in AUR](https://aur.archlinux.org/packages/python-posthog), currently stale and flagged out of date at `6.7.9-1`; use upstream metadata for the candidate | Haystack supporting Python packages and outbound reporting | The intervening releases add opt-in capture-v1 transport, metrics, MCP analytics, and broader AI observability while also adding default secret detection and URL/DSN credential masking for captured exception variables. Haystack permits this version, but the large outbound-reporting delta requires a privacy-default audit even if applications are expected to keep telemetry disabled. |
| [`python-rapidocr-onnxruntime`](../../packages/python-rapidocr-onnxruntime/PKGBUILD) | `1.4.4-1` | The legacy distribution remains [`1.4.4`](https://pypi.org/project/rapidocr-onnxruntime/1.4.4/), 2025-01-17; its active successor is [`rapidocr` `3.9.2`](https://github.com/RapidAI/RapidOCR/releases/tag/v3.9.2), 2026-07-21 | [`python-rapidocr-onnxruntime` in AUR](https://aur.archlinux.org/packages/python-rapidocr-onnxruntime), currently `1.4.4-1`; upstream RapidOCR is authoritative for migration | Open WebUI and system ML stack | The current RapidOCR instructions install `rapidocr` plus a separately selected engine such as `onnxruntime`. Open WebUI 0.11 now pins `rapidocr==3.9.2`, so retaining the legacy combined distribution would not satisfy the new application metadata without another packaging divergence. Treat this as a successor-package decision. |
| [`python-sentence-transformers`](../../packages/python-sentence-transformers/PKGBUILD) | `5.5.1-1` | [`5.7.0`](https://github.com/huggingface/sentence-transformers/releases/tag/v5.7.0), 2026-08-06 | [`python-sentence-transformers` in AUR](https://aur.archlinux.org/packages/python-sentence-transformers), currently `5.6.1-1` | Open WebUI and system ML stack | `5.7.0` adds `tokenizers` as a direct dependency, fixes multiple evaluator/mining correctness bugs, invalidates old hard-negative caches when prompts differ, and starts trust-checking third-party module imports ahead of a stricter 6.0 default. Open WebUI 0.11 pins `5.5.1`, so the candidate requires an explicit pin-divergence and system-provider decision. |
| [`qdrant`](../../packages/qdrant/PKGBUILD) | `1.18.1-2` | [`1.19.0`](https://github.com/qdrant/qdrant/releases/tag/v1.19.0), 2026-08-05 | [`qdrant` in AUR](https://aur.archlinux.org/packages/qdrant), currently `1.18.3-1`; retain the local service/config assets as deliberate divergence | Qdrant service and stored-state migration | `1.19.0` changes collection memory controls, enables single-file mmap vector storage by default for immutable segments, deprecates old search endpoints and strict-mode memory settings, and fixes a path-traversal vulnerability in S3 snapshot handling. It also reports effective cgroup resources in telemetry; the package's usage-telemetry-disabled default must remain verified. Snapshot and existing-state recovery belong in the acceptance gate. |
| [`thorium-browser-updated`](../../packages/thorium-browser-updated/PKGBUILD) | `149.0.7827.114-4` | [`Alacrium 151.0.7922.108`](https://github.com/brauliobo/alacrium/releases/tag/M151.0.7922.108), 2026-08-07 | [`alacrium-browser` in AUR](https://aur.archlinux.org/packages/alacrium-browser), currently `151.0.7922.71-1`; the recorded `thorium-browser-updated` AUR recipe no longer exists | Chromium browser provenance and expensive source build | `brauliobo/thorium` now redirects to `brauliobo/alacrium`, and the active AUR source recipe changed package identity, source preparation, pinned commits, dependencies, and installed paths. The later ticket must decide whether to migrate identity or preserve compatibility names before attempting the expensive build; old PR build evidence cannot validate the renamed 151 lane. |
| [`utilyze`](../../packages/utilyze/PKGBUILD) | `0.1.1-2` | [`0.1.3`](https://github.com/systalyze/utilyze/releases/tag/v0.1.3), 2026-04-27 | Upstream source and release; [no same-name AUR recipe](https://aur.archlinux.org/packages?O=0&K=utilyze) | NVIDIA runtime acceptance and package-patch reconciliation | Upstream `0.1.2` reorganized the application into a client/server design with long-lived configuration and added utilization modes; `0.1.3` fixes CUPTI/profile-cap prompts before the TUI starts. Those changes overlap the local config, profiling-policy, self-update, and telemetry-consent patches. A target cannot be selected responsibly without reconciling the patch purpose and completing the still-open NVIDIA runtime acceptance boundary. |

## Compatibility Lanes

### Haystack And Hayhooks

Treat `haystack-ai`, `hayhooks`, `python-fastapi-openai-compat`,
`python-haystack-experimental`, `python-lazy-imports`, `python-docstring-parser`,
and `python-posthog` as one decision lane. Hayhooks 1.23 supports both framework
majors, but Haystack 3 changes runtime APIs and the dependency graph. This lane
should decide the framework major first, then determine whether
`haystack-experimental` remains needed, and finally accept the supporting
packages and service behavior together.

### Open WebUI And The System ML Stack

Treat `open-webui`, `python-rapidocr-onnxruntime`,
`python-sentence-transformers`, `python-faster-whisper`, and `ctranslate2` as a
coupled lane. Open WebUI's current Python upper bound conflicts with the host
lane already patched by this repository, and its exact dependency pins conflict
with both the Sentence Transformers candidate and the legacy RapidOCR package
shape. The CTranslate2 security fixes are independently desirable, but their
acceptance still belongs with Faster Whisper runtime validation.

### Stateful, Expensive, And Policy-Managed Packages

Keep separate decisions for Qdrant stored-state compatibility, the
Thorium-to-Alacrium provenance and identity migration, utilyze's hardware-gated
patch reconciliation, and Codex's generated-artifact supply chain. These lanes
have materially different evidence requirements and should not be hidden in a
bulk Python-package update.

## Baseline Gaps

Only six of the seventeen package directories currently record all four fields
required by [`docs/policies/reference-packages.md`](../policies/reference-packages.md):
`authoritative_reference`, `advisory_references`, `divergence_notes`, and
`update_notes`. The refresh should add or repair package-local maintenance
baselines when each disposition is implemented. In particular:

- replace the vanished `thorium-browser-updated` reference with the selected
  Alacrium lane;
- record upstream-as-authoritative baselines where no Arch/AUR recipe exists;
- retain stale same-lane AUR recipes as packaging references without treating
  their versions as release candidates; and
- give the ingested Codex artifact a reproducible source/build identity even
  though this repository intentionally has no second `PKGBUILD` for it.

## Recommended Decision Order

1. Decide package identity and retention questions for Codex, Alacrium,
   utilyze, and the RapidOCR successor before writing update plans for them.
2. Decide whether the Haystack service stack moves to Haystack 3, then settle
   its supporting packages as one tested set.
3. Decide the Open WebUI Python and dependency-pin policy, then settle its
   system ML providers and CTranslate2/Faster Whisper runtime.
4. Decide the Qdrant state-migration and security acceptance gate.
5. Mark unchanged supporting packages verified-current, and schedule packaging
   revision diffs where their AUR baselines have moved.

This order records dependencies between decisions; it does not authorize any
package update, retirement, build, installation, or service mutation.
