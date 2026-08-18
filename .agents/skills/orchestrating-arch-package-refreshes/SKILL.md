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

Before package-lane work, apply the branch-start and repository-admission rules
in the policy's [re-entry section](../../../docs/policies/package-refresh-lifecycle.md#re-entry-and-decision-closure).
Each implementation lane starts from accepted protected `main`, not from a
stale branch retained as historical evidence. A new required CI context first
lands and passes on protected `main`; protection may refer to it only after its
exact context is observed.

For every applicable lane or coupled series, require explicit graph nodes for:

1. candidate production and immutable identity capture;
2. acceptance deployment of those exact candidate bytes;
3. promotion or explicit deferral;
4. accepted-only staging and publication;
5. lane-specific production deployment of the same published identity;
6. installed/runtime acceptance and rollback proof; and
7. retention release or continued preservation.

Audit the graph against the policy's
[required ticket shape](../../../docs/policies/package-refresh-lifecycle.md#required-ticket-shape).
In particular, render each lane or coupled series and reject it unless
`acceptance deployment` and `production deployment` are separately named.
Reject a generic terminal "deploy everything" node.

Use `implement` with `tdd` for one approved execution ticket at a time and
`maintaining-arch-packages` for package files. Use `code-review` before a
checkpoint. Keep Git and pull-request mechanics with
`checkpointing-and-publishing-git-work` and `publishing-reviewable-prs`.

## Advance lanes by evidence

Track the lifecycle milestones defined by the policy:

`candidate` → `acceptance-deployable` → `publication-eligible` → `published`
→ `production-deployed` → `retention-releasable`

Keep the policy's artifact evidence, lane disposition, repository state, and
deployed state as separate proof planes. Advance a milestone only when its exit
evidence exists. Carry one immutable artifact identity across acceptance,
promotion, publication, and installation. A rebuild or substitution, even at
the same version, creates a new candidate.

On a failed, inconclusive, or unavailable gate, or when a required paid,
privileged, live-state, or cleanup action lacks authority:

- preserve the candidate, evidence, state, and rollback material;
- mark the affected target deferred and publication-ineligible;
- preserve an older accepted identity only when the catalog explicitly keeps
  that identity publication-eligible;
- record the exact gate or authority needed to resume; and
- continue independent lanes whose dependencies remain satisfied.

When authority is present, route password-gated, paid-provider, live-host,
publication, installation, and service mutations through
`handling-privileged-steps` and verify the result. Never infer acceptance from
inability to run a gate.

Coupled lanes may produce candidates in parallel. Their composed acceptance,
promotion, publication, and production deployment follow dependency order.

## Publish and deploy exact accepted identities

Apply the policy's
[accepted-only publication](../../../docs/policies/package-refresh-lifecycle.md#accepted-only-publication)
contract. Reconstruct staging from empty against an explicit manifest of
promoted artifact identities; the repo updater and publisher do not decide
acceptance. If ordinary tooling cannot stage an accepted archive without
rebuilding, create an implementation ticket for that missing boundary.

Route the `packages/chatgpt/` immutable-ingest exception through its README and
`tools/ingest_chatgpt.zsh`; never invent a recipe or pass it to the ordinary
repo updater. Name both `packages/chatgpt/README.md` and
`tools/ingest_chatgpt.zsh` explicitly in the lifecycle ledger or ticket.

If repository recovery identity is ambiguous, preserve live, candidate,
previous, lock, and manifest state; mark the repository unverified and forbid
metadata refresh or installation until reconciled.

For deployment and cleanup, enforce the policy's
[production boundary](../../../docs/policies/package-refresh-lifecycle.md#production-deployment-and-cleanup):
install the exact published identity; pre-verify the replacement; serialize
producer and updater authority through a producer-free switch; and keep the
production edge lane-specific or explicitly dependency-coupled. That edge names
state preservation or migration, installed identity, health, rollback triggers
and evidence, and a stability condition. Release retention only after those
gates pass plus explicit, provenance-aware, target-local cleanup authority.
Before reporting the tail as execution-ready, confirm that the production
ticket must define its stability condition and that cleanup is explicitly
described as provenance-aware and target-local.

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
