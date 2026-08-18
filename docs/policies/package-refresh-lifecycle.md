# Package Refresh Lifecycle

Use this lifecycle for a repository-wide or multi-lane package refresh, for
re-entry into a dormant refresh, or when accepted artifacts must move through
publication and controlled deployment. An isolated package update stays with
the package-maintenance workflow. A development-only local install stays with
the local-deployment workflow.

The lifecycle coordinates existing owners. It does not replace package build,
tracker, review, Git, pull-request, publication, or privileged-operation
procedures.

## Proof planes and lifecycle milestones

Track artifact evidence, lane disposition, repository publication, and deployed
state as separate proof planes. The milestones below connect those planes; they
are not one flat enum. A runtime evidence set can be internally accepted while
the lane remains deferred and publication-ineligible at a later composed gate.
Coupled lanes may share an acceptance gate, but they do not share evidence by
implication.

| State | Required evidence | Permitted next action |
| --- | --- | --- |
| `candidate` | Exact source, build inputs, archive identity, and local gate results are recorded. | Prepare a declared acceptance environment. Do not publish or install in production. |
| `acceptance-deployable` | The candidate is unchanged, the acceptance environment and gate are defined, and required authority is present. | Deploy those exact bytes only to the disposable or otherwise authorized acceptance environment. |
| `publication-eligible` | The declared acceptance gate passed and an explicit promotion record binds the accepted artifact identity. | Include the exact accepted artifact in clean repository staging. |
| `published` | Accepted-only staging was reconstructed and verified, promoted atomically, and the published artifact identity matches the promoted identity. | Deploy the published identity through the lane's production route. |
| `production-deployed` | The exact published identity is installed, migration or cutover completed, runtime acceptance passed, and rollback anchors remain available. | Observe the lane-specific stability condition. |
| `retention-releasable` | The stability condition and rollback proof passed, and cleanup authority names the retained targets. | Perform target-local, provenance-aware cleanup. |

`deferred` is a pre-promotion lane disposition, not proof that every older
identity is unpublishable. A deferred target keeps its evidence and rollback
material, is excluded from accepted-only publication, and names the acceptance
gate needed to resume. A previously accepted identity remains publishable only
when the catalog explicitly marks that exact identity publication-eligible. A
failed or unavailable acceptance environment defers only the affected lane
unless a dependency edge also blocks another lane.

Later authority gaps are phase-specific holds, not retroactive demotions.
Missing publication authority preserves `publication-eligible`; missing
production authority preserves `published`; and missing cleanup authority
preserves `production-deployed` and its rollback anchors. Record the exact hold
without erasing the evidence or eligibility already established.

Artifact identity is continuous across the state transitions. Matching package
names and versions do not make rebuilt archives equivalent to accepted bytes.
Any rebuild, substitution, missing digest binding, or unreviewed promotion
delta returns the new artifact to `candidate`.

## Re-entry and decision closure

Begin broad or dormant work with read-only reconciliation:

- package catalog, selected upstream targets, and lane ownership;
- Git branches, worktrees, operations, pull requests, and unpublished commits;
- candidate, accepted, published, installed, and rollback artifact identities;
- installed services, updater or producer ownership, and retained state; and
- tracker decisions, open execution work, authority gates, and cleanup holds.

Report the proven current state and smallest frontier before editing. Preserve
ambiguous branches, worktrees, artifacts, locks, manifests, and recovery paths.

Use `wayfinder` while a material decision remains unresolved. A closed map is a
decision artifact, not an execution graph. Once the route is decision-complete,
use `to-tickets` to project it into vertical implementation tickets with native
blocking edges before broad implementation begins.

Start each implementation lane from accepted protected `main`. Do not
rehabilitate a stale bundled branch merely because it retains historical work;
keep it as evidence until its provenance and retention status permit cleanup.

Land repository-wide admission safeguards before package-lane changes. When a
new protected check is part of those safeguards, merge the check first, observe
its exact successful context on protected `main`, and only then require that
context.

## Required ticket shape

Every applicable lane or coupled lane series needs explicit work for:

1. producing and digest-binding candidate artifacts;
2. deploying the exact candidates to the declared acceptance environment;
3. recording promotion or explicit deferral;
4. including only promoted identities in clean repository staging and
   publication;
5. deploying the same published identities through a lane-specific production
   path;
6. validating installed/runtime behavior and exercising rollback triggers; and
7. releasing retention or recording why preservation continues.

Dependency-only packages may share a coupled stack's production edge when the
ticket states that relationship and binds their installed evidence. Do not
collapse the edges into a generic terminal deployment ticket. A
production ticket names its state preservation, migration or cutover,
dependencies, operator authority, health checks, rollback triggers, rollback
evidence, and stability condition.

