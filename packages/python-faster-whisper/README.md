# python-faster-whisper

Arch package for Faster Whisper transcription.

Use this package when Open WebUI needs local speech-to-text support without
bundling Faster Whisper and CTranslate2 inside the Open WebUI package.

## Maintenance Baseline

- `authoritative_reference`: `aur/python-faster-whisper`
- `advisory_references`: upstream `SYSTRAN/faster-whisper` release notes
- `divergence_notes`:
  - This package keeps the AUR source-build shape.
  - It depends on generic `python-ctranslate2` and `python-onnxruntime` provider
    names so optimized providers can satisfy them.
  - ROCm-accelerated CTranslate2 remains out of scope for this repo.
- `update_notes`:
  - Diff `aur/python-faster-whisper` before updating.
  - Recheck whether the sibling repo provides a ROCm-aware
    `python-ctranslate2` replacement before changing runtime expectations.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
