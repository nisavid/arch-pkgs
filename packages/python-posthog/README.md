# python-posthog

Arch package for the PostHog Python client used by Haystack's optional
telemetry integration.

## Maintenance Baseline

- `authoritative_reference`: upstream
  [`posthog` 7.38.4 release and source](https://github.com/PostHog/posthog-python/releases/tag/posthog-v7.38.4),
  because the same-lane AUR recipe trails the selected release.
- `advisory_references`: AUR
  [`python-posthog`](https://aur.archlinux.org/packages/python-posthog) for Arch
  packaging shape and upstream PyPI metadata for dependency constraints.
- `divergence_notes`: the current recipe packages upstream `7.16.2`; the
  selected `7.38.4` destination includes a substantial outbound-reporting and
  privacy delta and has not yet been accepted. Haystack telemetry must remain
  off when unset and available only through an explicit, reversible opt-in.
- `update_notes`: freeze and verify the selected source, diff the AUR packaging,
  audit dependency and reporting changes, clean-build and inspect the package
  on Python 3.14, then prove fail-closed telemetry behavior as part of the
  deferred Haystack 3 and Hayhooks lane before publication.
