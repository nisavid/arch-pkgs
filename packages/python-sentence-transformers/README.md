# python-sentence-transformers

Arch package for Sentence Transformers.

Use this package when Open WebUI or another local application needs embedding or
reranking support through the system PyTorch and Transformers stack.

## Maintenance Baseline

- `authoritative_reference`: `aur/python-sentence-transformers`
- `advisory_references`: upstream `UKPLab/sentence-transformers` release notes
- `divergence_notes`:
  - This package keeps the AUR source-build shape.
  - Dependencies use generic Arch virtual names so the sibling ROCm/gfx1151
    packages can satisfy PyTorch, Transformers, NumPy, and Pillow.
- `update_notes`:
  - Diff `aur/python-sentence-transformers` before updating.
  - Recheck dependency metadata against the system PyTorch and Transformers
    providers before accepting a new upstream version.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
