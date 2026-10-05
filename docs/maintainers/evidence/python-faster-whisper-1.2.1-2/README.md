# python-faster-whisper 1.2.1-2 G0-G2 Evidence

This directory holds the candidate evidence for `python-faster-whisper`
1.2.1-2. That release backports upstream
[`2ce7f9d`](https://github.com/SYSTRAN/faster-whisper/commit/2ce7f9d7a9fbe315a5804a33bf7224d42e101174)
so that `decode_audio()` works on PyAV 19
([speech transcription breaks on PyAV 19](https://github.com/nisavid/arch-pkgs/issues/124)).
It replaces the Faster Whisper part of the
[speech providers G0-G2 evidence](../speech-providers-4.8.2-1.2.1/). The
CTranslate2 4.8.2-1 evidence there carries over unchanged.

Lifecycle state: **candidate**. G0 and G1 passed against the archive below.
G2 is pending: it runs under the heavy-work lease, and its result goes into
`g0-g2.json`. Binding the archive into the
[household candidate set](../../open-webui-household-candidate-set.md)
accepts nothing. The sublane stays deferred and publication-ineligible until
[Promote or defer the Open WebUI household stack](https://github.com/nisavid/arch-pkgs/issues/90)
decides.

| Archive | Size | SHA-256 |
| --- | --- | --- |
| `python-faster-whisper-1.2.1-2-any.pkg.tar.zst` | 1088665 | `9d8bdab118453c3a3cfded8a0430a526784e2ee4c9bce5038171f4de3a29f89b` |

The archive was built from merged `main` at
`86549fa8062d792861d27d0f3faf722a733bcaaa`, the squash of
[#125](https://github.com/nisavid/arch-pkgs/pull/125). The package tree is
`042e1f67990f6b834153b58fb8b98bd9329ffe7f`, and the archive's `.BUILDINFO`
`pkgbuild_sha256sum` matches the `PKGBUILD` digest in `g0-g2.json`.

## Files

- `g0-g2.json`: the sources, recipe digests, build toolchain, archive and
  payload identity, and the G2 fixture with its inputs and, once run, its
  results.
- `g2_fixture.py`: the offline G2 harness.

## What G1 checked

The payload differs from 1.2.1-1 only in `faster_whisper/audio.py`, the
`RECORD` line for that file, and the package metadata. The 1.2.1-1
`audio.py`, re-patched with the committed patch, equals the packaged file byte
for byte. `version.py` still declares 1.2.1. The Silero VAD asset
`faster_whisper/assets/silero_vad_v6.onnx` keeps SHA-256
`4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2`.

## What G2 runs

The harness is the Faster Whisper half of the
[speech G2 harness](../speech-providers-4.8.2-1.2.1/g2_fixture.py), with the
same overlay, environment, and transcription checks. The overlay holds the
candidate archive and the two CTranslate2 4.8.2-1 archives. PyAV comes from
the host, so the run tests the archive against the installed PyAV 19. The
harness checks:

- That `ctranslate2` 4.8.2, `libctranslate2.so.4.8.2`, and `faster_whisper`
  1.2.1 load from the candidate archives, and that PyAV 19 loads from the
  host.
- That the patch's `av.open()` keyword gate passes no keywords on PyAV 19.
- The Silero VAD asset digest.
- `decode_audio()` on the JFK clip, which is the call that fails on PyAV 19
  without the patch.
- Faster Whisper `int8` CPU transcription of the JFK clip with word
  timestamps, with and without ONNX Runtime CPU VAD. It uses the pinned
  `Systran/faster-whisper-base` revision that the acceptance kit's
  speech-to-text smoke uses.
- Ownership of what the fixture loaded, as in the speech G2.

A baseline control runs the same harness against an overlay with the
unpatched 1.2.1-1 archive. It passes only if `decode_audio()` raises the
PyAV 19 `TypeError`, which shows that the fixture detects the defect.

To reproduce, extract the archives into `<root>` and run:

```bash
env -i HOME="$HOME" PATH=/usr/bin LANG=C.UTF-8 \
  PYTHONPATH=<root>/usr/lib/python3.14/site-packages \
  LD_LIBRARY_PATH=<root>/usr/lib \
  PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 \
  HF_HOME=<hf-cache> CUDA_VISIBLE_DEVICES= HIP_VISIBLE_DEVICES= ROCR_VISIBLE_DEVICES= \
  unshare -rn python3 g2_fixture.py candidate <root> \
    <faster-whisper-base-snapshot> <jfk.flac>
```

For the baseline control, extract the 1.2.1-1 archive in place of 1.2.1-2
and pass `baseline-control` as the first argument.

## Known Boundaries

- This G2 proves the generic CPU combination, as the earlier record did. The
  host keeps its gfx1151 CTranslate2 provider; see the
  [host provider seam](../speech-providers-4.8.2-1.2.1/README.md#host-provider-seam).
  The household acceptance's speech-to-text smoke covers the host
  combination.
- The patch keeps the PyAV 18 path (`metadata_errors="ignore"`), but this
  record runs only on PyAV 19. G1's byte-for-byte check of the backport is
  the evidence for the PyAV 18 branch.