Render each applicable lane or coupled series as an edge sequence before
approving the execution graph. The sequence must show separately named
`acceptance deployment` and `production deployment` nodes. Acceptance checks or
promotion do not replace acceptance deployment, and a terminal deployment node
does not replace lane-specific production deployment.

Candidate work for independent or coupled lanes may run in parallel. Coupled
acceptance, promotion, publication, and production deployment follow declared
dependency order. A lane may not borrow another lane's promotion merely because
the artifacts were built together.

## Acceptance and promotion

A clean package build is evidence for a candidate, not production authority.
Acceptance uses the exact candidate bytes and the lane's declared gates. Keep
local checks, immutable candidate evidence, hosted review and policy acceptance,
promotion, publication, installed acceptance, and retention release as separate
facts.

Paid providers, privileged hosts, live state, package installation, service
mutation, and publication need task-specific authority. Their presence does not
itself defer a lane. When authority is present, route the boundary through
`handling-privileged-steps` and verify the result. Otherwise prepare everything
that remains valid without the action. A missing, failed, or inconclusive
acceptance boundary leaves the candidate deferred and publication-ineligible.
At a later boundary, preserve the current milestone and record a publication,
production-deployment, or cleanup hold. No unavailable or unauthorized action
becomes an implicit pass.

The `packages/chatgpt/` immutable-ingest lane is the explicit exception to
local building. Follow its package README and `tools/ingest_chatgpt.zsh`; do not
invent a `PKGBUILD`, run `makepkg`, or pass it to
`tools/update_pacman_repo.zsh`. For terminal accepted-only publication with
ChatGPT as the only entry, omit the seed, use an absent or proven-empty dedicated
staging directory, and reconcile the complete result with the explicit
promotion manifest. Otherwise seed ingest only from a freshly materialized
repository whose complete database and archive set is bound to that manifest.
Do not reuse the live repository as a seed merely because its internal hashes
verify. If current tooling cannot enforce empty staging or materialize and prove
the accepted-only seed, create an implementation ticket and stop before
publication.

## Accepted-only publication

Build terminal staging from an empty destination against an explicit manifest
of artifact identities whose promotion records make them publication-eligible.
Exclude deferred targets and retired lanes, while retaining any older accepted
identity that the catalog explicitly keeps eligible. Reconcile every staging
entry with the accepted manifest: the repository updater and publisher do not
decide acceptance. If ordinary tooling cannot stage an exact accepted archive
without rebuilding, create an implementation ticket for that missing boundary.
Verify artifact and repository metadata identities before promotion, serialize
repository writers, and use the publication procedure in
[`docs/usage/local-repo.md`](../usage/local-repo.md).

Preserve the last-known-good repository. If live, candidate, previous, lock, or
manifest identities are ambiguous, preserve all of them, mark the published
repository unverified, and forbid metadata refresh or installation until the
identity is reconciled. Do not turn a recovery-state name into cleanup proof.

## Production deployment and cleanup

Install the exact accepted artifact as served by the verified published
repository. Do not rebuild at the accepted boundary. Verify installed package
identity before migration or cutover, then run the lane's runtime and rollback
checks.

A producer replacement first verifies the replacement, then creates a
producer-free transaction gap before enabling the new producer. Preserve shared
state and prevent overlapping services, updaters, or other update authorities.

Keep the last-known-good repository, accepted archives, matching configuration
and state, evidence, and required worktrees until the lane's stability and
rollback conditions pass. Cleanup is last. It requires explicit authority,
acts only on named targets, follows `checkpointing-and-publishing-git-work` for
Git provenance, and preserves anything whose identity or ownership is unclear.

## Workflow owners

- `orchestrating-arch-package-refreshes`: phase selection, lane state,
  cross-lane edges, and lifecycle exit gates.
- `maintaining-arch-packages`: one lane's discovery, recipe or asset changes,
  `.SRCINFO`, build verification, and package documentation.
- `deploying-local-arch-packages`: development installs and exact local host
  handoffs at the boundary declared by this lifecycle.
- `wayfinder`: unresolved decisions and research/prototype/grilling frontier.
- `to-tickets` and `github-issues`: execution projection and tracker mechanics.
- `implement`, `tdd`, and `code-review`: ticket implementation and review.
- `checkpointing-and-publishing-git-work` and `publishing-reviewable-prs`: Git
  checkpoints, remote publication, and reviewable pull requests.
- `handling-privileged-steps`: password-gated, privileged, paid, or live-host
  handoffs and post-action verification.

Current versions, issue numbers, lane inventories, temporary exceptions, and
unsettled service trust choices belong in the package catalog, tracker, and
evidence—not in this policy.
