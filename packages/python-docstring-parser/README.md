# python-docstring-parser

Arch package for the Python `docstring-parser` library used by Haystack and
Hayhooks.

## Maintenance Baseline

- `authoritative_reference`: AUR
  [`python-docstring-parser`](https://aur.archlinux.org/packages/python-docstring-parser),
  the same source-build and version lane as this package.
- `advisory_references`: upstream
  [`docstring-parser` PyPI source and metadata](https://pypi.org/project/docstring-parser/0.18.0/).
- `divergence_notes`: the current recipe packages upstream `0.18.0` as an
  architecture-independent wheel with only Python as a runtime dependency; no
  package-specific divergence is currently selected.
- `update_notes`: diff the AUR recipe, verify the immutable source, clean-build
  and inspect the package on Python 3.14, and prove imports in the deferred
  Haystack 3 and Hayhooks lane before publication.
