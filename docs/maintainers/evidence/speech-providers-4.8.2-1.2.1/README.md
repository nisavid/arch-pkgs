# Open WebUI Speech Providers G0-G2 Evidence

This directory holds the candidate evidence for the Open WebUI speech provider
sublane: `ctranslate2` and `python-ctranslate2` 4.8.2-1, plus
`python-faster-whisper` 1.2.1-1. The contract comes from the
[Open WebUI and local ML-stack decision](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835)
and its [CTranslate2 4.8.2 amendment](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5783734367),
which moved the target from 4.8.1 for security.

Lifecycle state: **candidate**. G0-G2 passed against the exact archives below.
The sublane stays deferred and publication-ineligible until
[Promote or defer the Open WebUI speech sublane](https://github.com/nisavid/arch-pkgs/issues/50)
reviews this evidence. The Open WebUI household-stack cutover owns production
installation.

| Archive | Size | SHA-256 |
| --- | --- | --- |
| `ctranslate2-4.8.2-1-x86_64.pkg.tar.zst` | 1055772 | `d0843d9254afde3dedd7d92e6e218aae63d559926f3ebffcdbf2827373d8267b` |
| `python-ctranslate2-4.8.2-1-x86_64.pkg.tar.zst` | 431574 | `6c8e5813e12e1a36d68af357afdce744481eca359a4d1576bfcd2d46ec765d0e` |
| `python-faster-whisper-1.2.1-1-any.pkg.tar.zst` | 1087994 | `9b052be890fd7f21135ca2ebc090ff140432e0e8493dd484b44585386ae8d1cb` |

The CTranslate2 archives were clean-built from source commit
`0b4b32705c7873f34405daccb415edc59ca58833`. The Faster Whisper archive is the
same bytes as in the superseded 4.8.1 set, because its recipe did not change.
Each archive's `.BUILDINFO` `pkgbuild_sha256sum` matches the PKGBUILD digests
recorded in `g0-g2.json`. A rebuild produces a new candidate, even at the same
version.

The earlier `ctranslate2` and `python-ctranslate2` 4.8.1-1 archives passed the
same G0-G2 procedure but are superseded. `g0-g2.json` keeps their names, sizes,
and digests under `supersedes`. They are not acceptance candidates.

## Files

- `g0-g2.json`: sources, recipe digests, build toolchain, archive and payload
  identities, and G2 results, including the provider profile and ownership
  summary.
- `g2_fixture.py`: the offline G2 harness.

## What G2 ran

The fixture extracts the three archives into one overlay root. It puts that
root's `site-packages` and `lib` first on `PYTHONPATH` and `LD_LIBRARY_PATH`,
ahead of the host's installed system providers. Everything runs under
`unshare -rn`, which leaves only loopback, with `HF_HUB_OFFLINE=1` and every
GPU visibility variable empty. The fixture then checks:

- That `ctranslate2` 4.8.2, `libctranslate2.so.4.8.2`, and `faster_whisper`
  1.2.1 all load from the candidate archives.
- The upstream CTranslate2 4.8.2 Python tests: 110 passed, 2 skipped (CUDA
  only), and 1 deselected (`test_logging` needs `wurlitzer`). They include the
  new check that importing `ctranslate2` loads neither PyTorch nor
  Transformers.
- The bundled `aren-transliteration` model at `float32` and `int8`.
- Four malformed `model.bin` variants. Each one raises a Python exception, and
  none of them kills the process.
- Faster Whisper `int8` CPU transcription of the JFK clip with word timestamps
  from the pinned `Systran/faster-whisper-tiny` revision, run with and without
  ONNX Runtime CPU VAD.
- Ownership of what the fixture loaded. Every module and native library from
  the overlay belongs to a candidate archive's manifest. `pacman -Qo` owns
  every other imported module and native library.

Against the 4.8.1 run, only the fixture's expected CTranslate2 version
changed. Its method and inputs are the same.

To reproduce, extract the archives into `<root>` and run:

```bash
env -i HOME="$HOME" PATH=/usr/bin LANG=C.UTF-8 \
  PYTHONPATH=<root>/usr/lib/python3.14/site-packages \
  LD_LIBRARY_PATH=<root>/usr/lib \
  PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 \
  HF_HOME=<hf-cache> CUDA_VISIBLE_DEVICES= HIP_VISIBLE_DEVICES= ROCR_VISIBLE_DEVICES= \
  unshare -rn python3 g2_fixture.py <root> <aren-transliteration-dir> \
    <faster-whisper-tiny-snapshot> <jfk.flac> <scratch-dir>
```

## Host Provider Seam

This seam is pending the lead's confirmation.

The host has `ctranslate2-gfx1151` and `python-ctranslate2-gfx1151` 4.7.2-1
installed from the Strix Halo package repository. Each provides and conflicts
with the generic `ctranslate2` or `python-ctranslate2`. On the host,
`python-faster-whisper` resolves `python-ctranslate2` from that ROCm build.

The Open WebUI cutover installs only `python-faster-whisper` and keeps the
ROCm provider. The generic `ctranslate2` 4.8.2 split package in this
repository is a publication identity for other hosts. It is not installed on
this host, and installing it would replace the ROCm build.

This record's G2 therefore proves the generic CPU combination. The integrated
Open WebUI acceptance's speech-to-text smoke covers the host combination of
Faster Whisper and the ROCm CTranslate2 provider. No separate G2 run against
the host provider is part of this record.

## Known Boundaries

- Importing `ctranslate2` 4.8.2 no longer loads PyTorch or Transformers,
  because upstream made the converter imports lazy. The G2 run loaded neither.
- `python-ctranslate2` no longer depends on `python-setuptools`, because
  upstream removed it from the runtime requirements.
