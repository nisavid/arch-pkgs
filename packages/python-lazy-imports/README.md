# python-lazy-imports

Arch package for the Python `lazy-imports` support library used by Haystack.

## Maintenance Baseline

- `authoritative_reference`: upstream
  [`lazy-imports` PyPI source and metadata](https://pypi.org/project/lazy-imports/1.2.0/);
  no same-name Arch or AUR recipe was available at the 2026-08 refresh.
- `advisory_references`: upstream
  [`lazy-imports` source](https://github.com/bachorp/lazy-imports) and Haystack's
  declared dependency metadata.
- `divergence_notes`: the current recipe packages upstream `1.2.0` from its
  source distribution with only Python as a runtime dependency; this remains
  the selected supporting version for Haystack `3.0.0`.
- `update_notes`: verify the immutable source, clean-build and inspect the
  package on Python 3.14, then prove its imports in the deferred Haystack 3
  offline behavior and migration gates before publication.
