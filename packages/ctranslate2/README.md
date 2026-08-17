# ctranslate2

Arch split package for CTranslate2 and its Python bindings.

Use this package when a local Python application needs Faster Whisper's
CTranslate2 runtime without pulling PyPI's CUDA-oriented wheel stack into an
application-private tree.

## Package Contents

- `ctranslate2`
- `python-ctranslate2`

## Maintenance Baseline

- `authoritative_reference`: upstream `OpenNMT/CTranslate2` release `v4.8.1`,
  the selected Open WebUI speech target
- `advisory_references`: AUR `ctranslate2` split-package recipe and upstream
  CTranslate2 release notes and build documentation
- `divergence_notes`:
  - The current split recipe packages `4.7.2-1`; the selected target is `4.8.1`
    for its model-load heap-overflow and Whisper correctness fixes.
  - Preserve the generic CPU/OpenBLAS split-package lane and omit the unused
    Intel oneAPI MKL dependency while `WITH_MKL=OFF`. ROCm/HIP acceleration
    remains outside this repository's lane.
  - For `4.8.1`, map the Thrust source to NVIDIA CCCL, remove the obsolete
    separate Cub source and setup, retain the required GCC 15 `cxxopts` fix,
    add `python-setuptools` as a runtime dependency of `python-ctranslate2`, and
    keep PyTorch optional for conversion rather than required for inference.
- `update_notes`:
  - Keep both split packages deferred and excluded from publication until the
    Open WebUI speech G0-G2 gate passes with Faster Whisper `1.2.1`; version
    selection alone is not acceptance.
  - G0 must verify immutable sources, checksums, regenerated `.SRCINFO`, the
    `4.8.1` source/dependency mapping, patch intent, and the exact speech
    compatibility matrix.
  - G1 must clean-build and inspect both package payloads and dependency edges
    without an undeclared network or runtime acquisition path.
  - G2 must pass the upstream tests and bundled CPU/OpenBLAS model offline,
    including malformed-model failure without a crash, then pass the composed
    Faster Whisper CPU `int8` transcription and word-timestamp fixture.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
