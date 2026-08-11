# Unfinished Pull Request, Branch, And Worktree Inventory

## Scope And Provenance

This inventory was captured on 2026-08-11 against repository `main` at
[`ca744c7`](https://github.com/nisavid/arch-pkgs/commit/ca744c74ea8bca30c6ac3166b7e1006821c51dba).
It uses live GitHub pull-request, review, branch, and ref data; the local Git
commit graph and worktree registry; and current first-party release registries.
Local commands included `git worktree list --porcelain`, `git branch -vv --all`,
`git rev-list`, `git cherry`, and per-worktree `git status --porcelain=v2`.

This note identifies evidence and preservation constraints. It does not decide
whether to merge, supersede, close, retain, or delete any pull request, branch,
artifact, or worktree.

## Executive Finding

The only unfinished GitHub pull requests are
[`Refresh package inventory and auto-adopt eligible updates`](https://github.com/nisavid/arch-pkgs/pull/15)
and
[`Update Thorium browser to 149.0.7827.155`](https://github.com/nisavid/arch-pkgs/pull/16).
Both still branch directly from the current `main`: the inventory branch has
three target-only commits and the Thorium branch has one. Their source changes,
reviews, and recorded validation remain recoverable from GitHub.

Neither pull request is a current package target. Every adopted or attempted
version in the inventory pull request now has a newer upstream candidate, and
the Thorium source/AUR lane has become Alacrium. The old work remains useful as
package-specific implementation history, acceptance-gate examples, and, for
Thorium, a locally retained build artifact. It does not replace a fresh target
decision or current validation.

## Open Pull Requests

### Package inventory refresh

The
[`package inventory refresh`](https://github.com/nisavid/arch-pkgs/pull/15)
is open, mergeable at the Git graph level, and blocked by a changes-requested
review. Its three commits change 28 paths:

- six package updates: CTranslate2 `4.8.0`, Hayhooks `1.20.0`, Haystack AI
  `2.30.1`, Open WebUI `0.9.6`, PostHog `7.19.2`, and Sentence Transformers
  `5.6.0`;
- removal of the entire utilyze package and its NVIDIA validation note;
- a package-workflow glossary and an agentic-upgrades policy draft; and
- catalog/backlog updates. Qdrant `1.18.2` appears only as a failed/deferred
  attempt in the pull-request record; no Qdrant recipe change is present.

The current pull-request body records source verification, builds, archive
inspection, and import/CLI smokes for the six adopted updates. No package
artifacts remain in a registered local worktree: the old worktree directory is
gone, and only a prunable Git registration remains. The remote branch and the
pull request therefore preserve source and review evidence, not build outputs.

Three review threads remain unresolved:

- [Deleting the utilyze validation note leaves a test reading the deleted
  path](https://github.com/nisavid/arch-pkgs/pull/15#discussion_r3433172018).
  The branch still contains that test reference while the note is absent, so
  this is a current defect in the branch.
- [The declared Open WebUI Node toolchain was not shown to be the toolchain used
  by the reviewed build](https://github.com/nisavid/arch-pkgs/pull/15#discussion_r3433198261).
  The current pull-request body says a later dependency-checked `makepkg -f`
  passed, but the thread was never resolved; a fresh clean build is the least
  ambiguous acceptance evidence.
- [A review claimed `nodejs-lts-krypton` was
  unavailable](https://github.com/nisavid/arch-pkgs/pull/15#discussion_r3433198394).
  That availability claim is no longer current: the official Arch package
  index now lists
  [`nodejs-lts-krypton`](https://archlinux.org/packages/extra/x86_64/nodejs-lts-krypton/).
  The unresolved historical thread still reinforces the need to bind a clean
  build to its declared dependencies.

Reusable evidence is granular rather than branch-wide: the CTranslate2 CCCL
submodule rewrite, the acceptance commands recorded per package, and the policy
draft can inform later package and safeguard decisions. The version pins,
checksums, catalog dates, utilyze disposition, and Open WebUI dependency choice
must be re-derived. Merging the branch as a single refresh would also couple
package updates, policy adoption, and package retirement that now belong to
separate decisions.

### Thorium refresh

The
[`Thorium refresh`](https://github.com/nisavid/arch-pkgs/pull/16)
is open, approved, mergeable, and has no review threads. Its one commit changes
the Thorium recipe, `.SRCINFO`, package note, and catalog row. All reported
GitHub checks succeeded. The pull-request body records a source build, package
inspection, version smoke, and bounded headless smoke, plus workarounds for an
unavailable V8 PGO profile and sandbox-hostile RPM paths.

The attached local worktree has no tracked modifications, but it is not clean:
it contains untracked `depot_tools/` and `thorium/` trees and ignored source,
build, and package outputs. Recoverable local evidence includes:

- a 5,748,648,616-byte Chromium source tarball;
- `pkg/` and `src/` build trees;
- a `185,632,455`-byte
  `thorium-browser-updated-149.0.7827.155-4-x86_64.pkg.tar.zst`; and
- package metadata reporting `thorium-browser-updated 149.0.7827.155-4`,
  `x86_64`, generated by `makepkg 7.1.0`. The package SHA-256 is
  `21e14c8987fcc9850902d7e9e1ce12ae1c79161bb8cafb4e0e858eab1a394802`.

Those artifacts substantiate the historical build and could reduce the cost of
inspecting it. They do not validate the current browser lane. GitHub now
redirects the former `brauliobo/thorium` repository to
[`brauliobo/alacrium`](https://github.com/brauliobo/alacrium), whose current
release is
[`M151.0.7922.108`](https://github.com/brauliobo/alacrium/releases/tag/M151.0.7922.108).
The AUR returns
[`alacrium-browser`](https://aur.archlinux.org/packages/alacrium-browser) and no
`thorium-browser-updated` result. Package identity, compatibility names,
provenance, and installation layout must therefore be decided before treating
the old recipe as a revival candidate.

## Upstream Supersession Snapshot

| June work item | June target or record | Current first-party candidate on 2026-08-11 | Consequence for reuse |
| --- | --- | --- | --- |
| CTranslate2 | `4.8.0` | [`4.8.1`](https://github.com/OpenNMT/CTranslate2/releases/tag/v4.8.1) | Preserve the CCCL source rewrite concept, but refresh the release, checksum, security review, and runtime evidence. |
| Hayhooks | `1.20.0` | [`1.23.0`](https://github.com/deepset-ai/hayhooks/releases/tag/v1.23.0) | Re-evaluate with the chosen Haystack major. |
| Haystack AI | `2.30.1` | [`3.0.0`](https://github.com/deepset-ai/haystack/releases/tag/v3.0.0) | The later major migration supersedes a routine bump. |
| Open WebUI | `0.9.6` | [`0.11.0`](https://github.com/open-webui/open-webui/releases/tag/v0.11.0) | Rebase local Python/system-ML patches and dependency policy from the current source. |
| PostHog | `7.19.2` | [`7.38.4`](https://pypi.org/project/posthog/7.38.4/) | Repeat the outbound-reporting and privacy-default audit. |
| Sentence Transformers | `5.6.0` | [`5.7.0`](https://github.com/huggingface/sentence-transformers/releases/tag/v5.7.0) | Reconcile the current Open WebUI pin before selecting a package version. |
| Qdrant | `1.18.2` attempted, no committed recipe | [`1.19.0`](https://github.com/qdrant/qdrant/releases/tag/v1.19.0) | The stopped June build is only historical evidence; use a fresh state-migration and security gate. |
| Thorium | `149.0.7827.155` | [`Alacrium 151.0.7922.108`](https://github.com/brauliobo/alacrium/releases/tag/M151.0.7922.108) | Decide identity and compatibility before adapting code or rerunning the expensive build. |
| utilyze tracking branch | Repository baseline `0.1.1-2`; no adoption commit | [`0.1.3`](https://github.com/systalyze/utilyze/releases/tag/v0.1.3) | The branch preserves only the current `main` baseline; patch reconciliation and NVIDIA acceptance remain outstanding. |

## Branch And Ref Inventory

### Live GitHub refs relevant to unfinished work

| Ref | Commit | Evidence and preservation value |
| --- | --- | --- |
| `main` | [`ca744c7`](https://github.com/nisavid/arch-pkgs/commit/ca744c74ea8bca30c6ac3166b7e1006821c51dba) | Protected authoritative repository baseline. |
| `nisavid/refresh-package-inventory` | [`85e34c6`](https://github.com/nisavid/arch-pkgs/commit/85e34c62a9abdcfae34f0552893567e2708a780b) | Exact source for the open inventory pull request; three commits ahead of `main`. |
| `nisavid/thorium-browser-updated-149.0.7827.155` | [`bd62133`](https://github.com/nisavid/arch-pkgs/commit/bd621337df5b0d9c3a97c81c71a2c2d2ad7a73b8) | Exact source for the open Thorium pull request; one commit ahead of `main`. |
| `nisavid/utilyze-adoption` | [`ca744c7`](https://github.com/nisavid/arch-pkgs/commit/ca744c74ea8bca30c6ac3166b7e1006821c51dba) | Identical to `main`; it contains no unique adoption or preservation commit. |

The current Wayfinder research branches are task-owned evidence branches and
are not June cleanup targets.

### Older local leftovers that affect cleanup

| Local ref | Graph result | Classification |
| --- | --- | --- |
| `codex/open-webui-ml-stack-unbundle` | One non-ancestor commit, but `git cherry main` marks it patch-equivalent to `main`; its package versions are older than the present baseline. | Duplicate/superseded work. No registered worktree or live remote ref was found. |
| `codex/refresh-update-publish-2026-05-14` | One local-only commit not patch-equivalent to `main`; its PostHog and Qdrant versions are older than `main`, and all upstream candidates are newer. | Obsolete content but still a unique local commit. Preserve, publish/archive, or intentionally discard it before deleting the branch. |
| `codex/refresh-upstream-updates-2026-05-01` | Fully behind and merged into `main`; zero target-only commits. | Redundant local pointer. |
| `origin/nisavid/ingest-thorium-browser-updated` | Stale local remote-tracking ref; the live GitHub head no longer exists. Every commit is patch-equivalent to `main` after the merged Thorium ingest. | Safe evidence is already in `main` and the merged pull request; reconcile the stale tracking ref only during deliberate cleanup. |

## Worktree Inventory And Risks

The local registry contained the following non-research states at capture time:

| Worktree class | State | Risk and constraint |
| --- | --- | --- |
| Primary checkout | Clean `main` at `ca744c7`, tracking the same remote commit. | Authoritative local baseline; preserve. |
| Current Wayfinder checkout | Clean detached checkout at `ca744c7`. | Active harness-owned worktree; preserve and let the harness own its lifecycle. |
| Two older Codex worktrees | Clean detached checkouts at `0dd4643`, an ancestor of `main`, with no unique commits. | Content is redundant, but cleanup must use the harness-native mechanism after confirming the tasks are inactive. |
| Inventory pull-request registration | Registered to `85e34c6`, but its directory no longer exists and Git marks the registration prunable. | No local artifacts are recoverable from that directory. Later cleanup should target only this exact stale registration; do not use a global prune as a substitute for classification. |
| Thorium pull-request worktree | Branch-attached at `bd62133`; tracked tree clean, with substantial untracked and ignored source/build artifacts. | Preserve until the Thorium/Alacrium decision explicitly retains, archives, or discards the artifacts. Raw deletion would lose evidence not stored on GitHub. Harness-native cleanup is required. |

Temporary worktrees created to produce the current research notes are active
task work and are excluded from cleanup decisions.

## Inputs To The Downstream Disposition Decision

1. Decide the package and policy lanes independently. The inventory branch is a
   bundle of current-version changes, a utilyze retirement, and policy changes;
   preserving one part does not require reviving the bundle.
2. Treat the inventory pull request's build commands and review threads as a
   checklist seed. Re-run source verification, builds, payload inspection, and
   smokes against newly selected versions and declared dependencies.
3. Decide Thorium compatibility versus Alacrium migration before editing its
   branch. If historical reproduction matters, retain the package artifact,
   source tarball, checksum, and build notes outside the worktree before any
   cleanup.
4. Treat `nisavid/utilyze-adoption` as a named pointer to the present baseline,
   not as evidence that `0.1.3` was packaged or accepted.
5. Closeout should be target-local: resolve or preserve each open pull request,
   then classify its branch, artifacts, and worktree separately. Avoid global
   pruning or branch deletion while any unique local commit or untracked build
   output remains unaccounted for.
