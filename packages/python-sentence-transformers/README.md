# python-sentence-transformers

Arch package for Sentence Transformers.

Use this package when Open WebUI or another local application needs embedding or
reranking support through the system PyTorch and Transformers stack.

## Maintenance Baseline

- `authoritative_reference`: upstream `UKPLab/sentence-transformers` release
  `5.5.1`, the exact target for the first accepted Open WebUI set
- `advisory_references`: AUR `python-sentence-transformers` source-package
  recipe and upstream Sentence Transformers release and installation material
- `divergence_notes`:
  - The current package `5.5.1-1` already matches the selected application
    version, but it has not passed the selected core acceptance contract.
    Sentence Transformers `5.7.0` is a later compatibility candidate, not this
    baseline's target.
  - Preserve the AUR source-build shape and generic Arch provider dependencies,
    but resolve them for acceptance to the exact Python/gfx1151 `3.14.6`,
    Transformers `5.8.1`, Tokenizers `0.22.2`, Accelerate `1.13.0`,
    SentencePiece `0.2.1`, PyTorch `2.12.0`, NumPy `2.4.6`, Pillow `12.2.0`,
    SciPy `1.18.0`, and scikit-learn `1.9.0` profile.
- `update_notes`:
  - Keep this package deferred and excluded from publication until the exact
    Python 3.14/system-ML checks and the composed Open WebUI core G0-G4 gate
    pass; matching `5.5.1` is not acceptance.
  - G0-G1 must verify the immutable source and dependency metadata, regenerate
    `.SRCINFO`, clean-build the source package, inspect its payload, and record
    the exact provider matrix without bundling the system ML stack.
  - G2 must run a deterministic offline embedding and save/load check against
    the pinned tiny safetensors fixture under the exact installed CPU-forced
    provider set, including `pacman -Qo` ownership evidence.
  - G3-G4 must pass the composed Open WebUI service, API, privacy, persistence,
    browser, migration, preservation, and whole-runtime rollback gates before
    this core dependency can be accepted.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
