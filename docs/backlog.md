# Backlog

This doc tracks active follow-up work for this repo. It is for maintainers and
for users who want to understand package workflow work that has not been fully
accepted yet.

## Repo workflow tooling

### Adopt declarative package maintenance policies

This repo has started to need package-specific maintenance policy beyond a
plain `PKGBUILD` workflow. `codex-app` is the first concrete case: it is built
by the maintained `codex-app-linux` source repo, and this repo should ingest a
fresh package artifact when one exists instead of rebuilding it here.

Adopt a generic, declarative maintenance-policy system derived from the
[`arch-strix-halo-pkgs`](https://github.com/nisavid/arch-strix-halo-pkgs)
approach, then express the `codex-app` ingestion policy as the first instance.
The current `tools/ingest_codex_app.zsh` helper should be treated as a working
bridge, not the final package-policy architecture.

If this repo's fetch, freshness, or update-disposition workflows develop gaps,
use the `arch-strix-halo-pkgs` refresh/update hardening stack as a reference
pattern. In particular, review its package-maintenance skill, freshness checker,
candidate-disposition ledger, and backlog/current-state wiring before designing
new local policy.

Deliverables:

- A small policy format for package maintenance rules, including source
  checkout location, freshness window, artifact selection, build command, and
  ingest/publish behavior.
- A canonical ignored `upstream/` checkout area for source repos that are not
  owned by this repo.
- A runner that can evaluate a package's policy and perform the declared
  action.
- A `codex-app` policy that preserves the current rule: use a package built in
  the past 24 hours when present; otherwise run `make build-app pacman` in
  `upstream/codex-app-linux`, cloning the source repo first when needed.
- Maintainer docs that explain how to add another package with the same policy
  mechanism.

Exit criteria:

- `codex-app` no longer needs a one-off ingest script for its normal update
  path.
- A maintainer can add a second package policy without designing new plumbing.
- The policy runner reports clearly whether it reused a fresh artifact, built a
  new artifact, or failed before publishing anything.

### Package `amerge` for shared local-repo management

`amerge` is not part of this repo workflow yet. The current install path is the
explicit build, refresh, publish, and install sequence in
[`docs/usage/local-repo.md`](usage/local-repo.md).

Future work may extract `amerge` from
[`arch-strix-halo-pkgs`](https://github.com/nisavid/arch-strix-halo-pkgs) into
its own package, then use that shared tool as the local-repo package manager for
both repos.

Exit criteria:

- `amerge` is available as a package outside
  [`arch-strix-halo-pkgs`](https://github.com/nisavid/arch-strix-halo-pkgs).
- This repo's local-repo usage docs either adopt it or explicitly keep the
  manual workflow as the preferred path.
