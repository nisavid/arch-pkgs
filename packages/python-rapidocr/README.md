# python-rapidocr

Arch source package for RapidOCR with the upstream default ONNX models included.

The package keeps `rapidocr/config.yaml` and all three model files under the
Python library root, so the default CPU ONNX Runtime path can initialize with an
empty cache and no network access.

## Maintenance Baseline

- `authoritative_reference`: AUR `python-rapidocr` recipe at commit
  `c2ed4f7f5844204ca6a110bd683c395fac3f406c`, aligned to upstream RapidOCR
  `v3.9.2` commit `095232a4c94f7f0e6600ba5bba1177010ad696d4`
- `advisory_references`: upstream release workflow, `prepare_wheel_assets.py`,
  `default_models.yaml`, and the PyPI `rapidocr` 3.9.2 wheel
- `divergence_notes`:
  - Build from the immutable commit archive because PyPI publishes no source
    distribution for this release.
  - Make `python-onnxruntime` a hard dependency and retain the packaged upstream
    `config.yaml` rather than moving it into `/etc`.
  - Package the exact detector, classifier, and recognizer models selected by
    upstream. Conflict with and replace `python-rapidocr-onnxruntime`, but do not
    provide it because the legacy package exposes a different import and API.
- `update_notes`:
  - Reconfirm the release commit, source-build metadata, model selection, and
    every immutable source hash before changing the version.
  - Regenerate `.SRCINFO`, build in a clean environment, inspect the payload,
    and prove the default OCR path uses all package-owned models with caches
    empty and network access blocked.
  - Keep the package deferred from publication until the composed Open WebUI
    core acceptance gate passes against the exact Python/provider set.

## Verification

```bash
makepkg --verifysource
makepkg -f
```
