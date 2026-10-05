# python-faster-whisper

Arch package for Faster Whisper transcription.

Use this package when Open WebUI needs local speech-to-text support without
bundling Faster Whisper and CTranslate2 inside the Open WebUI package.

## PyAV 19 Compatibility

`0001-support-pyav-19.patch` backports upstream commit
[`2ce7f9d`](https://github.com/SYSTRAN/faster-whisper/commit/2ce7f9d7a9fbe315a5804a33bf7224d42e101174)
([SYSTRAN/faster-whisper#1495](https://github.com/SYSTRAN/faster-whisper/pull/1495))
onto the `1.2.1` tag tarball, byte for byte. It changes only
`faster_whisper/audio.py`.

- **Why:** PyAV 19.0.0 removed the `metadata_errors` argument to `av.open()`.
  Unpatched `1.2.1` still passes `metadata_errors="ignore"`, so
  `decode_audio()` raises `TypeError` on PyAV 19
  ([#124](https://github.com/nisavid/arch-pkgs/issues/124)).
- **Behavior:** the patch passes `metadata_errors="ignore"` only when the PyAV
  major version is below 19. PyAV 19 always decodes metadata as UTF-8 with
  `surrogateescape`, which cannot fail, so the guard against non-UTF-8 tags is
  no longer needed there. PyAV 18 and older keep the old behavior, so
  `python-av` stays unversioned in `depends`.
- **Drop condition:** drop the patch, its `source` and `b2sums` entries, and
  `prepare()` at the first upstream release that contains `2ce7f9d`.

## Maintenance Baseline

- `authoritative_reference`: upstream `SYSTRAN/faster-whisper` release `1.2.1`,
  the exact selected Open WebUI speech target
- `advisory_references`: AUR `python-faster-whisper` source-package recipe and
  upstream Faster Whisper release and installation documentation
- `divergence_notes`:
  - The package `1.2.1-1` matches the selected application version.
    It passed the speech G0-G2 candidate gate with CTranslate2 `4.8.2` on
    PyAV 18; see the
    [candidate evidence](../../docs/maintainers/evidence/speech-providers-4.8.2-1.2.1/).
  - `1.2.1-2` carries `0001-support-pyav-19.patch`, a backport of upstream
    `2ce7f9d` for PyAV 19; see [PyAV 19 Compatibility](#pyav-19-compatibility).
    That gate evidence covers `1.2.1-1`, not `1.2.1-2`.
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
  - On each upstream release, check whether it contains `2ce7f9d`; if it
    does, drop `0001-support-pyav-19.patch` and `prepare()`.

## Verification

```bash
makepkg -f --verifysource
makepkg -f
```
