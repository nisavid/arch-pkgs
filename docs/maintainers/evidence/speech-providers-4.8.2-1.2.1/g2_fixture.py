#!/usr/bin/env python3
"""Offline CPU G2 fixture for the Open WebUI speech provider sublane.

Run it with the candidate archives extracted into one overlay root whose
site-packages and lib directories lead PYTHONPATH and LD_LIBRARY_PATH, inside
a network namespace with only loopback. The script prints one JSON document.
It exits nonzero when any check fails.

Arguments: overlay root, CTranslate2 bundled model dir, Faster Whisper model
dir, JFK audio file, scratch dir.
"""

import json
import os
import re
import shutil
import subprocess
import sys

OVERLAY, CT2_MODEL, FW_MODEL, JFK, SCRATCH = sys.argv[1:6]
result = {"checks": {}}
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


import ctranslate2  # noqa: E402
import faster_whisper  # noqa: E402

result["versions"] = {
    "python": sys.version.split()[0],
    "ctranslate2": ctranslate2.__version__,
    "faster_whisper": faster_whisper.__version__,
}
check(
    "identity",
    ctranslate2.__version__ == "4.8.2"
    and faster_whisper.__version__ == "1.2.1"
    and under_overlay(ctranslate2.__file__)
    and under_overlay(faster_whisper.__file__),
)
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

# Bundled CTranslate2 CPU/OpenBLAS model, with the upstream expected output.
tokens = ["آ", "ت", "ز", "م", "و", "ن"]
expected = ["a", "t", "z", "m", "o", "n"]
outputs = {}
for compute_type in ("float32", "int8"):
    translator = ctranslate2.Translator(CT2_MODEL, device="cpu", compute_type=compute_type)
    outputs[compute_type] = translator.translate_batch([tokens])[0].hypotheses[0]
    del translator
check(
    "ct2_bundled_model",
    all(v == expected for v in outputs.values()),
    outputs={k: " ".join(v) for k, v in outputs.items()},
)

# Malformed models must raise a Python exception, not kill the process.
model_bin = os.path.join(CT2_MODEL, "model.bin")
size = os.path.getsize(model_bin)
with open(model_bin, "rb") as f:
    original = f.read()
variants = {
    "empty": b"",
    "truncated_16_bytes": original[:16],
    "truncated_half": original[: size // 2],
    "oversized_first_length": original[:4] + b"\xff\xff\xff\x7f" + original[8:],
}
probe = (
    "import sys, ctranslate2\n"
    "try:\n"
    "    ctranslate2.Translator(sys.argv[1], device='cpu')\n"
    "except Exception as e:\n"
    "    print(type(e).__name__); sys.exit(0)\n"
    "print('loaded'); sys.exit(3)\n"
)
malformed = {}
for name, payload in variants.items():
    target = os.path.join(SCRATCH, "malformed-" + name)
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(CT2_MODEL, target)
    with open(os.path.join(target, "model.bin"), "wb") as f:
        f.write(payload)
    proc = subprocess.run(
        [sys.executable, "-c", probe, target], capture_output=True, text=True, timeout=120
    )
    malformed[name] = {"returncode": proc.returncode, "raised": proc.stdout.strip()}
check(
    "ct2_malformed_model_fails_without_crash",
    all(v["returncode"] == 0 and v["raised"] for v in malformed.values()),
    variants=malformed,
)

# Faster Whisper CPU int8 transcription and word timestamps.
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
check("fw_int8_with_onnxruntime_cpu_vad", vad.pop("ok"), **{k: vad[k] for k in ("language", "word_count")})

# Every loaded Python module and shared object, for ownership classification.
files = set(mapped_objects())
for mod in list(sys.modules.values()):
    f = getattr(mod, "__file__", None)
    if f:
        files.add(os.path.realpath(f))
result["loaded_files"] = sorted(files)
result["failed"] = failed
print(json.dumps(result))
sys.exit(1 if failed else 0)
