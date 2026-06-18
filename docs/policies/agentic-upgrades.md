# Agentic Upgrade Policy

This policy defines when an agent may adopt a package update without asking for
stakeholder input.

## Agentically Upgradable Candidates

An upgrade candidate is agentically upgradable when the agent can derive and
complete the package's acceptance gate without changing:

- product intent
- privacy or security posture
- exposed service defaults
- supported hardware lane
- license or source provenance
- acceptance criteria

The candidate does not need to be a trivial version bump. The agent may refresh
patches, reshape package-local checks, and add targeted smokes when the correct
path is clear and tractable.

## Patch Handling

Patch changes are agentically upgradable when there is one clearly best path:

- refresh the patch against the new source
- replace the patch with an upstreamed equivalent
- remove the patch because upstream now provides the behavior
- add a small patch that preserves the current package contract

The agent must verify the selected path with source checks, package builds, or a
targeted smoke that covers the patched behavior.

## Acceptance Gates

The acceptance gate follows the package contract. Use the strongest gate needed
by the package's changed behavior:

- source verification for metadata-only source changes
- package build for changed source, patches, generated outputs, or build flags
- payload inspection for install layout changes
- import or CLI smoke for Python libraries and command-line tools
- service smoke for packaged services
- browser smoke for browser packages
- hardware or live validation only when that is part of the declared package
  contract

Package-local checks should be expanded or reshaped when a better local harness
or smoke can prove the contract. Do not defer a candidate only because the
existing checks are too narrow.

## Ready Inventory

No partially adopted package belongs in the ready inventory. A package on
`main` is either accepted for its declared contract or it stays on a tracking
branch until its acceptance gate is complete.

When a candidate cannot be adopted, record the failed or deferred gate in the
PR summary or package-local maintainer docs. Do not keep stale session reports
as durable policy.
