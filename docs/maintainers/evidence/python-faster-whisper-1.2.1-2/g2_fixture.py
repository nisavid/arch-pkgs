#!/usr/bin/env python3
"""Offline CPU G2 fixture for python-faster-whisper 1.2.1-2 on PyAV 19.

This is the Faster Whisper half of the speech G2 harness in
../speech-providers-4.8.2-1.2.1/g2_fixture.py. Its overlay, environment, and
transcription checks are the same. The CTranslate2 bundled-model and
malformed-model checks are dropped, because the CTranslate2 4.8.2-1 evidence
carries over unchanged. It adds the PyAV identity, the av.open() keyword gate
that the 1.2.1-2 patch introduces, the Silero VAD asset digest, and a direct
decode_audio() call on the JFK clip.

Run it with the candidate archives extracted into one overlay root whose
site-packages and lib directories lead PYTHONPATH and LD_LIBRARY_PATH, inside
a network namespace with only loopback. The script prints one JSON document.
It exits nonzero when any check fails.

Arguments: mode, overlay root, Faster Whisper model dir, JFK audio file.

- mode "candidate": the full fixture, for an overlay holding 1.2.1-2.
- mode "baseline-control": for an overlay holding the unpatched 1.2.1-1. It
  passes only when decode_audio() raises the PyAV 19 TypeError, which shows
  that the fixture detects the defect that 1.2.1-2 fixes.
"""

import hashlib
import json
import os
import re
import sys

MODE, OVERLAY, FW_MODEL, JFK = sys.argv[1:5]
if MODE not in ("candidate", "baseline-control"):
    raise SystemExit(f"unknown mode {MODE!r}")

EXPECTED = {"ctranslate2": "4.8.2", "faster_whisper": "1.2.1", "av_major": 19}
SILERO_VAD_V6_SHA256 = "4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2"
result = {"mode": MODE, "checks": {}}
failed = []


def check(name, ok, **detail):
    result["checks"][name] = {"pass": bool(ok), **detail}
    if not ok:
        failed.append(name)


def under_overlay(path):
    return os.path.realpath(path).startswith(os.path.realpath(OVERLAY) + os.sep)


def mapped_objects():
    paths = set()
    with open("/proc/self/maps") as maps:
        for line in maps:
            parts = line.split(None, 5)
            if len(parts) == 6 and parts[5].startswith("/"):
                paths.add(parts[5].strip())
    return paths


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finish():
    files = set(mapped_objects())
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if f:
            files.add(os.path.realpath(f))
    result["loaded_files"] = sorted(files)
    result["failed"] = failed
    print(json.dumps(result))
    sys.exit(1 if failed else 0)


import av  # noqa: E402
import ctranslate2  # noqa: E402
import faster_whisper  # noqa: E402
import faster_whisper.audio  # noqa: E402
from faster_whisper.audio import decode_audio  # noqa: E402

result["versions"] = {
    "python": sys.version.split()[0],
    "av": av.__version__,
    "ctranslate2": ctranslate2.__version__,
    "faster_whisper": faster_whisper.__version__,
}
check(
    "identity",
    ctranslate2.__version__ == EXPECTED["ctranslate2"]
    and faster_whisper.__version__ == EXPECTED["faster_whisper"]
    and under_overlay(ctranslate2.__file__)
    and under_overlay(faster_whisper.__file__),
)
# PyAV is the host's: the fixture tests the archive against the installed
# PyAV, so av must come from outside the overlay.
check(
    "pyav_from_host",
    int(av.__version__.split(".")[0]) == EXPECTED["av_major"] and not under_overlay(av.__file__),
    version=av.__version__,
)
gate = getattr(faster_whisper.audio, "_AV_OPEN_KWARGS", None)

