# python-backoff

Arch package for the Python `backoff` retry-decorator library.

## Maintenance Baseline

- `authoritative_reference`: AUR
  [`python-backoff`](https://aur.archlinux.org/packages/python-backoff), the
  same source-build lane as this package.
- `advisory_references`: upstream
  [`backoff` PyPI source and metadata](https://pypi.org/project/backoff/2.2.1/).
- `divergence_notes`: the current recipe keeps upstream `2.2.1` and a minimal
  Python-only dependency surface; the AUR packaging revision may advance
  independently of the unchanged upstream source version.
- `update_notes`: diff the AUR recipe, verify the immutable source, clean-build
  and inspect the package on Python 3.14, and exercise its imports as part of
  the deferred PostHog and Haystack 3 dependency closure before publication.
