# ctranslate2

Arch split package for CTranslate2 and its Python bindings.

Use this package when a local Python application needs Faster Whisper's
CTranslate2 runtime without pulling PyPI's CUDA-oriented wheel stack into an
application-private tree.

## Package Contents

- `ctranslate2`
- `python-ctranslate2`

## Maintenance Baseline

- `authoritative_reference`: upstream `OpenNMT/CTranslate2` release `v4.8.2`,
  the selected Open WebUI speech target, amended from `v4.8.1` for security
- `advisory_references`: AUR `ctranslate2` split-package recipe and upstream
  CTranslate2 release notes and build documentation
- `divergence_notes`:
  - The split recipe packages `4.8.2` for its StorageView index
    out-of-bounds-read fixes and its size validation before allocation, on top
    of the `4.8.1` model-load heap-overflow and Whisper correctness fixes.
  - Preserve the generic CPU/OpenBLAS split-package lane and omit the unused
    Intel oneAPI MKL dependency while `WITH_MKL=OFF`. ROCm/HIP acceleration
    remains outside this repository's lane.
  - Map the Thrust source to NVIDIA CCCL (since `4.8.0`) and keep the separate
    Cub source removed. `4.8.2` pins `cxxopts` `v3.3.1`, which already carries
    the GCC 15 fix, so the recipe no longer cherry-picks it.
  - `4.8.2` drops the runtime `setuptools` requirement and imports its
    converters lazily, so `python-ctranslate2` depends on neither
    `python-setuptools` nor PyTorch. PyTorch stays optional for conversion.
- `update_notes`:
  - The Open WebUI speech G0-G2 gate passed with Faster Whisper `1.2.1`; see
    the [candidate evidence](../../docs/maintainers/evidence/speech-providers-4.8.2-1.2.1/).
    Keep both split packages deferred and excluded from publication until
    [Promote or defer the Open WebUI speech sublane](https://github.com/nisavid/arch-pkgs/issues/50)
    decides; a passed candidate gate is not promotion.
  - G0 must verify immutable sources, checksums, regenerated `.SRCINFO`, the
    `4.8.2` source/dependency mapping, patch intent, and the exact speech
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
