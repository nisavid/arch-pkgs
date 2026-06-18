# Context

## Glossary

- **Acceptance gate**: The strongest verification required before a package can
  be treated as ready for its declared contract.
- **Adopted package**: A package whose source, recipe, payload, and required
  acceptance gate are complete for the current ready inventory.
- **Agentically upgradable**: An upgrade candidate that an agent can adopt
  without stakeholder input because it can derive and complete the required
  acceptance gate without changing product intent, privacy or security posture,
  exposed service defaults, supported hardware lane, license or source
  provenance, or acceptance criteria.
- **Ready inventory**: The package catalog for packages accepted on `main`.
- **Tracked candidate**: An observed upgrade candidate that remains outside the
  ready inventory until its adoption work and acceptance gate are complete.
- **Upgrade candidate**: A newer upstream release, source ref, package baseline,
  or recipe input observed for a maintained package.
