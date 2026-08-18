---
name: orchestrating-arch-package-refreshes
description: Use for repository-wide or multi-lane Arch package refreshes, dormant refresh re-entry, refresh-index reconciliation, coupled package acceptance, exact-candidate promotion, accepted-only pacman repository publication, lane-specific production deployment, rollback retention, or refresh cleanup. Also use when a completed Wayfinder package-refresh map lacks execution tickets or when a plan ends in one generic deploy step. Do not use for an ordinary isolated package update or a one-off development `makepkg -si`; route those to the narrower repo-local skills.
---

# Orchestrating Arch Package Refreshes

Own the workspace-scale lifecycle and its transitions. Keep this skill thin:
route leaf mechanics to their existing owners instead of restating them.

Read [`docs/policies/package-refresh-lifecycle.md`](../../../docs/policies/package-refresh-lifecycle.md)
before acting. Treat written plans as hypotheses and compare them with the live
catalog, tracker, Git state, artifact identities, installed state, and current
repository policy.

## Route narrow work away

- For one isolated package update, use `maintaining-arch-packages`.
- For a one-off development build or install, use
  `deploying-local-arch-packages`.
- For an unresolved design or policy question, use `wayfinder` and its named
  research, prototype, or grilling skills.

Continue here only when multiple lanes, dormant re-entry, acceptance/promotion,
accepted-only publication, production cutover, or retention coordination makes
the lifecycle itself the work.

## Reconcile before mutation

For dormant or broad work, begin read-only. Reconcile:

- catalog targets, dispositions, lane ownership, and upstream cursors;
- branches, worktrees, in-progress Git operations, pull requests, and remote
  state;
- candidate, accepted, published, installed, and rollback identities;
- services, state, producers, updaters, locks, manifests, and recovery paths;
  and
- tracker decisions, execution children, dependencies, authority, and cleanup
  holds.

Report the proven current state, mismatches, and smallest frontier before
editing. Preserve ambiguous state.

If material decisions remain, route them through `wayfinder`. If the map is
decision-complete but has no vertical execution children, use `to-tickets`
before implementation. Use `github-issues` for native parent and blocking
relationships. Do not treat a closed decision map as proof that execution
happened.

## Project the lifecycle graph

Before package-lane work, project repository-wide admission safeguards. A new
required CI context first lands and passes on protected `main`; protection may
refer to it only after its exact context is observed.

For every applicable lane or coupled series, require explicit graph nodes for:

1. candidate production and immutable identity capture;
2. acceptance deployment of those exact candidate bytes;
3. promotion or explicit deferral;
4. accepted-only staging and publication;
5. lane-specific production deployment of the same published identity;
6. installed/runtime acceptance and rollback proof; and
7. retention release or continued preservation.

Dependency-only packages may share a coupled stack's production edge only when
the ticket names that relationship and its evidence. Reject a generic terminal
"deploy everything" node. Production deployment must name state preservation,
migration or cutover, dependencies, authority, health, rollback triggers,
rollback evidence, and the stability condition.

Before accepting the graph, render each applicable lane or coupled series as an
edge sequence and check that it contains two separately named nodes:
`acceptance deployment` and `production deployment`. Acceptance checks or a
promotion node do not substitute for acceptance deployment. A terminal deploy
node does not substitute for lane-specific production deployment. If either
edge is missing or collapsed, the graph is not execution-ready.

Use `implement` with `tdd` for one approved execution ticket at a time and
`maintaining-arch-packages` for package files. Use `code-review` before a
checkpoint. Keep Git and pull-request mechanics with
`checkpointing-and-publishing-git-work` and `publishing-reviewable-prs`.

## Advance lanes by evidence

Track the lifecycle milestones defined by the policy:

`candidate` → `acceptance-deployable` → `publication-eligible` → `published`
→ `production-deployed` → `retention-releasable`

Keep artifact evidence, lane disposition, repository state, and deployed state
as separate proof planes. Advance a milestone only when its exit evidence
exists. Carry one immutable artifact identity across acceptance, promotion,
publication, and installation. A rebuild or substitution, even at the same
version, creates a new candidate.

On a failed, inconclusive, unavailable, paid, privileged, or unauthorized gate:

- preserve the candidate, evidence, state, and rollback material;
- mark the affected target deferred and publication-ineligible;
- preserve an older accepted identity only when the catalog explicitly keeps
  that identity publication-eligible;
- record the exact gate or authority needed to resume; and
- continue independent lanes whose dependencies remain satisfied.

Route password-gated, paid-provider, live-host, publication, installation, and
service mutations through `handling-privileged-steps`. Never infer acceptance
from inability to run a gate.

Coupled lanes may produce candidates in parallel. Their composed acceptance,
promotion, publication, and production deployment follow dependency order.

## Publish and deploy exact accepted identities

Reconstruct staging from empty against an explicit manifest of promoted
artifact identities. Reconcile every staged entry with that manifest; the repo
updater and publisher do not decide acceptance. Route ordinary package archives
through the current local-repository workflow only when it preserves the exact
accepted bytes. If the tooling cannot stage an accepted ordinary archive
without rebuilding, create an implementation ticket for that missing boundary.

Route the `packages/chatgpt/` immutable-ingest exception through its README and
`tools/ingest_chatgpt.zsh`; never invent a recipe or pass it to the ordinary
repo updater.

If repository recovery identity is ambiguous, preserve live, candidate,
previous, lock, and manifest state; mark the repository unverified and forbid
metadata refresh or installation until reconciled.

Production deployment installs the exact published identity without rebuilding.
For a producer switch, pre-verify the replacement, create a producer-free
transaction gap, preserve shared state, and prevent overlapping update
authorities. Verify installed identity, migration or cutover, runtime health,
and rollback behavior before calling the lane production-deployed.

Cleanup comes only after the stability condition and rollback proof pass and
explicit authority names the targets. Use provenance-aware, target-local
cleanup; preserve ambiguous artifacts, recovery state, branches, and worktrees.

## Report the frontier

Return a concise lifecycle ledger with:

- each lane or coupled series and its current milestone across the separate
  proof planes;
- the immutable identity or missing binding;
- passed and open gates;
- native blockers and cross-lane order;
- authority and retention holds; and
- the exact next ticket, handoff, or command owner.

Keep versions, issue numbers, current lane inventories, and unsettled service
trust decisions out of the reusable skill. Read them from live evidence.
