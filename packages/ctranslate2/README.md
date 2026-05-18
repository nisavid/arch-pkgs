# ctranslate2

Arch split package for CTranslate2 and its Python bindings.

Use this package when a local Python application needs Faster Whisper's
CTranslate2 runtime without pulling PyPI's CUDA-oriented wheel stack into an
application-private tree.

## Package Contents

- `ctranslate2`
- `python-ctranslate2`

## Maintenance Baseline

- `authoritative_reference`: `aur/ctranslate2`
- `advisory_references`: upstream `OpenNMT/CTranslate2` release notes and build
  documentation
- `divergence_notes`:
  - This package keeps the AUR split-package shape.
  - This package builds the generic CPU/OpenBLAS lane only.
  - This package removes the unused Intel oneAPI MKL build dependency from the
    AUR baseline because `WITH_MKL=OFF`.
  - ROCm/HIP acceleration is intentionally out of scope here and belongs in the
    sibling `arch-strix-halo-pkgs` repo if needed.
- `update_notes`:
  - Diff `aur/ctranslate2` before changing the source, submodule, or build
    options.
  - Recheck upstream CTranslate2 build options before enabling a new backend.
  - Keep this package as the generic CPU provider unless a broader package
    policy says otherwise.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
