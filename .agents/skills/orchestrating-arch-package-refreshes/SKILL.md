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

## Project and execute the lifecycle graph

Use the companion policy as the canonical source for transition invariants.
Orchestrate it in five passes:

1. Apply the branch-start and safeguard rules in
   [re-entry and decision closure](../../../docs/policies/package-refresh-lifecycle.md#re-entry-and-decision-closure).
   Each lane starts from accepted protected `main`; retained stale branches are
   evidence, not implementation bases.
2. Render every applicable lane or coupled series against the
   [required ticket shape](../../../docs/policies/package-refresh-lifecycle.md#required-ticket-shape).
   Require separately named candidate production, exact-candidate acceptance
   deployment, promotion or deferral, accepted-only publication, lane-specific
   production deployment, installed/rollback proof, and retention disposition.
   Reject a generic terminal "deploy everything" node.
3. Advance the policy's proof planes and milestones only when their exit
   evidence exists. Version equality never substitutes for the immutable
   artifact identity carried through acceptance, promotion, publication, and
   installation.
4. Apply the
   [accepted-only publication](../../../docs/policies/package-refresh-lifecycle.md#accepted-only-publication)
   and
   [production deployment](../../../docs/policies/package-refresh-lifecycle.md#production-deployment-and-cleanup)
   boundaries without moving leaf mechanics into this skill.
5. Release retention only after the declared stability and rollback conditions
   plus explicit, target-local, provenance-aware cleanup authority.

Use phase-specific holds. A failed, unavailable, or unauthorized acceptance
gate leaves that target deferred and publication-ineligible. Missing publication
authority preserves `publication-eligible`; missing production authority
preserves `published`; and missing cleanup authority preserves
`production-deployed`. Record the exact hold and resume edge without erasing
earlier evidence or eligibility. Preserve ambiguous identities, state, and
rollback material, and continue independent lanes whose dependencies remain
satisfied.

Route authorized password-gated, paid-provider, live-host, publication,
installation, and service mutations through `handling-privileged-steps` and
verify the result. Coupled candidates may run in parallel; composed acceptance
and later transitions follow dependency order.

For the `packages/chatgpt/` immutable-ingest exception, name and follow both its
README and `tools/ingest_chatgpt.zsh`; never invent a recipe or pass it to the
ordinary repo updater. In terminal accepted-only publication, omit seeding when
ChatGPT is the only entry. Otherwise seed only from a freshly materialized
repository whose every archive and database entry is bound to the explicit
promotion manifest. A verified live repository is not sufficient seed evidence.
If current tooling cannot produce that manifest-approved seed, open an
implementation ticket and stop before publication.

Use `implement` with `tdd` for one approved execution ticket at a time,
`maintaining-arch-packages` for package files, and `code-review` before a
checkpoint. Keep Git, pull-request, and leaf deployment mechanics with
`checkpointing-and-publishing-git-work`, `publishing-reviewable-prs`, and
`deploying-local-arch-packages`.

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
