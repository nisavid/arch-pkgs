# Lemonade provider port status — 2026-08-19

## Verdict

**Not ready for a new accepted Open WebUI household-envelope run.** The
ZeroEntropy reranking adapter has reached the current Lemonade fork, and an
older coherent package family was built and live-smoked. The updated fork has
not been propagated into a current, immutable five-package Lemonade/llama.cpp
family, however. The measurement must stay blocked until that package family
exists and its exact archives are bound into the measurement subject.

The practical distinction is:

- **Source port: landed.** The live fork `main` is
  [`0c93411bc9b0463eee0f56d38cd97fffb0bae633`](https://github.com/nisavid/lemonade/commit/0c93411bc9b0463eee0f56d38cd97fffb0bae633),
  reports Lemonade 11.6.0, and contains the selected-logit ZeroEntropy adapter.
- **Historical package family: coherent but stale.** The current packaging
  repository still describes Lemonade 10.7.0 plus llama.cpp b9442. That tuple
  has historical build, deployment, zembed, and zerank evidence, but it is not
  the reviewed current-fork package generation and its package archives are not
  retained in Git with accepted digests.
- **Current package family: absent.** No package update or build binds live
  Lemonade 11.6.0 to a current common llama.cpp source and refreshed patch set.

## Lemonade fork state

The adapter first landed through
[`nisavid/lemonade` PR #17](https://github.com/nisavid/lemonade/pull/17) at
merge commit
[`6764b0bdca8172c5c3af52d255f8008fceffae32`](https://github.com/nisavid/lemonade/commit/6764b0bdca8172c5c3af52d255f8008fceffae32).
The related UI restriction landed through
[PR #20](https://github.com/nisavid/lemonade/pull/20), and the last source
revision consumed by the Arch packages was the v10.7.0 sync
[`e18b9c1e352df8ab5aff2ff353402f1ec77c47f2`](https://github.com/nisavid/lemonade/commit/e18b9c1e352df8ab5aff2ff353402f1ec77c47f2)
from [PR #24](https://github.com/nisavid/lemonade/pull/24).

The fork did not reach its current line by completing the still-open
[v10.8.0 sync PR #25](https://github.com/nisavid/lemonade/pull/25). That PR
remains at `e2b873facea3a9d5c3bb8a6039839bd19841918b`; the live branches are
372 commits on the `main` side and two commits on the PR side. Instead,
[`0e5b4ad66cc38805a47a65a2bdc8a557d9cbaefb`](https://github.com/nisavid/lemonade/commit/0e5b4ad66cc38805a47a65a2bdc8a557d9cbaefb)
merged the v11.6.0 stable line into the fork and explicitly preserved the
ZeroEntropy adapter and the fork's other retained behavior.

The current implementation is present at
[`src/cpp/server/backends/llamacpp_reranking_adapter.cpp`](https://github.com/nisavid/lemonade/blob/0c93411bc9b0463eee0f56d38cd97fffb0bae633/src/cpp/server/backends/llamacpp_reranking_adapter.cpp).
The current catalog binds `zerank-2-GGUF` to the
`zeroentropy-logit-score` adapter, selected token ID `9454`, and scale `5.0`
in
[`src/cpp/resources/server_models.json`](https://github.com/nisavid/lemonade/blob/0c93411bc9b0463eee0f56d38cd97fffb0bae633/src/cpp/resources/server_models.json).
The opt-in live scenario remains in
[`test/server_llm.py`](https://github.com/nisavid/lemonade/blob/0c93411bc9b0463eee0f56d38cd97fffb0bae633/test/server_llm.py).
The adapter source itself is unchanged between the packaged v10.7.0 revision
and current `main`.

This establishes that the adapter survived the upstream port. It does not
establish an accepted current release: the full durable-pin, startup,
admission, reclamation, and refusal contract is still gated by
[`arch-strix-halo-pkgs` #112](https://github.com/nisavid/arch-strix-halo-pkgs/issues/112),
whose terminal evidence remains open.

## Current Arch package chain

The live `arch-strix-halo-pkgs` default branch is
[`a3f88a145bb9b69043cd4f99ef3673caf23b5869`](https://github.com/nisavid/arch-strix-halo-pkgs/commit/a3f88a145bb9b69043cd4f99ef3673caf23b5869).
Its last package implementation is the family admitted by
[PR #73](https://github.com/nisavid/arch-strix-halo-pkgs/pull/73), combined
with the shared selected-logit llama.cpp patch introduced through
[PR #32](https://github.com/nisavid/arch-strix-halo-pkgs/pull/32).

| Package | Packaged version | Bound source |
| --- | --- | --- |
| `lemonade-server` | `10.7.0-1` | fork commit `e18b9c1e352df8ab5aff2ff353402f1ec77c47f2` plus four server patches |
| `lemonade-app` | `10.7.0-1` | the same fork commit plus the Tauri GLib patch |
| `lemonade` | `10.7.0-1` | meta package requiring the server, app, HIP backend, and Vulkan backend |
| `llama.cpp-hip-gfx1151` | `b9442-1` | upstream commit `d4c8e2c29ce2fb9a251a0a4a16d6c857b4f70f8c` plus the shared selected-logit patch |
| `llama.cpp-vulkan-gfx1151` | `b9442-1` | the same upstream commit and patch |

The exact package recipes are
[`packages/lemonade-server/PKGBUILD`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/packages/lemonade-server/PKGBUILD),
[`packages/lemonade-app/PKGBUILD`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/packages/lemonade-app/PKGBUILD),
[`packages/lemonade/PKGBUILD`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/packages/lemonade/PKGBUILD),
[`packages/llama.cpp-hip-gfx1151/PKGBUILD`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/packages/llama.cpp-hip-gfx1151/PKGBUILD),
and
[`packages/llama.cpp-vulkan-gfx1151/PKGBUILD`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/packages/llama.cpp-vulkan-gfx1151/PKGBUILD).
Their SHA-256 identities at `a3f88a1` are, in the same order:

- `cc0b540fb303e82d025223f5328480db984d0cc048f1bfbb06ca92a65d500b59`
- `f32c830b82d51c9729b883fc91bfb3c70b6ce6e65fbe0a69628f964d6f95efa4`
- `444ec512939b0f6a1ad6ae903982cb175643130ef73ebc6b4a2b6b1e400a8eab`
- `47b69198f82313ed135e07cb12fca6a4421dd64e65a92a2b2e0a9002d6082f41`
- `07da138cf7122555fb030868640ea70c0fe311ef60138a64763104a27fba7c9a`

The shared
[`0001-server-return-selected-token-logits.patch`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/patches/llama.cpp-common/0001-server-return-selected-token-logits.patch)
has SHA-256
`8d9cad515f96f67764416177a557c3c69187d2c3209d474e27abc343f8c49e3b`.
The four server patch hashes, in PKGBUILD order, are
`84149e7e765b80de94b0058edf930ee61ca39ceee534bff4e01fdd7e050cfb27`,
`28bdecea3931d13a756ec79b7ff0d8976f6643f61daf80988c8a0283a41d8933`,
`567757053609fce709a8392d91eab3596b8fe1915f2ffce3d064bd4c0e17da46`,
and
`80e5d6f182f8050643737ed8e726a2e63bc6d279f717a40514ce9f016ff32c82`.
The app patch hash is
`a1206e0fedcdaa87a725719cade8a499aaaa401bce0c9a5442bc57f95e0be177`.

The repository records that this historical tuple was built, published,
installed, and passed both the zembed embedding scenario and zerank
selected-logit scenario; see
[`docs/maintainers/current-state.md`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/docs/maintainers/current-state.md)
and
[`inference/scenarios/lemonade-pooling.toml`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/a3f88a145bb9b69043cd4f99ef3673caf23b5869/inference/scenarios/lemonade-pooling.toml).
The raw run directories and package archives cited by that historical note are
not retained in Git. The recipes also use `SKIP` for their source checksums.
Therefore the repository proves that a coherent provider worked, but does not
currently supply the digest-bound package archives required as the new
measurement subject.

## Exact model assets retained by the measurement contract

The household-envelope contract already binds the provider's data artifacts
in
[`tools/measure_open_webui_household.py`](https://github.com/nisavid/arch-pkgs/blob/59566131f576bfec29783e4b8f909bd1ef907769/tools/measure_open_webui_household.py):

| Role | Repository and revision | File | Size | SHA-256 |
| --- | --- | --- | ---: | --- |
| embedding | `Abiray/zembed-1-Q4_K_M-GGUF` at `c1fed1b47f407fdf5ceb25d6919ac7e5237151c9` | `zembed-1-Q4_K_M.gguf` | `2497280960` | `3098f7963ca0563e8b39a55ee09a53697e57e49be5b9082892739bf24e075836` |
| reranking | `mradermacher/zerank-2-GGUF` at `c3c0d69a75b8dad9f56e99aec416d6aff12b85c7` | `zerank-2.Q8_0.gguf` | `4280405664` | `7b9ba05a0509151c911582a4d62b14003f6a4fafa0e7ccdf572c7598cde1c100` |

Those model identities can remain stable while the provider package family is
rebuilt. The new run must additionally bind the resulting Lemonade and
llama.cpp package archives, not merely the model files and installed binary
paths.

## Why the updated family is not build-ready

The package repository's accepted convergence policy requires all five
packages to come from one reviewed Lemonade line and one common llama.cpp
revision; see the resolution in
[`arch-strix-halo-pkgs` #93](https://github.com/nisavid/arch-strix-halo-pkgs/issues/93).
The current execution graph leaves the source freeze, fork behavior, and
package build open in
[#105](https://github.com/nisavid/arch-strix-halo-pkgs/issues/105),
[#112](https://github.com/nisavid/arch-strix-halo-pkgs/issues/112), and
[#113](https://github.com/nisavid/arch-strix-halo-pkgs/issues/113).

The current candidate ledger still names Lemonade 11.5.2 and llama.cpp b10369,
while the refreshed fork is already Lemonade 11.6.0 and its bundled backend
metadata names b10375 for Vulkan and b10397 for stable ROCm. This is precisely
the unsettled source-selection decision owned by #105; those values must not
be silently mixed.

Fresh dry-run composition checks also show real porting work:

- Against fork `0c93411`, server patch 1 applies with offsets, but server
  patches 2, 3, and 4 have failed hunks. The app patch still applies cleanly.
- Against llama.cpp b10369 commit
  [`6e62ba538478202094edc6c100c782719e310aa3`](https://github.com/ggml-org/llama.cpp/commit/6e62ba538478202094edc6c100c782719e310aa3),
  the selected-logit patch has four failed hunks across
  `tools/server/server-context.cpp` and `tools/server/server-task.cpp`.

The old patch carry therefore cannot be pointed at the new refs and rebuilt as
is. Some server-patch behavior now overlaps newer upstream system-backend
support, so #113 should rederive the desired package behavior against the
current architecture instead of mechanically replaying every old hunk.

## Smallest path to readiness

1. Complete #105 by selecting one reviewed live-fork commit and one common
   llama.cpp commit for both HIP and Vulkan. Refresh the stale candidate names
   at the same time.
2. Complete the source behavior required by #112 and admit its focused fork
   evidence to that frozen revision.
3. Under #113, refresh the server/app package integration, port the
   selected-logit extension to the chosen llama.cpp revision, regenerate all
   five recipes, replace checksum skips with immutable inputs, and build the
   family as one release unit.
4. Inspect and hash every package archive, then prove the zembed and zerank
   scenarios against the exact model assets above with no downloader fallback.
5. Add those Lemonade and llama.cpp archive identities to #68's executable
   subject. Only then repeat the integrated start, restore, and rollback runs.

The immediate formal blocker is #105's source freeze. The immediate mechanical
blockers after that decision are the server package carry and selected-logit
patch ports. No live service, protected state, package repository, or model
cache was inspected or changed for this scout.
