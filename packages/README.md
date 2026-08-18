# Package Catalog

Each directory under `packages/` is a self-contained Arch package lane. Normal
lanes carry a `PKGBUILD`, `.SRCINFO`, service assets, patches, and local notes.
The `chatgpt` lane is the explicit exception: it accepts an exact package
artifact and provenance record, so it has no local `PKGBUILD` or `.SRCINFO`.

## Refresh Index

This is the checked human record for the current repository refresh. It was
reconciled on 2026-08-17 against the complete dated upstream sweep and the
subsequent package-lane decisions. The packaged version is mechanical truth
from `.SRCINFO`, except for the immutable `chatgpt` lane, where the tracked
artifact baseline is authoritative. A review date records the latest human
target or disposition review; it is not an assertion that no newer release
exists.

The dispositions have deliberately narrow meanings:

- `accepted-current`: the selected package or artifact passed its lane-specific
  acceptance gate and may enter the terminal publication manifest.
- `deferred`: the named target is still maintained, but the row states its next
  gate and whether any package from that lane may be published in this refresh.
- `retired`: the package is excluded from the final inventory and scheduled for
  preservation-aware source and artifact cleanup.

Publication eligibility refers to the terminal clean refresh manifest, not to
whether an old archive exists or a recipe can be built. Every deferred lane in
this refresh is excluded until a later acceptance record explicitly promotes
it. The empty legacy `packages/codex-app/` directory is not a package lane: it
has no recipe or immutable artifact baseline and therefore has no catalog row.

