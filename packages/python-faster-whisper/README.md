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
  - The current package `1.2.1-1` matches the selected application version.
    It passed the speech G0-G2 candidate gate with CTranslate2 `4.8.2`; see
    the [candidate evidence](../../docs/maintainers/evidence/speech-providers-4.8.2-1.2.1/).
  - Preserve the AUR source-build shape and generic `python-ctranslate2` and
    `python-onnxruntime` provider dependencies. The accepted set must compose
    with CTranslate2 `4.8.2` and the exact Python 3.14/system-provider profile.
  - ROCm-accelerated CTranslate2 remains outside this repository's lane.
- `update_notes`:
  - Keep this package deferred and excluded from publication until
    [Promote or defer the Open WebUI speech sublane](https://github.com/nisavid/arch-pkgs/issues/50)
    decides; matching the selected version or passing the candidate gate is
    not promotion.
  - G0 must verify immutable `1.2.1` sources and checksums, regenerated
    `.SRCINFO`, package-baseline metadata, and the exact speech compatibility
    matrix with CTranslate2 `4.8.2`.
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
