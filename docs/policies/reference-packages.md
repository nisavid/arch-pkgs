# Reference Package Policy

This policy explains how this repo chooses and records package baselines when a
new package is onboarded or an existing package's maintenance story changes.

## Purpose

Each maintained package needs a legible Arch-facing source story:

- which package recipe is the authoritative reference
- which nearby recipes are advisory references
- where this repo deliberately diverges
- what future maintainers should check during updates

That information belongs in tracked repo files, not chat history.

## Selection Rule

Choose the same or closest compatibility lane first. Only then rank sources
within that lane.

Compatibility lane means, as closely as available:

- same source type: upstream release, VCS snapshot, source build, binary
  package, service wrapper, Python package, or package bundle
- same interpreter, runtime, service, or build-tool family
- same architecture or hardware specificity
- same major.minor version lane

Within a matching lane, prefer:

1. Arch
2. CachyOS
3. AUR

If no package exists in the exact lane, use the closest available package. Do
not treat that as "no baseline exists" while there is still a useful recipe,
service unit, dependency list, install script, or config default to inspect.

Out-of-lane packages are still useful, but only as advisory references.

## Onboarding Checklist

Before writing a new `packages/<name>/PKGBUILD`:

1. Scout Arch, CachyOS, and AUR for same-lane and nearby package recipes.
2. Read the selected PKGBUILD, `.install` scripts, service files, config files,
   dependencies, optdepends, conflicts, and package comments.
3. Read upstream release notes and build/install documentation for the target
   version.
4. Compare interpreter and dependency constraints from upstream metadata
   against the host/runtime lane this repo supports.
5. Decide which baseline pieces to adopt, which to reject, and which to treat
   as advisory only.
6. Record the decision in the package README before closeout.

## Package README Metadata

Every `accepted-current` or `deferred` package in the checked refresh index must
have a package README with exactly one nonempty entry for each of these fields:

```markdown
## Maintenance Baseline

- `authoritative_reference`: <the package recipe or upstream source to diff first>
- `advisory_references`: <nearby packages and upstream material worth scouting>
- `divergence_notes`: <deliberate local differences, or an explicit statement that there are none>
- `update_notes`: <the mandatory update and validation checks>
```

The values may continue on indented lines when a field needs a list. Use `none`
only when review established that there is no relevant advisory reference or no
deliberate divergence; do not leave a value blank. A retired package is exempt
because its disposition and preservation-aware removal boundary live in the
refresh index and decision record rather than a maintained baseline.

The four fields answer different questions:

- `authoritative_reference` identifies the first package or upstream source to
  compare and its compatibility lane.
- `advisory_references` identifies other useful packaging, service, dependency,
  or platform sources without treating them as authoritative.
- `divergence_notes` states the local source, dependency, integration, privacy,
  or service behavior that an update must preserve or deliberately replace.
- `update_notes` states the freshness checks and lane-specific build, payload,
  migration, runtime, privacy, or hardware gates required after an update.

The repository consistency checker enforces field presence and basic shape:

```bash
python3 tools/check_repo_consistency.py
```

It does not decide whether the selected reference, divergence, or acceptance
gate is correct. That remains human package review; this policy is not a
generalized package-policy engine.

## Guardrails

- Do not copy networked post-install dependency bootstraps into maintained
  packages.
- Do not silently accept interpreter or dependency pins that conflict with the
  repo's supported host lane.
- Do not silently remove upstream version bounds. Carry compatibility patches
  only with visible rationale and verification.
- Prefer normal Arch system integration for users, services, config defaults,
  and state directories.
- Keep reusable source changes in patch files when practical instead of burying
  them in ad hoc PKGBUILD shell edits.