if MODE == "baseline-control":
    check("baseline_has_no_av_open_gate", gate is None)
    try:
        decode_audio(JFK, sampling_rate=16000)
    except TypeError as error:
        check(
            "baseline_decode_audio_raises_pyav19_typeerror",
            "metadata_errors" in str(error),
            raised="TypeError",
            message=str(error),
        )
    except Exception as error:  # noqa: BLE001
        check(
            "baseline_decode_audio_raises_pyav19_typeerror",
            False,
            raised=type(error).__name__,
            message=str(error),
        )
    else:
        check("baseline_decode_audio_raises_pyav19_typeerror", False, raised=None)
    finish()

libct2 = sorted(p for p in mapped_objects() if "libctranslate2.so" in p)
check(
    "libctranslate2_from_candidate",
    len(libct2) == 1 and under_overlay(libct2[0]),
    mapped=[os.path.relpath(p, OVERLAY) if under_overlay(p) else "outside-overlay" for p in libct2],
)
cpu_types = sorted(ctranslate2.get_supported_compute_types("cpu"))
check(
    "cpu_only",
    ctranslate2.get_cuda_device_count() == 0 and "int8" in cpu_types,
    cuda_device_count=ctranslate2.get_cuda_device_count(),
    cpu_compute_types=cpu_types,
)
# On PyAV 19 the 1.2.1-2 gate passes no metadata_errors keyword.
check("av_open_gate_passes_no_keywords_on_pyav19", gate == {}, av_open_kwargs=gate)
silero = os.path.join(os.path.dirname(faster_whisper.__file__), "assets", "silero_vad_v6.onnx")
silero_sha256 = sha256_file(silero)
check(
    "silero_vad_v6_asset",
    under_overlay(silero) and silero_sha256 == SILERO_VAD_V6_SHA256,
    sha256=silero_sha256,
)

# decode_audio() is the function that calls av.open().
try:
    samples = decode_audio(JFK, sampling_rate=16000)
except Exception as error:  # noqa: BLE001
    check("decode_audio_jfk", False, raised=type(error).__name__, message=str(error))
else:
    seconds = len(samples) / 16000
    check(
        "decode_audio_jfk",
        str(samples.dtype) == "float32" and samples.ndim == 1 and 10.5 <= seconds <= 11.5,
        dtype=str(samples.dtype),
        samples=int(len(samples)),
        seconds=round(seconds, 3),
    )

# Faster Whisper CPU int8 transcription and word timestamps, as in the
# speech G2 harness.
from faster_whisper import WhisperModel  # noqa: E402

model = WhisperModel(FW_MODEL, device="cpu", compute_type="int8", cpu_threads=4)


def transcribe(**kwargs):
    segments, info = model.transcribe(JFK, word_timestamps=True, **kwargs)
    segments = list(segments)
    words = [w for s in segments for w in s.words]
    text = " ".join(s.text.strip() for s in segments)
    norm = re.sub(r"[^a-z ]", "", text.lower())
    ordered = all(w.start <= w.end for w in words) and all(
        a.start <= b.start for a, b in zip(words, words[1:])
    )
    in_range = all(0.0 <= w.start and w.end <= info.duration + 0.5 for w in words)
    return {
        "language": info.language,
        "duration": round(info.duration, 3),
        "text": text,
        "word_count": len(words),
        "first_word": [words[0].word.strip(), round(words[0].start, 2), round(words[0].end, 2)] if words else None,
        "last_word": [words[-1].word.strip(), round(words[-1].end, 2)] if words else None,
        "ok": info.language == "en"
        and "ask not what your country can do for you" in norm
        and "ask what you can do for your country" in norm
        and len(words) >= 20
        and ordered
        and in_range,
    }


plain = transcribe()
vad = transcribe(vad_filter=True)
check("fw_int8_transcription_word_timestamps", plain.pop("ok"), **plain)
check(
    "fw_int8_with_onnxruntime_cpu_vad",
    vad.pop("ok"),
    **{k: vad[k] for k in ("language", "word_count", "text")},
)
finish()
