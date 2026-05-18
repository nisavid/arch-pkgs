# python-rapidocr-onnxruntime

Arch package for RapidOCR's ONNX Runtime backend.

Use this package when Open WebUI needs OCR support through a system
`python-onnxruntime` provider instead of a private PyPI wheel.

## Maintenance Baseline

- `authoritative_reference`: `aur/python-rapidocr-onnxruntime`
- `advisory_references`: upstream `RapidAI/RapidOCR` release notes
- `divergence_notes`:
  - This package keeps the AUR wheel-install shape.
  - Dependencies use generic Arch provider names so
    `python-onnxruntime-opt-rocm` and system OpenCV can satisfy runtime imports.
- `update_notes`:
  - Diff `aur/python-rapidocr-onnxruntime` before updating.
  - Recheck the ONNX Runtime provider package before changing dependency names.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
