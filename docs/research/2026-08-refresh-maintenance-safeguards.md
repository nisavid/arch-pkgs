# Refresh Maintenance Safeguards Audit

## Answer

The repository has useful local package rules and a sound review ruleset, but
it does not currently make its package-maintenance claims merge-gating facts.
At the audited commit, local checks pass and all tracked `.SRCINFO` files match
their recipes, yet a pull request can merge without running those checks; the
human catalog already disagrees with two recipes; most package directories lack
the maintenance metadata required by repository policy; and Codex app ingestion
does not bind an artifact to a reviewed source revision.

The minimum safeguard set for this refresh is:

1. one always-on repository-consistency workflow, made a required status check
   after its check name has run successfully;
2. one complete, dated package catalog whose recipe-backed versions are checked
   against `.SRCINFO` and whose rows carry the refresh disposition and next
   gate;
3. complete package-baseline metadata for every maintained package lane;
4. a narrow, provenance-aware Codex app ingestion contract with tests; and
5. a clean local-repository rebuild whose package manifest is checked before
   and after publication.

These are safeguards for the current refresh. A generalized maintenance-policy
engine, provider-based freshness checker, reusable disposition ledger, `amerge`
extraction, and cross-repository adoption remain outside this map and are
already preserved in the open issue [Chart declarative package maintenance and
amerge adoption](https://github.com/nisavid/arch-pkgs/issues/17).

## Provenance and method

- Audit date: 2026-08-11.
- Repository base: immutable commit
  [`ca744c74ea8bca30c6ac3166b7e1006821c51dba`](https://github.com/nisavid/arch-pkgs/tree/ca744c74ea8bca30c6ac3166b7e1006821c51dba).
- Research branch: `research/refresh-maintenance-safeguards`, created in a
  directly agent-created isolated worktree from that exact commit.
- Reference repository: immutable commit
  [`c8b3181a952b92ef7c870b97af437263be38519b`](https://github.com/nisavid/arch-strix-halo-pkgs/tree/c8b3181a952b92ef7c870b97af437263be38519b).
- GitHub configuration was read through the repository APIs on the audit date,
  including the active [`main` ruleset](https://api.github.com/repos/nisavid/arch-pkgs/rulesets/15548292),
  Actions configuration, workflow list, recent runs, and the `main` branch.
- Local evidence was collected with `python -m unittest`, `zsh -n` over every
  tracked Zsh helper, and `diff` between every tracked `.SRCINFO` and
  `makepkg --printsrcinfo`. The last command is the supported way to generate
  SRCINFO content according to the
  [Arch `makepkg(8)` manual](https://man.archlinux.org/man/makepkg.8.en#--printsrcinfo).

No package source download or package build was performed. This audit assesses
maintenance safeguards, not current package buildability.

## Existing safeguards

### Local repository checks

The eight committed unit tests all pass. They cover the Arch CUDA container,
SSH entrypoint, GPU validation modes, tag helper, workflow structure, pinned
action references in that workflow, and its maintainer documentation. The
test's Zsh syntax case covers three named scripts rather than discovering all
tracked Zsh helpers ([test source](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/tests/test_arch_cuda_image.py#L13-L197)).

A broader audit found:

- all six tracked Zsh helpers parse successfully;
- all 16 package directories with a `PKGBUILD` have a tracked `.SRCINFO`;
- all 16 `.SRCINFO` files exactly match current `makepkg --printsrcinfo`
  output; and
- there are 17 package directories because `codex-app` ingests an artifact
  instead of carrying a second recipe.

The repository instructions already require `.SRCINFO` regeneration and fresh
package evidence, while the catalog documents `makepkg --verifysource` followed
by `makepkg -f` as the package build route
([catalog build instructions](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/packages/README.md#L40-L58)).
Those are good operator contracts. They are not automated merge gates.

### GitHub rules and workflows

The active `main` ruleset blocks deletion and non-fast-forward updates. It also
requires pull requests, one approval, approval of the last push, dismissal of
stale approvals, and resolution of review threads. CodeQL, GitHub code quality,
and Copilot review rules are enabled. The ruleset has no required-status-check
rule ([live ruleset response](https://api.github.com/repos/nisavid/arch-pkgs/rulesets/15548292)).

GitHub reports the tracked Arch CUDA workflow plus GitHub-managed CodeQL and
Copilot workflows. The only workflow file in the audited tree is
`arch-cuda-image.yml`. Its pull-request trigger is limited to the CUDA image,
its helper, its workflow file, and one maintainer document; the PR job builds
only the container. A normal package or catalog change does not trigger it
([workflow source](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/.github/workflows/arch-cuda-image.yml#L1-L44)).

The workflow's external actions are pinned to full commit SHAs, and the local
test enforces that property for this one file. Repository Actions settings do
not globally require SHA pinning, so a future workflow can silently weaken the
property. GitHub documents a full commit SHA as the immutable action reference
([GitHub Actions documentation](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/manage-custom-actions#using-a-commit-sha-for-release-management)).

This leaves two distinct gaps:

- package correctness and repository consistency are not run in GitHub CI;
- even a future repository-check workflow would remain advisory until the
  `main` ruleset requires its status. GitHub's ruleset documentation confirms
  that required status checks must pass before merge
  ([GitHub ruleset documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging)).

### Catalog, freshness, and maintenance metadata

`packages/README.md` is the only complete human inventory. It says freshness is
checked per maintenance task and records 2026-05-23 as its last upstream review
date ([catalog contract](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/packages/README.md#L7-L12)).
It has no per-row reviewed date, upstream cursor, disposition, evidence link, or
next gate. A row marked `Current` therefore cannot say what was checked or when.

The catalog has already drifted from repository truth:

- it records Hayhooks `1.19.1-1`, while the recipe is `1.19.2-1`
  ([catalog row](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/packages/README.md#L18),
  [recipe](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/packages/hayhooks/PKGBUILD#L1-L3));
- it records `python-posthog` `7.15.3-1`, while the recipe is `7.16.2-1`
  ([catalog row](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/packages/README.md#L35),
  [recipe](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/packages/python-posthog/PKGBUILD#L1-L3)).

The reference-package policy requires `authoritative_reference`,
`advisory_references`, `divergence_notes`, and `update_notes` in package README
maintenance sections
([policy](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/docs/policies/reference-packages.md#L57-L71)).
Only 6 of 17 package directories currently contain all four fields. The 11
incomplete directories are:

- `codex-app`
- `hayhooks`
- `haystack-ai`
- `python-backoff`
- `python-docstring-parser`
- `python-fastapi-openai-compat`
- `python-haystack-experimental`
- `python-lazy-imports`
- `python-posthog`
- `qdrant`
- `utilyze`

There is no current automated upstream freshness discovery, machine-readable
review cursor, or durable adopted/tracked/rejected/blocked disposition. That
absence is acceptable only if the current refresh leaves a complete, dated
manual record and the broader automation stays visibly queued.

### Codex app ingestion

The Codex helper is a useful bridge, and its README describes its policy. The
implementation defines “fresh” as an artifact whose filesystem mtime is within
24 hours, choosing the newest matching filename
([selection logic](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/tools/ingest_codex_app.zsh#L48-L70)).
If a source directory exists, the helper verifies only that it is some Git
worktree; it does not verify its origin, branch, revision, cleanliness, tracking
state, or whether it contains the reviewed upstream source. If absent, it clones
the remote's current default branch without recording the resolved commit
([checkout logic](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/tools/ingest_codex_app.zsh#L72-L97)).

Before staging, it validates only that `pacman -Qp` reports package name
`codex-app`. It does not bind package version, architecture, checksum, source
commit, or build invocation to the artifact. After a successful fallback build,
it selects the newest artifact regardless of age, so a command that succeeds
without producing a new archive can reuse an older output
([build and selection path](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/tools/ingest_codex_app.zsh#L227-L265)).

Staging removes the existing database entry and archive before copying or
linking the replacement and running `repo-add`. A later failure can therefore
leave a partially updated staging repository
([staging logic](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/tools/ingest_codex_app.zsh#L148-L171)).
No committed test covers this helper, and the existing unit test's Zsh list
does not parse it.

### Local repository publication

The documented local repository is intentionally disposable. The update helper
replaces only explicitly targeted package names and leaves unrelated packages
alone; the publish helper then mirrors the complete staging directory with
`rsync --delete`
([update helper](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/tools/update_pacman_repo.zsh),
[publish helper](https://github.com/nisavid/arch-pkgs/blob/ca744c74ea8bca30c6ac3166b7e1006821c51dba/tools/publish_pacman_repo.zsh)).
That is reasonable for incremental work, but it cannot prove that a full refresh
removed retired package archives or that every accepted package has the exact
expected version. Neither helper emits or checks a package manifest, and the
publish path does not compare the destination database with staging after the
copy.

## Relevant reference-repository patterns

`arch-strix-halo-pkgs` demonstrates useful contracts at a larger scale. It is a
reference for the semantics, not a mandate to import its architecture into this
refresh.

- Every recipe directory belongs to exactly one freshness family. A family
  records source roles, the last reviewed cursor, comparison policy, priority,
  and workflow
  ([freshness policy](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/policies/package-freshness.toml)).
- Its read-only checker distinguishes discovery states such as current, stable
  update, baseline drift, metadata mismatch, query failure, and manual review.
  It invalidates cached results when package directories or relevant policy
  inputs change
  ([checker](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/tools/check_package_updates.py),
  [workflow contract](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/docs/maintainers/update-workflows.md#L15-L94)).
- Discovery and disposition are separate. Actionable candidates receive an
  adopted, tracked, rejected, or blocked disposition, with the next gate kept
  durable
  ([candidate ledger](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/docs/maintainers/update-candidates.toml),
  [disposition contract](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/docs/maintainers/update-workflows.md#L67-L121)).
- Tests exercise missing policy coverage, invalid source contracts, and source
  mismatches rather than trusting human convention
  ([checker tests](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/tests/test_check_package_updates.py)).
- Repository-local dependency edges can derive a build order and downstream
  affected set
  ([package graph tests](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/tests/test_repo_package_graph.py)).
- Its reference-package policy carries the same four maintenance fields into
  generated package metadata and READMEs, making the next update legible from
  repository files
  ([reference policy](https://github.com/nisavid/arch-strix-halo-pkgs/blob/c8b3181a952b92ef7c870b97af437263be38519b/docs/policies/reference-packages.md)).

The transferable lesson is to make coverage, reviewed state, disposition, and
next gates explicit and testable. The current refresh does not need the
reference repository's provider framework, policy renderer, graph engine, or
`amerge` implementation to obtain that benefit.

## Minimum safeguard specification for this refresh

### 1. Add and require one repository-consistency check

Create a workflow with an unchanging job name that runs for every pull request
and for pushes to `main`, without package-path exclusions. Run it in an Arch
environment so `makepkg --printsrcinfo` is authoritative. It must fail when:

- committed unit tests fail;
- any tracked Zsh helper fails `zsh -n`;
- a `PKGBUILD` lacks `.SRCINFO`, a `.SRCINFO` lacks `PKGBUILD`, or generated
  SRCINFO differs;
- a package directory is absent from the catalog or appears more than once;
- a recipe-backed catalog version differs from `.SRCINFO`;
- a maintained package lacks the four required baseline fields; or
- any external action in any workflow is not pinned to a full commit SHA.

After the workflow has produced its real check name successfully, add that name
as a required status check in the active `main` ruleset. Keep CodeQL and review
rules; they answer different questions. This gate deliberately does not run all
package builds in hosted CI.

### 2. Make the catalog the complete refresh index

Keep `packages/README.md` as the single human inventory, but make every one of
the 17 package directories appear exactly once. Each row must carry:

- recipe-backed packaged version, or an explicit ingested-artifact version;
- accepted-current, deferred, or retired disposition;
- exact upstream target or reviewed cursor;
- review date;
- acceptance state or next gate; and
- a link to package-local detail when the row cannot explain the decision in
  one line.

Generate or validate recipe-backed versions from `.SRCINFO`; do not hand-copy
them without a consistency test. Avoid undated `Current`. Update the row in the
same change that updates a recipe or changes a disposition.

For this refresh, upstream discovery may remain a deliberate manual sweep. The
completed catalog and lane evidence are the durable result. Automatic provider
queries, caching, and candidate-ledger architecture belong to the future
Wayfinder issue.

### 3. Complete the package maintenance story

Before a package lane is accepted, fill its README's
`authoritative_reference`, `advisory_references`, `divergence_notes`, and
`update_notes`. The update notes must name the lane's actual acceptance gates,
including build, payload inspection, install, service, browser, GPU, or other
runtime checks when applicable. The catalog links to this detail instead of
duplicating it.

CI verifies presence and basic shape. It cannot prove that a baseline remains
the right baseline or that an expensive acceptance gate passed; those remain
reviewed package-lane evidence.

### 4. Bind Codex ingestion to reviewed source and artifact provenance

Keep the one-off helper for this refresh, but require it to:

- resolve and record the exact source origin and commit used;
- reject an unexpected origin, dirty source tree, or unreviewed revision;
- reuse an artifact only when its recorded source revision and package
  metadata match the selected revision and target;
- after a build, require an artifact produced by that invocation rather than
  falling back to an arbitrary old archive;
- validate name, version, architecture, and checksum before changing staging;
- stage transactionally or preserve the previous database and archive until
  the replacement and database update succeed; and
- emit a small provenance record suitable for the catalog or lane evidence.

Add fixture-driven tests for fresh reuse, stale rebuild, absent checkout,
unexpected or dirty checkout, build-without-output, invalid artifact metadata,
and staging failure. This is immediate hardening of the existing bridge, not a
generic maintenance-policy runner.

### 5. Close the refresh with a clean repository rebuild

Do not treat the current incremental staging repository as acceptance evidence.
After lane decisions and builds are complete:

1. reconstruct staging from an empty temporary directory using only accepted
   package artifacts plus the provenance-checked Codex artifact;
2. emit an expected manifest of package names, versions, architectures, archive
   checksums, and source package directories;
3. compare that manifest with the generated pacman database and fail on
   missing, duplicate, unexpected, stale, or retired packages;
4. publish the verified staging tree; and
5. compare the published database and archive checksums with staging before
   installation or runtime acceptance checks.

This is a refresh-specific clean rebuild and verification path. It does not
require adopting `amerge`.

## Recommended order

1. Land the repository-consistency workflow, catalog schema, and baseline-field
   backfill before package refresh lanes begin.
2. Make the workflow's stable job name required in the `main` ruleset.
3. Use the catalog and package READMEs as the shared acceptance record while
   resolving each package lane.
4. Harden and test the Codex ingestion bridge before accepting the Codex lane.
5. Rebuild and verify the local repository from the accepted inventory only
   after all lane dispositions are settled.

That order prevents new drift during the refresh without turning this effort
into the policy-engine and `amerge` project that the future Wayfinder seed owns.
