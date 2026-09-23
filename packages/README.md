# Package Catalog

Each directory under `packages/` is a self-contained Arch package lane with a
`PKGBUILD`, `.SRCINFO`, service assets, patches, and local notes as needed.

## Refresh Index

This is the checked human record for the current repository refresh. It was
reconciled on 2026-09-22, retiring Thorium and rebinding deferred gates to the tracker, against the complete dated upstream sweep and the
subsequent package-lane decisions. The packaged version is mechanical truth
from `.SRCINFO`. A review date records the latest human target or disposition
review; it is not an assertion that no newer release exists.

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
it. The retired ChatGPT fallback is not a package lane or catalog row; its
public historical evidence is documented in
[`docs/maintainers/chatgpt-retirement.md`](../docs/maintainers/chatgpt-retirement.md).

| Directory | Package | Packaged version | Disposition | Reviewed target or cursor | Review date | Acceptance state or next gate | Publication eligible |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [`ctranslate2`](ctranslate2/) | `ctranslate2`, `python-ctranslate2` | 4.7.2-1 | deferred | [CTranslate2 4.8.1](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Excluded; pass the Open WebUI speech G0-G2 package, payload, offline-runtime, and Faster Whisper checks. | no |
| [`hayhooks`](hayhooks/) | `hayhooks` | 1.19.2-1 | deferred | [Hayhooks 1.23.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass the Haystack 3 package gates, Qdrant-backed G4 service gate, v2-to-v3 migration, and rollback drill. Stays deferred until [Adopt a concrete reusable Haystack/Hayhooks workflow](https://github.com/nisavid/arch-pkgs/issues/71) activates. | no |
| [`haystack-ai`](haystack-ai/) | `python-haystack-ai` | 2.29.0-1 | deferred | [Haystack 3.0.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass the Haystack 3 package gates, Qdrant-backed G4 service gate, v2-to-v3 migration, and rollback drill. Stays deferred until [Adopt a concrete reusable Haystack/Hayhooks workflow](https://github.com/nisavid/arch-pkgs/issues/71) activates. | no |
| [`open-webui`](open-webui/) | `open-webui` | 0.11.0-5 | deferred | [Fresh Open WebUI 0.11.0 native-RAG envelope](https://github.com/nisavid/arch-pkgs/issues/68) | 2026-09-22 | Excluded; the 0.11.0-3 [offline closure, no-egress build, and payload gate](../docs/maintainers/open-webui-offline-package-build-2026-08-19.md) passed. Next gate: the one integrated trial set (one restore, one rollback) against the live-validated Lemonade provider under [Acceptance-deploy the Open WebUI household candidate set](https://github.com/nisavid/arch-pkgs/issues/89), then [Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90). | no |
| [`python-backoff`](python-backoff/) | `python-backoff` | 2.2.1-1 | deferred | [backoff 2.2.1; review AUR packaging revision 2.2.1-4](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; accept as part of the complete Haystack 3 dependency closure and composed service gate. Stays deferred until [Adopt a concrete reusable Haystack/Hayhooks workflow](https://github.com/nisavid/arch-pkgs/issues/71) activates. | no |
| [`python-docstring-parser`](python-docstring-parser/) | `python-docstring-parser` | 0.18.0-1 | deferred | [docstring-parser 0.18.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; accept as part of the complete Haystack 3 dependency closure and composed service gate. Stays deferred until [Adopt a concrete reusable Haystack/Hayhooks workflow](https://github.com/nisavid/arch-pkgs/issues/71) activates. | no |
| [`python-fastapi-openai-compat`](python-fastapi-openai-compat/) | `python-fastapi-openai-compat` | 1.2.0-1 | deferred | [fastapi-openai-compat 1.2.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass the Hayhooks 1.23 and Haystack 3 compatibility and composed service gates. Stays deferred until [Adopt a concrete reusable Haystack/Hayhooks workflow](https://github.com/nisavid/arch-pkgs/issues/71) activates. | no |
| [`python-faster-whisper`](python-faster-whisper/) | `python-faster-whisper` | 1.2.1-1 | deferred | [Faster Whisper 1.2.1](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Excluded; pass the Open WebUI speech G0-G2 gate with CTranslate2 4.8.1. | no |
| [`python-haystack-experimental`](python-haystack-experimental/) | `python-haystack-experimental` | 0.19.0-1 | retired | [Retire after final archived 0.19.0.post1](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Retired from the Haystack 3 dependency set; preserve the rollback artifact until migration acceptance releases it, then remove source and artifacts. | no |
| [`python-lazy-imports`](python-lazy-imports/) | `python-lazy-imports` | 1.2.0-1 | deferred | [lazy-imports 1.2.0](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; accept as part of the complete Haystack 3 dependency closure and composed service gate. Stays deferred until [Adopt a concrete reusable Haystack/Hayhooks workflow](https://github.com/nisavid/arch-pkgs/issues/71) activates. | no |
| [`python-posthog`](python-posthog/) | `python-posthog` | 7.16.2-1 | deferred | [PostHog 7.38.4](https://github.com/nisavid/arch-pkgs/issues/27#issuecomment-5259162959) | 2026-08-11 | Excluded; pass dependency, no-network, and telemetry-disabled privacy acceptance with the Haystack 3 lane. Stays deferred until [Adopt a concrete reusable Haystack/Hayhooks workflow](https://github.com/nisavid/arch-pkgs/issues/71) activates. | no |
| [`python-rapidocr`](python-rapidocr/) | `python-rapidocr` | 3.9.2-1 | deferred | [RapidOCR 3.9.2 successor for the Open WebUI 0.11.0 candidate](https://github.com/nisavid/arch-pkgs/issues/68) | 2026-08-19 | Excluded; the Open WebUI provider-boundary verifier passed against the staged RapidOCR metadata fixture. Complete the accepted integrated provider and runtime gate before promotion. | no |
| [`python-rapidocr-onnxruntime`](python-rapidocr-onnxruntime/) | `python-rapidocr-onnxruntime` | 1.4.4-1 | retired | [Retire legacy 1.4.4; replace with RapidOCR 3.9.2](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-08-11 | Retired; the source-built `python-rapidocr` successor must pass the Open WebUI core gate before preservation-aware cleanup. | no |
| [`python-sentence-transformers`](python-sentence-transformers/) | `python-sentence-transformers` | 5.5.1-1 | deferred | [Sentence Transformers 5.5.1 for the first accepted Open WebUI set](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835) | 2026-09-22 | Excluded; pass the exact Python 3.14 and system-ML provider-set checks and the composed Open WebUI gate. Next gate: [Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90). | no |
| [`qdrant`](qdrant/) | `qdrant` | 1.19.0-1 | deferred | [Qdrant 1.19.0 via 1.18.3, with Qdrant Web UI 0.2.16](https://github.com/nisavid/arch-pkgs/issues/28#issuecomment-5259788912) | 2026-09-22 | Excluded; G0-G3 accepted. Next gate: promotion together with Open WebUI under [Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90); deploy via [Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58). | no |
| [`qdrant-migration`](qdrant-migration/) | `qdrant-migration` | 1.18.3-1 | deferred | [Retained Qdrant 1.18.3 consecutive-minor migration artifact](https://github.com/nisavid/arch-pkgs/issues/28#issuecomment-5259788912) | 2026-09-22 | Excluded; G0-G3 accepted. Next gate: promotion together with Open WebUI under [Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90); deploy via [Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58). | no |
| [`qdrant-web-ui`](qdrant-web-ui/) | `qdrant-web-ui` | 0.2.16-1 | deferred | [Qdrant Web UI 0.2.16 in the Qdrant 1.19.0 service contract](https://github.com/nisavid/arch-pkgs/issues/28#issuecomment-5259788912) | 2026-09-22 | Excluded; G0-G3 accepted. Next gate: promotion together with Open WebUI under [Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90); deploy via [Deploy the accepted Qdrant service](https://github.com/nisavid/arch-pkgs/issues/58). | no |
| [`thorium-browser-updated`](thorium-browser-updated/) | `thorium-browser-updated` | 149.0.7827.114-4 | retired | Thorium and the planned Alacrium successor are retired from arch-pkgs; the AUR provides source and binary Alacrium packages (`alacrium-browser`, `alacrium-browser-bin`) | 2026-09-22 | Excluded; preservation-aware source and artifact cleanup under [Release retained rollback anchors and clean target-local state](https://github.com/nisavid/arch-pkgs/issues/62). | no |
| [`utilyze`](utilyze/) | `utilyze` | 0.1.1-2 | deferred | [utilyze v0.1.3 at `a9e211813f6717b63ad826e1eb4097cdaea1dd43`](https://github.com/nisavid/arch-pkgs/issues/25#issuecomment-5257258123) | 2026-09-22 | Excluded until [Resume the utilyze lane when NVIDIA validation is available](https://github.com/nisavid/arch-pkgs/issues/84) activates; utilyze is NVIDIA-only and cannot be deployed and runtime-validated on the host. | no |

The three Qdrant rows share the disposable G0-G3 fixture and evidence contract in
[`docs/maintainers/qdrant-migration-acceptance.md`](../docs/maintainers/qdrant-migration-acceptance.md).
Building any recipe does not change its deferred disposition.
The Qdrant rows no longer wait on the coupled Haystack G4 gate; this supersedes the runbook's closing G4 clause, whose bytes stay frozen in the G0-G3 evidence.

Run the local structural check after editing the catalog or any retained
package baseline:

```bash
python3 tools/check_repo_consistency.py
```

The checker verifies catalog coverage, row shape, package identity and version,
required baseline-field shape, `.SRCINFO` agreement, retired ChatGPT source
boundaries, checkout Zsh syntax, pinned workflow actions, and the unit tests
discovered in the checkout. It does not query providers, select candidates,
build packages, or decide whether lane-specific acceptance evidence is
sufficient; those remain explicit maintainer review.

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