| Directory | Package | Packaged version | Disposition | Reviewed target or cursor | Review date | Acceptance state or next gate | Publication eligible |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [`chatgpt`](chatgpt/) | `chatgpt` | 26.810.52044-1 | accepted-current | [`fallback-baseline-2026-08-16`](https://github.com/nisavid/chatgpt-linux/tree/fallback-baseline-2026-08-16) at `dd3d1397f544752ea1170af8393cd59379373f52` | 2026-08-17 | Exact ingest, repository publication, fallback installation, and host acceptance passed; retain the fallback only until the separate parity and sunsetting decision releases it. | yes |
| [`ctranslate2`](ctranslate2/) | `ctranslate2`, `python-ctranslate2` | 4.7.2-1 | deferred | [CTranslate2 4.8.1](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Excluded; pass the Open WebUI speech G0-G2 package, payload, offline-runtime, and Faster Whisper checks. | no |
| [`hayhooks`](hayhooks/) | `hayhooks` | 1.19.2-1 | deferred | [Hayhooks 1.23.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass the Haystack 3 package gates, Qdrant-backed G4 service gate, v2-to-v3 migration, and rollback drill. | no |
| [`haystack-ai`](haystack-ai/) | `python-haystack-ai` | 2.29.0-1 | deferred | [Haystack 3.0.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass the Haystack 3 package gates, Qdrant-backed G4 service gate, v2-to-v3 migration, and rollback drill. | no |
| [`open-webui`](open-webui/) | `open-webui` | 0.9.5-1 | deferred | [Open WebUI 0.11.0](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Excluded; pass Python 3.14 and system-ML G0-G2, then household HTTPS, migration, browser, preservation, and whole-runtime rollback G3-G4. | no |
| [`python-backoff`](python-backoff/) | `python-backoff` | 2.2.1-1 | deferred | [backoff 2.2.1; review AUR packaging revision 2.2.1-4](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; accept as part of the complete Haystack 3 dependency closure and composed service gate. | no |
| [`python-docstring-parser`](python-docstring-parser/) | `python-docstring-parser` | 0.18.0-1 | deferred | [docstring-parser 0.18.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; accept as part of the complete Haystack 3 dependency closure and composed service gate. | no |
| [`python-fastapi-openai-compat`](python-fastapi-openai-compat/) | `python-fastapi-openai-compat` | 1.2.0-1 | deferred | [fastapi-openai-compat 1.2.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass the Hayhooks 1.23 and Haystack 3 compatibility and composed service gates. | no |
| [`python-faster-whisper`](python-faster-whisper/) | `python-faster-whisper` | 1.2.1-1 | deferred | [Faster Whisper 1.2.1](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Excluded; pass the Open WebUI speech G0-G2 gate with CTranslate2 4.8.1. | no |
| [`python-haystack-experimental`](python-haystack-experimental/) | `python-haystack-experimental` | 0.19.0-1 | retired | [Retire after final archived 0.19.0.post1](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Retired from the Haystack 3 dependency set; preserve the rollback artifact until migration acceptance releases it, then remove source and artifacts. | no |
| [`python-lazy-imports`](python-lazy-imports/) | `python-lazy-imports` | 1.2.0-1 | deferred | [lazy-imports 1.2.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; accept as part of the complete Haystack 3 dependency closure and composed service gate. | no |
| [`python-posthog`](python-posthog/) | `python-posthog` | 7.16.2-1 | deferred | [PostHog 7.38.4](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass dependency, no-network, and telemetry-disabled privacy acceptance with the Haystack 3 lane. | no |
| [`python-rapidocr-onnxruntime`](python-rapidocr-onnxruntime/) | `python-rapidocr-onnxruntime` | 1.4.4-1 | retired | [Retire legacy 1.4.4; replace with RapidOCR 3.9.2](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Retired; the source-built `python-rapidocr` successor must pass the Open WebUI core gate before preservation-aware cleanup. | no |
| [`python-sentence-transformers`](python-sentence-transformers/) | `python-sentence-transformers` | 5.5.1-1 | deferred | [Sentence Transformers 5.5.1 for the first accepted Open WebUI set](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Excluded; pass the exact Python 3.14 and system-ML provider-set checks and the composed Open WebUI gate. | no |
| [`qdrant`](qdrant/) | `qdrant` | 1.19.0-1 | deferred | [Qdrant 1.19.0 via 1.18.3, with Qdrant Web UI 0.2.16](https://github.com/nisavid/arch-pkgs/issues/28#issuecomment-5259788912) | 2026-08-11 | Excluded; pass empty-state and 1.17.1-to-1.18.3-to-1.19.0 G0-G3 migration and recovery, then the coupled Haystack G4 gate. | no |
| [`qdrant-migration`](qdrant-migration/) | `qdrant-migration` | 1.18.3-1 | deferred | [Retained Qdrant 1.18.3 consecutive-minor migration artifact](https://github.com/nisavid/arch-pkgs/issues/28#issuecomment-5259788912) | 2026-08-11 | Excluded; pass Qdrant G0-G3 provenance, isolated payload, consecutive-minor migration, recovery, and rollback gates. | no |
| [`qdrant-web-ui`](qdrant-web-ui/) | `qdrant-web-ui` | 0.2.16-1 | deferred | [Qdrant Web UI 0.2.16 in the Qdrant 1.19.0 service contract](https://github.com/nisavid/arch-pkgs/issues/28#issuecomment-5259788912) | 2026-08-11 | Excluded; pass Qdrant G0-G3 provenance, package, loopback-runtime, CSP, no-egress, migration, and recovery gates. | no |
| [`thorium-browser-updated`](thorium-browser-updated/) | `thorium-browser-updated` | 149.0.7827.114-4 | deferred | [Source-built Alacrium M151.0.7922.108 successor cursor](https://github.com/nisavid/arch-pkgs/issues/29#issuecomment-5261359711) | 2026-08-12 | Excluded; freeze the newest eligible Alacrium release and pass immutable offline two-build reproducibility plus desktop and security G0-G4 before retiring Thorium. | no |
| [`utilyze`](utilyze/) | `utilyze` | 0.1.1-2 | deferred | [utilyze v0.1.3 at `a9e211813f6717b63ad826e1eb4097cdaea1dd43`](https://github.com/nisavid/arch-pkgs/issues/25#issuecomment-5257258123) | 2026-08-11 | Excluded; pass local package and fail-closed privacy gates, then separately authorize and pass the paid Ampere-or-newer NVIDIA G4 run. | no |

The three Qdrant rows share the disposable G0-G3 fixture and evidence contract in
[`docs/maintainers/qdrant-migration-acceptance.md`](../docs/maintainers/qdrant-migration-acceptance.md).
Building any recipe does not change its deferred disposition.

Run the local structural check after editing the catalog or any retained
package baseline:

```bash
python3 tools/check_repo_consistency.py
```

The checker verifies catalog coverage, row shape, package identity and version,
required baseline-field shape, `.SRCINFO` agreement, tracked Zsh syntax, pinned
workflow actions, and the committed unit tests. It does not query providers,
select candidates, build packages, or decide whether lane-specific acceptance
evidence is sufficient; those remain explicit maintainer review.

## Build And Publish

For a repository-wide or multi-lane refresh, follow the
[`package refresh lifecycle`](../docs/policies/package-refresh-lifecycle.md) and
use `orchestrating-arch-package-refreshes` before building or publishing. A
successful build does not change a lane's disposition. Terminal staging must
match the explicit manifest of accepted, publication-eligible identities.

The build and staging commands below are development-candidate operations
only. They may create or stage new bytes, so they are neither acceptance nor
lifecycle publication steps. After promotion, follow the
[`accepted-only publication`](../docs/policies/package-refresh-lifecycle.md#accepted-only-publication)
and [`publisher`](../docs/usage/local-repo.md#publish-a-pacman-visible-copy)
procedures with the exact accepted artifacts and without rebuilding them.

This workflow applies to ordinary package lanes with a `PKGBUILD`; it does not
apply to [`chatgpt`](chatgpt/). Stage that immutable artifact lane only with
[`tools/ingest_chatgpt.zsh`](../tools/ingest_chatgpt.zsh), following its
package-local README and accepted baseline.

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
