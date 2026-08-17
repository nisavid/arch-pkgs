# python-faster-whisper

Arch package for Faster Whisper transcription.

Use this package when Open WebUI needs local speech-to-text support without
bundling Faster Whisper and CTranslate2 inside the Open WebUI package.

## Maintenance Baseline

- `authoritative_reference`: upstream `SYSTRAN/faster-whisper` release `1.2.1`,
  the exact selected Open WebUI speech target
- `advisory_references`: AUR `python-faster-whisper` source-package recipe and
  upstream Faster Whisper release and installation documentation
- `divergence_notes`:
  - The current package `1.2.1-1` already matches the selected application
    version, but it has not passed the selected speech acceptance contract.
  - Preserve the AUR source-build shape and generic `python-ctranslate2` and
    `python-onnxruntime` provider dependencies. The accepted set must compose
    with CTranslate2 `4.8.1` and the exact Python 3.14/system-provider profile.
  - ROCm-accelerated CTranslate2 remains outside this repository's lane.
- `update_notes`:
  - Keep this package deferred and excluded from publication until the complete
    Open WebUI speech G0-G2 gate passes; matching the selected version is not
    acceptance.
  - G0 must verify immutable `1.2.1` sources and checksums, regenerated
    `.SRCINFO`, package-baseline metadata, and the exact speech compatibility
    matrix with CTranslate2 `4.8.1`.
  - G1 must clean-build and inspect the package and dependency payload without
    undeclared runtime acquisition or a bundled provider stack.
  - G2 must run offline CPU `int8` transcription and word timestamps against
    the pinned tiny model and JFK audio fixture after the required CTranslate2
    CPU/OpenBLAS model, malformed-model, and ownership checks pass.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
