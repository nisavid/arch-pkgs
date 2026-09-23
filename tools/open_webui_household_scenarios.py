#!/usr/bin/env python3
"""Open WebUI household scenarios shared by the acceptance trial and re-smoke.

The four ``open-webui.resmoke.*`` scenarios are the same functions the single
acceptance trial runs, and the ones arch-strix-halo-pkgs reruns after a later
Lemonade redeploy.  ``configure`` is the admin connection helper shared by the
acceptance environment and the production install.

This module uses only the Python standard library so that it runs with
``/usr/bin/python3`` and nothing else.  It never loads, unloads, pins, pulls,
restarts, or reconfigures Lemonade: its only Lemonade requests are
``GET /api/v1/health``, ``GET /api/v1/models``, and inference.

Exit codes: 0 all pass, 1 a failure, 3 escalate (zembed canary), 75 a
precondition is not met.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import http.client
import json
import math
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import measure_open_webui_household as v1  # noqa: E402

RECEIPT_SCHEMA = "open-webui-household-resmoke/v1"

# Frozen.  A behavior change gets a new id and a schema bump, never a
# rewritten id.  The group runs in this order.
SCENARIO_IDS: tuple[str, ...] = (
    "open-webui.resmoke.zembed-canary",
    "open-webui.resmoke.zerank-qualification",
    "open-webui.resmoke.cited-answer",
    "open-webui.resmoke.stt",
)

TARGETS = ("acceptance", "production")

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ESCALATE = 3
EXIT_PRECONDITION = 75

PASS = "PASS"
FAIL = "FAIL"
ESCALATE = "ESCALATE"
BLOCKED = "BLOCKED"
RESULT_EXIT_CODES = MappingProxyType(
    {PASS: EXIT_PASS, FAIL: EXIT_FAIL, ESCALATE: EXIT_ESCALATE, BLOCKED: EXIT_PRECONDITION}
)

DEFAULT_LEMOND_URL = "http://127.0.0.1:13305"
DEFAULT_WHISPER_MODEL = "base"
# The owner's Lemonade config pins this chat model.  The fork's listing
# surfaces may emit the bare name of the precedence winner, and bare names
# resolve as input, so every readiness check compares ids through
# ``bare_model_id``.
DEFAULT_CHAT_MODEL = "user.Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL"
DEFAULT_ACCEPTANCE_ORIGIN = "https://localhost:18443"
ACCEPTANCE_UNIT = "owui-acc-open-webui.service"
PRODUCTION_UNIT = "open-webui.service"
NEEDS_OWNER_RESTART = "NEEDS OWNER: sudo systemctl restart open-webui.service"

# The only /proc/<pid>/environ keys this kit ever keeps.  The packaged wrapper
# exports secrets (WEBUI_SECRET_KEY, REDIS_URL, QDRANT_API_KEY, ...) into the
# same environ, so every read filters in memory and the raw block is dropped.
ENVIRON_ALLOWLIST: frozenset[str] = frozenset(
    {
        "ANONYMIZED_TELEMETRY",
        "DO_NOT_TRACK",
        "SCARF_NO_ANALYTICS",
        "ENABLE_VERSION_UPDATE_CHECK",
        "OFFLINE_MODE",
        "HF_HUB_OFFLINE",
        "WHISPER_MODEL",
        "RAG_EMBEDDING_MODEL",
        "RAG_EMBEDDING_QUERY_PREFIX",
        "RAG_EMBEDDING_CONTENT_PREFIX",
        "RAG_RERANKING_MODEL",
    }
)
TELEMETRY_EXPECTED = MappingProxyType(
    {
        "ANONYMIZED_TELEMETRY": "false",
        "DO_NOT_TRACK": "true",
        "SCARF_NO_ANALYTICS": "true",
        "ENABLE_VERSION_UPDATE_CHECK": "false",
        "OFFLINE_MODE": "true",
    }
)

ZEMBED_QUERY_HEAD = "<|im_start|>system\nquery<|im_end|>\n<|im_start|>user\n"
ZEMBED_DOCUMENT_HEAD = "<|im_start|>system\ndocument<|im_end|>\n<|im_start|>user\n"

# Expected production settings, keyed by the promoted open-webui package
# version and bound to its archive SHA-256.  The installed env is root-only,
# so production re-smoke uses these frozen values instead of reading it.
#
# Entries come only from the candidate of record: the acceptance trial prints
# the entry for the open-webui archive it deployed (and records it in the
# evidence as ``production_expectation``), and the evidence commit adds it
# here.  A consistency test ties every entry to committed acceptance
# evidence.  Until that evidence exists this map is empty, so production S6
# exits 75 instead of passing against bytes that are not of record.
PRODUCTION_EXPECTATION_KEYS = (
    "RAG_EMBEDDING_MODEL",
    "RAG_RERANKING_MODEL",
    "RAG_EMBEDDING_QUERY_PREFIX",
    "RAG_EMBEDDING_CONTENT_PREFIX",
)
PRODUCTION_EXPECTATIONS: Mapping[str, Mapping[str, str]] = MappingProxyType({})

# Whisper snapshots, pinned by Hugging Face revision (the model repository's
# source commit) and the SHA-256 of every file faster-whisper loads.  Only
# these files are placed, and ``HF_HUB_OFFLINE=1`` keeps a load failure from
# reaching the network.
#
# base is the owner's choice for acceptance and production.  Its revision and
# model.bin digest come from the Hugging Face API
# (``/api/models/Systran/faster-whisper-base``, LFS metadata), and the other
# digests from the files at that revision, resolved read-only on 2026-09-23.
WHISPER_BASE = MappingProxyType(
    {
        "repository": "Systran/faster-whisper-base",
        "revision": "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
        "files": MappingProxyType(
            {
                "config.json": "56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a",
                "model.bin": "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9",
                "tokenizer.json": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
                "vocabulary.txt": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
            }
        ),
    }
)
# tiny stays available only as an explicit, non-default ``--whisper-model``.
# Its revision and model.bin digest are ported from "feat(ctranslate2): update
# to 4.8.2 with speech G0-G2 evidence"
# (https://github.com/nisavid/arch-pkgs/pull/92), commit
# e12fdd98251a01cdc99f22a5a113741b2473b107; the other digests were resolved
# at that revision like base's.
WHISPER_TINY = MappingProxyType(
    {
        "repository": "Systran/faster-whisper-tiny",
        "revision": "d90ca5fe260221311c53c58e660288d3deb8d356",
        "files": MappingProxyType(
            {
                "config.json": "a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8",
                "model.bin": "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1",
                "tokenizer.json": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
                "vocabulary.txt": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
            }
        ),
    }
)
WHISPER_PINS: Mapping[str, Mapping[str, Any]] = MappingProxyType({"base": WHISPER_BASE, "tiny": WHISPER_TINY})


def whisper_pin_record(model: str) -> dict[str, Any]:
    """One Whisper pin as plain JSON-ready data, for evidence and receipts."""

    pin = WHISPER_PINS[model]
    return {"repository": pin["repository"], "revision": pin["revision"], "files": dict(pin["files"])}


JFK_FLAC_SHA256 = "63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715"
JFK_PHRASES = (
    "ask not what your country can do for you",
    "ask what you can do for your country",
)
JFK_MINIMUM_WORDS = 20
SPEECH_PROVIDER_PACKAGE = "python-ctranslate2-gfx1151"

# zembed canary texts, recorded in every receipt.
CANARY_QUERY = "Which key opens the seed cabinet?"
CANARY_RELEVANT = "The brass key opens the seed cabinet."
CANARY_UNRELATED = "Bananas ripen faster in a closed paper bag."
STORED_VECTOR_MINIMUM_COSINE = 0.999

# The fixture handbook and its fact come from the v1 fixture generator.
HANDBOOK_NAME = "winter-garden-handbook.md"
CANONICAL_FACT = "The brass key opens the seed cabinet."
CANONICAL_QUERY = "Which key opens the seed cabinet?"
CANONICAL_CITATION = "Winter Garden Handbook § 3"
CITED_ANSWER_PROMPT = (
    "Using only the attached handbook, quote verbatim the one sentence that "
    "says which key opens the seed cabinet. Reply with that sentence only."
)

# Open WebUI 0.11 routes.  The stub rehearsal fixes any shape mismatch here.
API = MappingProxyType(
    {
        "signin": "/api/v1/auths/signin",
        "ready": "/ready",
        "rag_health": "/api/v1/retrieval/health",
        "rag_config": "/api/v1/retrieval/config",
        "rag_config_update": "/api/v1/retrieval/config/update",
        "files": "/api/v1/files/",
        "file": "/api/v1/files/{id}",
        "file_status": "/api/v1/files/{id}/process/status",
        "chat": "/api/chat/completions",
        "models": "/api/models",
        "transcriptions": "/api/v1/audio/transcriptions",
        "ollama_config": "/ollama/config",
        "ollama_config_update": "/ollama/config/update",
        "openai_config": "/openai/config",
        "openai_config_update": "/openai/config/update",
        "audio_config": "/api/v1/audio/config",
        "audio_config_update": "/api/v1/audio/config/update",
        "models_config": "/api/v1/configs/models",
    }
)

# Lemonade routes.  Deliberately no load, unload, pull, pin, or delete route.
LEMOND_API = MappingProxyType(
    {
        "health": "/api/v1/health",
        "models": "/api/v1/models",
        "embeddings": "/api/v1/embeddings",
        "rerank": "/api/v1/rerank",
    }
)

TEMPLATES = REPO_ROOT / "tools" / "templates" / "open-webui-household"
PACKAGED_ENV = REPO_ROOT / "packages" / "open-webui" / "open-webui.env"
RAG_GATE = REPO_ROOT / "packages" / "open-webui" / "open-webui-rag-gate.py"

# Keys the acceptance overlay may set, beyond the packaged state-path keys.
OVERLAY_FIXED_KEYS: frozenset[str] = frozenset(
    {"QDRANT_URI", "RAG_EXTERNAL_RERANKER_URL"}
)
CONNECTION_SEED_KEYS: frozenset[str] = frozenset(
    {"ENABLE_OLLAMA_API", "OPENAI_API_BASE_URLS", "OPENAI_API_KEYS"}
)
REHEARSAL_ONLY_KEYS: frozenset[str] = frozenset({"RAG_OPENAI_API_BASE_URL"})
PACKAGED_STATE_ROOT = "/var/lib/open-webui"


class Blocked(RuntimeError):
    """A precondition is not met; the run exits 75."""


class ScenarioFailure(RuntimeError):
    """The scenario ran and its pass condition does not hold."""


class Escalation(RuntimeError):
    """The zembed canary failed; the run stops and escalates to the lead."""


# ---------------------------------------------------------------------------
# Pure helpers


def aggregate_exit_code(results: Sequence[str]) -> int:
    """Return the run's exit code from its ordered scenario results."""

    for result in results:
        if result not in RESULT_EXIT_CODES:
            raise ValueError(f"unknown scenario result: {result}")
    for result in (ESCALATE, BLOCKED, FAIL):
        if result in results:
            return RESULT_EXIT_CODES[result]
    return EXIT_PASS


def select_scenarios(requested: Sequence[str]) -> tuple[str, ...]:
    """Return the requested ids in registry order; ``all`` selects every id."""

    if not requested or "all" in requested:
        return SCENARIO_IDS
    unknown = sorted(set(requested) - set(SCENARIO_IDS))
    if unknown:
        raise ValueError(f"unknown scenario id: {', '.join(unknown)}")
    return tuple(item for item in SCENARIO_IDS if item in requested)


def filter_environ(raw: bytes) -> dict[str, str]:
    """Keep only allowlisted keys from a NUL-separated environ block."""

    kept: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        name, separator, value = entry.partition(b"=")
        if not separator:
            continue
        key = name.decode("ascii", "replace")
        if key in ENVIRON_ALLOWLIST:
            kept[key] = value.decode("utf-8", "replace")
    return kept


def read_process_environ(pid: int) -> dict[str, str]:
    """Read ``/proc/<pid>/environ`` and return only the allowlisted keys."""

    with open(f"/proc/{int(pid)}/environ", "rb") as source:
        return filter_environ(source.read())


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must be nonempty and the same length")
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    if norm == 0:
        raise ValueError("zero vector")
    return dot / norm


def normalize_words(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", text.lower())).strip()


def transcription_passes(text: str, language: str | None) -> bool:
    norm = normalize_words(text)
    return (
        (language is None or language == "en")
        and all(phrase in norm for phrase in JFK_PHRASES)
        and len(norm.split()) >= JFK_MINIMUM_WORDS
    )


def loaded_model_names(health: Any) -> set[str]:
    """Return the model names Lemonade reports as loaded."""

    names: set[str] = set()
    if not isinstance(health, dict):
        return names
    for item in health.get("all_models_loaded") or []:
        if isinstance(item, dict) and isinstance(item.get("model_name"), str):
            names.add(item["model_name"])
    if isinstance(health.get("model_loaded"), str):
        names.add(health["model_loaded"])
    return names


def bare_model_id(model_id: str) -> str:
    """Strip one leading ``user.`` so a canonical id and its bare name compare equal."""

    return model_id.removeprefix("user.")


def listed_model_id(listed: Iterable[str], wanted: str) -> str | None:
    """The listed id that names ``wanted``: the exact id first, else its bare-name match."""

    ids = set(listed)
    if wanted in ids:
        return wanted
    matches = sorted(item for item in ids if bare_model_id(item) == bare_model_id(wanted))
    return matches[0] if matches else None


def served_model_ids(models: Any) -> set[str]:
    data = models.get("data") if isinstance(models, dict) else None
    return {
        item["id"]
        for item in data or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def require_models_ready(models: Any, health: Any, model_ids: Sequence[str]) -> None:
    """Refuse (exit 75) unless every id is served and already loaded.

    The kit never triggers a load on the shared Lemonade, so a model that is
    served but not resident is a precondition failure, not something to fix.
    """

    served = {bare_model_id(item) for item in served_model_ids(models)}
    missing = [item for item in model_ids if bare_model_id(item) not in served]
    if missing:
        raise Blocked(f"NEEDS LEAD: Lemonade does not serve {', '.join(missing)}")
    loaded = {bare_model_id(item) for item in loaded_model_names(health)}
    unloaded = [item for item in model_ids if bare_model_id(item) not in loaded]
    if unloaded:
        raise Blocked(f"NEEDS LEAD: Lemonade has not loaded {', '.join(unloaded)}")


def validate_rerank_results(results: Any, document_count: int) -> list[float]:
    """Return one finite score per document index, or raise ScenarioFailure."""

    if not isinstance(results, list) or len(results) != document_count:
        raise ScenarioFailure("rerank did not return one result per document")
    scores: dict[int, float] = {}
    for item in results:
        index = item.get("index") if isinstance(item, dict) else None
        score = item.get("relevance_score") if isinstance(item, dict) else None
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < document_count
            or index in scores
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise ScenarioFailure("rerank returned a malformed or non-finite result")
        scores[index] = float(score)
    return [scores[index] for index in range(document_count)]


def parse_chat_response(body: bytes, content_type: str) -> tuple[str, list[dict[str, Any]]]:
    """Return the answer text and sources from a streamed or plain chat reply."""

    text_parts: list[str] = []
    sources: list[dict[str, Any]] = []

    def absorb(event: Any) -> None:
        if not isinstance(event, dict):
            return
        for source in event.get("sources") or []:
            if isinstance(source, dict):
                sources.append(source)
        for choice in event.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            for part in (choice.get("delta"), choice.get("message")):
                if isinstance(part, dict) and isinstance(part.get("content"), str):
                    text_parts.append(part["content"])

    if "text/event-stream" in content_type:
        for line in body.decode("utf-8", "replace").splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:") :].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                absorb(json.loads(payload))
            except json.JSONDecodeError:
                continue
    else:
        absorb(json.loads(body))
    return "".join(text_parts), sources


def summarize_sources(sources: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Collapse chat sources to distinct documents with their scores."""

    documents: dict[str, dict[str, Any]] = {}
    for source in sources:
        described = source.get("source")
        if not isinstance(described, dict):
            described = {}
        key = str(described.get("id") or described.get("name") or "")
        entry = documents.setdefault(key, {"name": described.get("name"), "scores": []})
        for score in source.get("distances") or []:
            entry["scores"].append(score)
    return {
        "count": len(documents),
        "names": [entry["name"] for entry in documents.values()],
        "scores": [score for entry in documents.values() for score in entry["scores"]],
    }


def cited_answer_passes(text: str, summary: Mapping[str, Any], expected_name: str) -> bool:
    scores = summary["scores"]
    return (
        CANONICAL_FACT in text
        and summary["count"] == 1
        and summary["names"] == [expected_name]
        and bool(scores)
        and all(
            not isinstance(score, bool)
            and isinstance(score, (int, float))
            and math.isfinite(score)
            for score in scores
        )
    )


def handbook_bytes() -> bytes:
    """The fixture handbook from the v1 fixture generator."""

    for name, data in v1._small_fixture_files():
        if name == f"documents/{HANDBOOK_NAME}":
            return data
    raise RuntimeError("the v1 fixture no longer contains the handbook")


def provider_restart_needed(active_enter_epoch: float | None, install_epoch: float | None) -> bool:
    """True when Open WebUI started before the speech provider was installed."""

    if active_enter_epoch is None:
        return True
    if install_epoch is None:
        return False
    return active_enter_epoch <= install_epoch


# ---------------------------------------------------------------------------
# Templates and the acceptance overlay


_TEMPLATE_TOKEN = re.compile(r"@([A-Z][A-Z0-9_]*)@")


def render_template(name: str, values: Mapping[str, str]) -> str:
    """Render ``tools/templates/open-webui-household/<name>`` exactly.

    Every ``@TOKEN@`` must have a value and every value must be used.
    """

    text = (TEMPLATES / name).read_text(encoding="utf-8")
    tokens = set(_TEMPLATE_TOKEN.findall(text))
    missing = tokens - set(values)
    extra = set(values) - tokens
    if missing or extra:
        raise ValueError(
            f"template {name}: missing {sorted(missing)}, unexpected {sorted(extra)}"
        )
    for key, value in values.items():
        if "\n" in value and key not in {"GLOBAL_OPTIONS"}:
            raise ValueError(f"template {name}: {key} must be a single line")
    return _TEMPLATE_TOKEN.sub(lambda match: values[match.group(1)], text)


def acceptance_caddy_global_options(root: Path) -> str:
    return (
        "{\n"
        "\tadmin off\n"
        "\tauto_https disable_redirects\n"
        "\tskip_install_trust\n"
        "\tdefault_bind 127.0.0.1\n"
        f"\tstorage file_system {root}/state/caddy\n"
        "}\n"
    )


def render_acceptance_caddyfile(root: Path, socket_path: Path, port: int = 18443) -> str:
    return render_template(
        "open-webui.caddy.in",
        {
            "GLOBAL_OPTIONS": acceptance_caddy_global_options(root),
            "SITE_ADDRESS": f"https://localhost:{port}",
            "BIND": "127.0.0.1",
            "TLS": "internal",
            "SOCKET": str(socket_path),
        },
    )


def acceptance_caddy_root_certificate(root: Path) -> Path:
    return root / "state" / "caddy" / "pki" / "authorities" / "local" / "root.crt"


def valkey_password_hash(password: str) -> str:
    if not password:
        raise ValueError("the Valkey password must be nonempty")
    return hashlib.sha256(password.encode()).hexdigest()


def render_valkey_config(port: int, acl_file: Path, directory: Path) -> str:
    return render_template(
        "valkey-open-webui.conf.in",
        {"PORT": str(int(port)), "ACL_FILE": str(acl_file), "DIR": str(directory)},
    )


def render_valkey_acl(password_sha256: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", password_sha256):
        raise ValueError("the ACL takes the password's lowercase SHA-256, never the password")
    return render_template("valkey-open-webui.acl.in", {"PASSWORD_SHA256": password_sha256})


def connection_seed(lemond_url: str = DEFAULT_LEMOND_URL) -> dict[str, str]:
    """The credential-free, Lemonade-only chat connection seed for one provider origin.

    The packaged ``open-webui.env`` carries this seed for the default origin
    from 0.11.0-5 on, so the acceptance overlay sets only the keys whose
    packaged value differs (the rehearsal stub origin, or an older package).
    """

    return {
        "ENABLE_OLLAMA_API": "false",
        "OPENAI_API_BASE_URLS": lemond_url.rstrip("/") + "/api/v1",
        "OPENAI_API_KEYS": "",
    }


def speech_environment(whisper_model: str = DEFAULT_WHISPER_MODEL) -> dict[str, str]:
    """Local Whisper settings (ruling 11), set as unit ``Environment=`` lines.

    They are not part of the connection seed: ``HF_HUB_OFFLINE=1`` keeps a
    Whisper load failure from falling back to the network.  The acceptance
    unit and the production drop-in carry the same two values.
    """

    return {"WHISPER_MODEL": whisper_model, "HF_HUB_OFFLINE": "1"}


def parse_env_file(text: str) -> dict[str, str]:
    """Parse a systemd EnvironmentFile, including double-quoted multi-line values."""

    values: dict[str, str] = {}
    lines = iter(text.splitlines())
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if value.startswith('"'):
            value = value[1:]
            while not value.endswith('"'):
                value += "\n" + next(lines)
            value = value[:-1]
        values[key] = value
    return values


def packaged_state_path_keys(packaged_env: Mapping[str, str]) -> frozenset[str]:
    return frozenset(
        key
        for key, value in packaged_env.items()
        if PACKAGED_STATE_ROOT in value
    )


def overlay_allowlist(packaged_env: Mapping[str, str], *, rehearsal: bool) -> frozenset[str]:
    allowed = packaged_state_path_keys(packaged_env) | OVERLAY_FIXED_KEYS | CONNECTION_SEED_KEYS
    return allowed | REHEARSAL_ONLY_KEYS if rehearsal else allowed


def acceptance_overlay(
    packaged_env: Mapping[str, str],
    root: Path,
    *,
    lemond_url: str = DEFAULT_LEMOND_URL,
    qdrant_port: int = 16333,
    relay_port: int = 13306,
    rehearsal: bool = False,
) -> dict[str, str]:
    """The acceptance overlay; the only deviation from the packaged env bytes."""

    state = str(root / "state" / "open-webui")
    overlay = {
        key: packaged_env[key].replace(PACKAGED_STATE_ROOT, state)
        for key in sorted(packaged_state_path_keys(packaged_env))
    }
    overlay["QDRANT_URI"] = f"http://127.0.0.1:{int(qdrant_port)}"
    overlay["RAG_EXTERNAL_RERANKER_URL"] = f"http://127.0.0.1:{int(relay_port)}/api/v1/rerank"
    overlay.update(
        (key, value)
        for key, value in connection_seed(lemond_url).items()
        if packaged_env.get(key) != value
    )
    if rehearsal:
        overlay["RAG_OPENAI_API_BASE_URL"] = lemond_url.rstrip("/") + "/api/v1"
    extra = set(overlay) - overlay_allowlist(packaged_env, rehearsal=rehearsal)
    if extra:
        raise ValueError(f"overlay keys outside the allowlist: {sorted(extra)}")
    return overlay


def render_overlay(overlay: Mapping[str, str]) -> str:
    for key, value in overlay.items():
        if "\n" in value or '"' in value:
            raise ValueError(f"overlay value for {key} must be a plain single line")
    return "".join(f"{key}={overlay[key]}\n" for key in sorted(overlay))


# ---------------------------------------------------------------------------
# Transport


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = str(socket_path)

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


@dataclasses.dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


class Endpoint:
    """HTTP to Open WebUI over an HTTPS origin or a UNIX socket, or to Lemonade."""

    def __init__(
        self,
        *,
        origin: str | None = None,
        socket_path: Path | None = None,
        cacert: Path | None = None,
        timeout: float = 120.0,
    ):
        if (origin is None) == (socket_path is None):
            raise ValueError("give exactly one of origin or socket_path")
        self.socket_path = socket_path
        self.timeout = timeout
        self.base_path = ""
        if origin is not None:
            parsed = urllib.parse.urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("origin must be an http or https URL")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("origin must not carry credentials, a query, or a fragment")
            self.scheme = parsed.scheme
            self.host = parsed.hostname
            self.port = parsed.port
            self.base_path = parsed.path.rstrip("/")
            self.context = (
                ssl.create_default_context(cafile=str(cacert) if cacert else None)
                if parsed.scheme == "https"
                else None
            )

    def _connection(self) -> http.client.HTTPConnection:
        if self.socket_path is not None:
            return _UnixHTTPConnection(self.socket_path, self.timeout)
        if self.scheme == "https":
            return http.client.HTTPSConnection(
                self.host, self.port, timeout=self.timeout, context=self.context
            )
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any = None,
        body: bytes | None = None,
        content_type: str | None = None,
        token: str | None = None,
    ) -> Response:
        headers = {"Accept": "application/json, text/event-stream"}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        connection = self._connection()
        try:
            connection.request(method, self.base_path + path, body=body, headers=headers)
            response = connection.getresponse()
            return Response(response.status, response.getheader("Content-Type", ""), response.read())
        finally:
            connection.close()

    def json(self, method: str, path: str, payload: Any = None, *, token: str | None = None, expected: tuple[int, ...] = (200,)) -> Any:
        response = self.request(method, path, payload=payload, token=token)
        if response.status not in expected:
            raise ScenarioFailure(f"{method} {path} returned HTTP {response.status}")
        return response.json()


def multipart_file(field: str, filename: str, data: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = "owui-household-" + uuid.uuid4().hex
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            data,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    return body, f"multipart/form-data; boundary={boundary}"


def signin(endpoint: Endpoint, email: str, password: str) -> str:
    session = endpoint.json("POST", API["signin"], {"email": email, "password": password})
    if not isinstance(session, dict) or not isinstance(session.get("token"), str):
        raise Blocked("Open WebUI sign-in did not return a token")
    return session["token"]


def credential(name: str, directory: Path | None = None) -> str:
    """Read one systemd credential; the value is never printed or recorded."""

    base = directory or (Path(os.environ["CREDENTIALS_DIRECTORY"]) if os.environ.get("CREDENTIALS_DIRECTORY") else None)
    if base is None:
        raise Blocked("the systemd credential directory is unavailable")
    try:
        value = (base / name).read_text(encoding="utf-8").rstrip("\n")
    except OSError as error:
        raise Blocked(f"required credential is unavailable: {name}") from error
    if not value:
        raise Blocked(f"required credential is empty: {name}")
    return value


# ---------------------------------------------------------------------------
# Effective settings


@dataclasses.dataclass(frozen=True)
class Settings:
    embedding_model: str
    reranking_model: str
    query_prefix: str
    content_prefix: str
    source: str
    archive_sha256: str | None = None
    archive_verified: bool = False
    environ: Mapping[str, str] = dataclasses.field(default_factory=dict)


def _systemctl_show(unit: str, prop: str, *, user: bool) -> str:
    command = ["systemctl"] + (["--user"] if user else []) + ["show", "-p", prop, "--value", unit]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


OPEN_WEBUI_COMMAND = b"from open_webui import app"


def open_webui_pid(
    unit: str = ACCEPTANCE_UNIT,
    *,
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    proc_root: Path = Path("/proc"),
) -> int:
    """Find the Open WebUI Python process in the unit's cgroup.

    The unit's main process may be bwrap, which forks, stays as the parent,
    and carries the same unit environment.  The Python process is the one
    whose command line runs the packaged wrapper's ``from open_webui import
    app``; exactly one must match.
    """

    cgroup = _systemctl_show(unit, "ControlGroup", user=True)
    if not cgroup:
        raise Blocked(f"{unit} is not running")
    try:
        procs = (cgroup_root / cgroup.lstrip("/") / "cgroup.procs").read_text().split()
    except OSError as error:
        raise Blocked(f"{unit} has no readable cgroup") from error
    matches = []
    for line in procs:
        try:
            command = (proc_root / line / "cmdline").read_bytes()
        except OSError:
            continue
        if OPEN_WEBUI_COMMAND in command:
            matches.append(int(line))
    if len(matches) != 1:
        raise Blocked(f"expected one Open WebUI process in {unit}, found {len(matches)}")
    return matches[0]


def settings_from_environ(environ: Mapping[str, str]) -> Settings:
    required = (
        "RAG_EMBEDDING_MODEL",
        "RAG_RERANKING_MODEL",
        "RAG_EMBEDDING_QUERY_PREFIX",
        "RAG_EMBEDDING_CONTENT_PREFIX",
    )
    missing = [key for key in required if key not in environ]
    if missing:
        raise Blocked(f"the Open WebUI process environ lacks {', '.join(missing)}")
    return Settings(
        embedding_model=environ["RAG_EMBEDDING_MODEL"],
        reranking_model=environ["RAG_RERANKING_MODEL"],
        query_prefix=environ["RAG_EMBEDDING_QUERY_PREFIX"],
        content_prefix=environ["RAG_EMBEDDING_CONTENT_PREFIX"],
        source="process-environ",
        environ=dict(environ),
    )


def installed_open_webui_version() -> str:
    result = subprocess.run(["pacman", "-Q", "open-webui"], capture_output=True, text=True)
    if result.returncode != 0:
        raise Blocked("open-webui is not installed")
    return result.stdout.split()[1]


_OPEN_WEBUI_ARCHIVE = re.compile(r"^open-webui-(?P<version>[^-]+-[^-]+)-x86_64\.pkg\.tar\.zst$")


def production_expectation(archive: str, archive_sha256: str, packaged_env: Mapping[str, str]) -> dict[str, Any]:
    """The ``PRODUCTION_EXPECTATIONS`` entry for one deployed open-webui archive.

    The trial derives it from the candidate of record it deployed; the
    evidence commit pastes it into this module.
    """

    match = _OPEN_WEBUI_ARCHIVE.match(archive)
    if match is None or not re.fullmatch(r"[0-9a-f]{64}", archive_sha256):
        raise ValueError(f"not an open-webui archive record: {archive}")
    entry = {"archive": archive, "archive_sha256": archive_sha256}
    entry.update({key: packaged_env[key] for key in PRODUCTION_EXPECTATION_KEYS})
    return {"version": match.group("version"), "entry": entry}


def settings_for_production(version: str, cache_dir: Path = Path("/var/cache/pacman/pkg")) -> Settings:
    expected = PRODUCTION_EXPECTATIONS.get(version)
    if expected is None:
        raise Blocked(f"NEEDS LEAD: no frozen settings for open-webui {version}")
    cached = cache_dir / expected["archive"]
    verified = False
    if cached.is_file():
        if v1._file_sha256(cached) != expected["archive_sha256"]:
            raise Blocked("the cached open-webui archive does not match the promoted SHA-256")
        verified = True
    return Settings(
        embedding_model=expected["RAG_EMBEDDING_MODEL"],
        reranking_model=expected["RAG_RERANKING_MODEL"],
        query_prefix=expected["RAG_EMBEDDING_QUERY_PREFIX"],
        content_prefix=expected["RAG_EMBEDDING_CONTENT_PREFIX"],
        source=f"frozen:{version}",
        archive_sha256=expected["archive_sha256"],
        archive_verified=verified,
    )


def confirm_model_ids(settings: Settings, embedding_model: str | None, reranking_model: str | None) -> None:
    """Explicit ids only confirm the effective settings; the kit never remaps."""

    for given, effective, label in (
        (embedding_model, settings.embedding_model, "embedding"),
        (reranking_model, settings.reranking_model, "reranking"),
    ):
        if given is not None and given != effective:
            raise Blocked(f"NEEDS LEAD: {label} model {given} differs from the Open WebUI setting")


# ---------------------------------------------------------------------------
# Scenarios


@dataclasses.dataclass
class Context:
    target: str
    webui: Endpoint
    lemond: Endpoint
    token: str
    settings: Settings
    chat_model: str
    audio: Path | None = None
    whisper_model: str = DEFAULT_WHISPER_MODEL
    # Acceptance only: returns (chunk text, stored Qdrant vector) for one
    # indexed chunk of the handbook, so A-R3 can tie the app path to the
    # settings prefix.  None skips that part of the canary.
    stored_chunk: Callable[[], tuple[str, list[float]]] | None = None
    # Acceptance only: returns the Open WebUI journal since start.
    journal: Callable[[], str] | None = None
    unit: str = ACCEPTANCE_UNIT
    poll_timeout: float = 180.0


@dataclasses.dataclass
class ScenarioResult:
    id: str
    result: str
    detail: str
    duration_s: float
    values: dict[str, Any] = dataclasses.field(default_factory=dict)

    def line(self) -> str:
        return f"{self.id} {self.result} {self.detail}"


def lemond_embed(ctx: Context, text: str) -> list[float]:
    response = ctx.lemond.json(
        "POST",
        LEMOND_API["embeddings"],
        {"model": ctx.settings.embedding_model, "input": [text]},
    )
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ScenarioFailure("Lemonade embeddings returned malformed data")
    vector = data[0].get("embedding")
    if not isinstance(vector, list) or not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector
    ):
        raise ScenarioFailure("Lemonade embeddings returned a non-numeric vector")
    return [float(value) for value in vector]


def zembed_canary(ctx: Context) -> dict[str, Any]:
    query = lemond_embed(ctx, ctx.settings.query_prefix + CANARY_QUERY)
    relevant = lemond_embed(ctx, ctx.settings.content_prefix + CANARY_RELEVANT)
    unrelated = lemond_embed(ctx, ctx.settings.content_prefix + CANARY_UNRELATED)
    values: dict[str, Any] = {
        "texts": {"query": CANARY_QUERY, "relevant": CANARY_RELEVANT, "unrelated": CANARY_UNRELATED},
        "dimensions": len(query),
        "margin": round(cosine(query, relevant) - cosine(query, unrelated), 6)
        if len(query) == len(relevant) == len(unrelated)
        else None,
        "prefix_source": ctx.settings.source,
    }
    if not v1.embedding_canary_passes(query, relevant, unrelated):
        raise Escalation("ESCALATE: zembed canary")
    if ctx.stored_chunk is not None:
        chunk, stored = ctx.stored_chunk()
        direct = lemond_embed(ctx, ctx.settings.content_prefix + chunk)
        similarity = cosine(stored, direct)
        values["stored_vector_cosine"] = round(similarity, 6)
        if similarity < STORED_VECTOR_MINIMUM_COSINE:
            raise Escalation("ESCALATE: zembed canary (stored vector differs from the settings-prefixed embedding)")
    else:
        values["stored_vector_cosine"] = "not-applicable"
    return values


def rag_gate_constants() -> tuple[str, tuple[str, ...]]:
    namespace: dict[str, Any] = {}
    source = RAG_GATE.read_text(encoding="utf-8")
    for name in ("RAG_QUALIFICATION_QUERY", "RAG_QUALIFICATION_DOCUMENTS"):
        match = re.search(rf"^{name} = (\(.*?\n\)|\".*?\")$", source, re.MULTILINE | re.DOTALL)
        if match is None:
            raise RuntimeError(f"the packaged RAG gate no longer defines {name}")
        namespace[name] = ast.literal_eval(match.group(1))
    return namespace["RAG_QUALIFICATION_QUERY"], tuple(namespace["RAG_QUALIFICATION_DOCUMENTS"])


def zerank_qualification(ctx: Context) -> dict[str, Any]:
    health = ctx.webui.request("GET", API["rag_health"], token=ctx.token)
    if health.status == 503:
        if ctx.target == "production":
            raise Blocked(NEEDS_OWNER_RESTART)
        raise Blocked(f"NEEDS: re-save the RAG config or restart {ctx.unit}")
    if health.status != 200 or (health.json() or {}).get("status") != "qualified":
        raise ScenarioFailure(f"retrieval health returned HTTP {health.status}")
    query, documents = rag_gate_constants()
    response = ctx.lemond.json(
        "POST",
        LEMOND_API["rerank"],
        {"model": ctx.settings.reranking_model, "query": query, "documents": list(documents)},
    )
    scores = validate_rerank_results(
        response.get("results") if isinstance(response, dict) else None, len(documents)
    )
    if scores[0] <= max(scores[1:]):
        raise ScenarioFailure("the relevant document was not ranked first")
    return {"health": "qualified", "scores": [round(score, 6) for score in scores]}


def _wait_for_file(ctx: Context, file_id: str) -> None:
    deadline = time.monotonic() + ctx.poll_timeout
    path = API["file_status"].format(id=file_id)
    while True:
        response = ctx.webui.request("GET", path, token=ctx.token)
        status = (response.json() or {}).get("status") if response.status == 200 else None
        if status == "completed":
            return
        if status == "failed" or response.status not in {200, 202}:
            raise ScenarioFailure(f"file processing ended with HTTP {response.status} status {status}")
        if time.monotonic() > deadline:
            raise ScenarioFailure("file processing did not complete in time")
        time.sleep(0.5)


def cited_answer(ctx: Context) -> dict[str, Any]:
    body, content_type = multipart_file("file", HANDBOOK_NAME, handbook_bytes(), "text/markdown")
    started = time.monotonic()
    upload = ctx.webui.request("POST", API["files"], body=body, content_type=content_type, token=ctx.token)
    if upload.status != 200 or not isinstance((upload.json() or {}).get("id"), str):
        raise ScenarioFailure(f"handbook upload returned HTTP {upload.status}")
    file_id = upload.json()["id"]
    timings = {"upload_s": round(time.monotonic() - started, 3)}
    try:
        started = time.monotonic()
        _wait_for_file(ctx, file_id)
        timings["index_s"] = round(time.monotonic() - started, 3)
        started = time.monotonic()
        response = ctx.webui.request(
            "POST",
            API["chat"],
            payload={
                "model": ctx.chat_model,
                "stream": True,
                "temperature": 0,
                "params": {"temperature": 0},
                "messages": [{"role": "user", "content": CITED_ANSWER_PROMPT}],
                "files": [{"type": "file", "id": file_id}],
            },
            token=ctx.token,
        )
        timings["chat_s"] = round(time.monotonic() - started, 3)
        if response.status != 200:
            raise ScenarioFailure(f"file-scoped chat returned HTTP {response.status}")
        text, sources = parse_chat_response(response.body, response.content_type)
        summary = summarize_sources(sources)
        values = {
            "timings": timings,
            "sources": summary,
            "canonical_citation": CANONICAL_CITATION,
            "fact_present": CANONICAL_FACT in text,
        }
        if not cited_answer_passes(text, summary, HANDBOOK_NAME):
            raise ScenarioFailure(json.dumps(values, sort_keys=True, ensure_ascii=False))
        return values
    finally:
        ctx.webui.request("DELETE", API["file"].format(id=file_id), token=ctx.token)


def _active_enter_epoch(unit: str) -> float | None:
    raw = subprocess.run(
        ["systemctl", "show", "-p", "ActiveEnterTimestamp", "--timestamp=unix", "--value", unit],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return float(raw[1:]) if raw.startswith("@") else None


def _provider_install_epoch(package: str = SPEECH_PROVIDER_PACKAGE) -> float | None:
    for desc in Path("/var/lib/pacman/local").glob(f"{package}-*/desc"):
        lines = desc.read_text().splitlines()
        if lines[lines.index("%NAME%") + 1] == package and "%INSTALLDATE%" in lines:
            return float(lines[lines.index("%INSTALLDATE%") + 1])
    return None


def stt(ctx: Context) -> dict[str, Any]:
    if ctx.audio is None or not ctx.audio.is_file():
        raise Blocked("the jfk.flac clip is unavailable")
    if v1._file_sha256(ctx.audio) != JFK_FLAC_SHA256:
        raise Blocked("the jfk.flac clip does not match its pinned SHA-256")
    if ctx.target == "production" and provider_restart_needed(
        _active_enter_epoch(PRODUCTION_UNIT), _provider_install_epoch()
    ):
        raise Blocked(NEEDS_OWNER_RESTART)
    body, content_type = multipart_file("file", "jfk.flac", ctx.audio.read_bytes(), "audio/flac")
    started = time.monotonic()
    response = ctx.webui.request(
        "POST", API["transcriptions"], body=body, content_type=content_type, token=ctx.token
    )
    elapsed = round(time.monotonic() - started, 3)
    if response.status != 200:
        raise ScenarioFailure(f"transcription returned HTTP {response.status}")
    result = response.json()
    if not isinstance(result, dict):
        result = {}
    text = result.get("text")
    if not isinstance(text, str):
        text = ""
    language = result.get("language")
    if not isinstance(language, str):
        language = None
    values = {
        "transcription_s": elapsed,
        "language": language,
        "word_count": len(normalize_words(text).split()),
        "whisper": {"model": ctx.whisper_model, **whisper_pin_record(ctx.whisper_model)},
    }
    if not transcription_passes(text, language):
        raise ScenarioFailure(f"transcription did not match: {normalize_words(text)[:120]}")
    if ctx.journal is not None and "WhisperModel initialization failed" in ctx.journal():
        raise ScenarioFailure("the journal shows a Whisper model load failure")
    return values


SCENARIOS: Mapping[str, Callable[[Context], dict[str, Any]]] = MappingProxyType(
    {
        SCENARIO_IDS[0]: zembed_canary,
        SCENARIO_IDS[1]: zerank_qualification,
        SCENARIO_IDS[2]: cited_answer,
        SCENARIO_IDS[3]: stt,
    }
)


# A scenario that raises one of these is a FAIL row: a malformed Open WebUI or
# Lemonade response never ends the run without a receipt.
SCENARIO_FAILURES = (
    ScenarioFailure, OSError, http.client.HTTPException, ValueError, KeyError,
    TypeError, AttributeError, IndexError,
)


def run_scenario(ctx: Context, scenario_id: str) -> ScenarioResult:
    started = time.monotonic()
    try:
        values = SCENARIOS[scenario_id](ctx)
        result, detail = PASS, "ok"
    except Escalation as error:
        values, result, detail = {}, ESCALATE, str(error)
    except Blocked as error:
        values, result, detail = {}, BLOCKED, str(error)
    except SCENARIO_FAILURES as error:
        values, result, detail = {}, FAIL, f"{type(error).__name__}: {error}"
    return ScenarioResult(scenario_id, result, detail, round(time.monotonic() - started, 3), values)


def run_scenarios(ctx: Context, scenario_ids: Sequence[str]) -> list[ScenarioResult]:
    """Run in registry order; stop after an escalation or a blocked precondition."""

    results: list[ScenarioResult] = []
    for scenario_id in select_scenarios(scenario_ids):
        outcome = run_scenario(ctx, scenario_id)
        results.append(outcome)
        print(outcome.line(), flush=True)
        if outcome.result in {ESCALATE, BLOCKED}:
            break
    return results


def lemond_snapshot(lemond: Endpoint) -> tuple[Any, Any]:
    """The two read-only Lemonade requests: health and the served models."""

    return lemond.json("GET", LEMOND_API["health"]), lemond.json("GET", LEMOND_API["models"])


def build_receipt(
    *,
    target: str,
    mode: str,
    settings: Settings | None,
    chat_model: str,
    health: Any,
    results: Sequence[ScenarioResult],
    precondition: str | None = None,
) -> dict[str, Any]:
    codes = [item.result for item in results] + ([BLOCKED] if precondition else [])
    lemond = {
        key: health[key]
        for key in ("version", "start_time", "started_at", "uptime")
        if isinstance(health, dict) and key in health
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "target": target,
        "mode": mode,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lemonade": lemond,
        # The digest is claimed only when the cached archive was hashed and
        # matched; otherwise the binding is the pacman version alone.
        "open_webui_archive_sha256": settings.archive_sha256 if settings and settings.archive_verified else None,
        "open_webui_archive_binding": (
            None if settings is None or settings.source == "process-environ"
            else "archive-sha256" if settings.archive_verified else "pacman-version-only"
        ),
        "models": {
            "embedding": settings.embedding_model if settings else None,
            "reranking": settings.reranking_model if settings else None,
            "chat": chat_model,
        },
        "settings_source": settings.source if settings else None,
        "precondition": precondition,
        "scenarios": [
            {
                "id": item.id,
                "result": item.result,
                "detail": item.detail,
                "duration_s": item.duration_s,
                "values": item.values,
            }
            for item in results
        ],
        "exit_code": aggregate_exit_code(codes),
    }
    v1.assert_public_safe(receipt)
    return receipt


def write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    v1.assert_public_safe(receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Admin helpers shared by the acceptance environment and the production install


def resave_rag_config(webui: Endpoint, token: str, overrides: Mapping[str, Any] | None = None) -> int:
    """Re-save the current RAG config (optionally overridden); return health status."""

    current = webui.json("GET", API["rag_config"], token=token)
    if not isinstance(current, dict):
        raise ScenarioFailure("the RAG config response is malformed")
    webui.json("POST", API["rag_config_update"], {**current, **(overrides or {})}, token=token)
    return webui.request("GET", API["rag_health"], token=token).status


def configure(
    webui: Endpoint,
    token: str,
    *,
    chat_model: str,
    lemond_url: str = DEFAULT_LEMOND_URL,
    whisper_model: str = DEFAULT_WHISPER_MODEL,
) -> dict[str, Any]:
    """Set the credential-free Lemonade connection, local Whisper STT, and the chat model."""

    ollama = webui.json("GET", API["ollama_config"], token=token) or {}
    webui.json("POST", API["ollama_config_update"], {**ollama, "ENABLE_OLLAMA_API": False}, token=token)
    openai = webui.json("GET", API["openai_config"], token=token) or {}
    webui.json(
        "POST",
        API["openai_config_update"],
        {
            **openai,
            "ENABLE_OPENAI_API": True,
            "OPENAI_API_BASE_URLS": [lemond_url.rstrip("/") + "/api/v1"],
            "OPENAI_API_KEYS": [""],
            "OPENAI_API_CONFIGS": {"0": {}},
        },
        token=token,
    )
    audio = webui.json("GET", API["audio_config"], token=token) or {}
    stt_config = {**(audio.get("stt") or {}), "ENGINE": "", "WHISPER_MODEL": whisper_model}
    webui.json("POST", API["audio_config_update"], {**audio, "stt": stt_config}, token=token)
    listed = webui_chat_model(webui, token, chat_model)
    defaults = webui.json("GET", API["models_config"], token=token) or {}
    webui.json("POST", API["models_config"], {**defaults, "DEFAULT_MODELS": listed}, token=token)
    return {
        "chat_model": listed,
        "designated_chat_model": chat_model,
        "whisper_model": whisper_model,
        "ollama": False,
        "openai_keys": "empty",
    }


def webui_chat_model(webui: Endpoint, token: str, chat_model: str) -> str:
    """The id Open WebUI lists for the designated chat model, as this account sees it.

    Open WebUI forwards chat by the id it lists, which may be the bare name of
    a ``user.`` id.  A model the account cannot see is a precondition: the
    owner grants the account access in the admin UI.
    """

    models = webui.json("GET", API["models"], token=token) or {}
    listed = listed_model_id(served_model_ids(models), chat_model)
    if listed is None:
        raise Blocked(
            f"NEEDS OWNER: Open WebUI does not list the chat model {chat_model} for this account"
        )
    return listed


# ---------------------------------------------------------------------------
# CLI


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    resmoke = commands.add_parser("resmoke", help="run the open-webui.resmoke.* scenarios")
    resmoke.add_argument("--target", choices=TARGETS, required=True)
    resmoke.add_argument("--root", type=Path, help="acceptance root (acceptance target only; required there)")
    resmoke.add_argument("--origin", help=f"Open WebUI HTTPS origin (acceptance default {DEFAULT_ACCEPTANCE_ORIGIN})")
    resmoke.add_argument("--socket", type=Path, help="talk to Open WebUI over this UNIX socket instead")
    resmoke.add_argument("--cacert", type=Path, help="CA for the origin (acceptance default: the Caddy internal root)")
    resmoke.add_argument("--lemond-url", default=DEFAULT_LEMOND_URL, help=f"Lemonade origin (default {DEFAULT_LEMOND_URL})")
    resmoke.add_argument(
        "--chat-model", default=DEFAULT_CHAT_MODEL,
        help=f"the designated resident chat model; its bare name also matches (default {DEFAULT_CHAT_MODEL})",
    )
    resmoke.add_argument("--embedding-model", help="confirm the effective zembed id (default: the Open WebUI setting)")
    resmoke.add_argument("--reranking-model", help="confirm the effective zerank id (default: the Open WebUI setting)")
    resmoke.add_argument(
        "--whisper-model", choices=tuple(WHISPER_PINS), default=DEFAULT_WHISPER_MODEL,
        help=f"recorded Whisper size (default {DEFAULT_WHISPER_MODEL})",
    )
    resmoke.add_argument("--audio", type=Path, help="retained jfk.flac, SHA-256 verified before use")
    resmoke.add_argument("--scenario", action="append", default=[], help="scenario id or all (default all)")
    resmoke.add_argument("--receipt", type=Path, required=True)
    resmoke.add_argument("--mode", choices=("record", "rehearsal"), default="record")
    resmoke.add_argument("--credentials-dir", type=Path, help="directory with resmoke-email and resmoke-password (default $CREDENTIALS_DIRECTORY)")
    resmoke.add_argument("--unit", default=ACCEPTANCE_UNIT, help="acceptance Open WebUI user unit")

    configure_parser = commands.add_parser("configure", help="admin connection, STT, and chat-model settings over the socket")
    configure_parser.add_argument("--socket", type=Path, required=True)
    configure_parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)
    configure_parser.add_argument("--lemond-url", default=DEFAULT_LEMOND_URL)
    configure_parser.add_argument("--whisper-model", choices=tuple(WHISPER_PINS), default=DEFAULT_WHISPER_MODEL)
    configure_parser.add_argument("--credentials-dir", type=Path, help="directory with admin-email and admin-final-password (default $CREDENTIALS_DIRECTORY)")
    return parser


def _resmoke(args: argparse.Namespace) -> int:
    if args.target == "acceptance" and args.root is None:
        raise Blocked("--root is required for the acceptance target")
    lemond = Endpoint(origin=args.lemond_url)
    if args.socket is None and args.target == "production" and not args.origin:
        raise Blocked("--origin is required for the production target")

    settings: Settings | None = None
    health: Any = None
    results: list[ScenarioResult] = []
    precondition: str | None = None
    try:
        try:
            try:
                if args.socket is not None:
                    webui = Endpoint(socket_path=args.socket)
                elif args.target == "acceptance":
                    webui = Endpoint(
                        origin=args.origin or DEFAULT_ACCEPTANCE_ORIGIN,
                        cacert=args.cacert or acceptance_caddy_root_certificate(args.root),
                    )
                else:
                    webui = Endpoint(origin=args.origin, cacert=args.cacert)
            except (OSError, ssl.SSLError) as error:
                raise Blocked(f"the Open WebUI CA certificate is unavailable ({type(error).__name__})") from error
            if args.target == "acceptance":
                settings = settings_from_environ(read_process_environ(open_webui_pid(args.unit)))
            else:
                settings = settings_for_production(installed_open_webui_version())
            confirm_model_ids(settings, args.embedding_model, args.reranking_model)
            try:
                health, models = lemond_snapshot(lemond)
            except (OSError, http.client.HTTPException, ScenarioFailure) as error:
                raise Blocked(f"NEEDS LEAD: Lemonade is unreachable ({type(error).__name__})") from error
            require_models_ready(
                models, health, (settings.embedding_model, settings.reranking_model, args.chat_model)
            )
            email = credential("resmoke-email", args.credentials_dir)
            password = credential("resmoke-password", args.credentials_dir)
            try:
                token = signin(webui, email, password)
            except (OSError, http.client.HTTPException, ScenarioFailure) as error:
                raise Blocked(
                    f"Open WebUI is unreachable or rejected the smoke sign-in ({type(error).__name__})"
                ) from error
            chat_model = webui_chat_model(webui, token, args.chat_model)
        except Blocked as error:
            print(f"precondition BLOCKED {error}", flush=True)
            precondition = str(error)
        else:
            ctx = Context(
                target=args.target, webui=webui, lemond=lemond, token=token, settings=settings,
                chat_model=chat_model, audio=args.audio, unit=args.unit, whisper_model=args.whisper_model,
            )
            results = run_scenarios(ctx, args.scenario)
    except Exception as error:
        # An unexpected error still leaves a FAIL receipt; the detail names
        # only the error type so the receipt stays public-safe.
        results.append(ScenarioResult("open-webui.resmoke.run", FAIL, type(error).__name__, 0.0))
        raise
    finally:
        # Every run that gets this far leaves a receipt with its exit code,
        # except a rehearsal, which writes no evidence-shaped file.
        receipt = build_receipt(
            target=args.target, mode=args.mode, settings=settings, chat_model=args.chat_model,
            health=health, results=results, precondition=precondition,
        )
        receipt["whisper_model"] = args.whisper_model
        if args.mode != "rehearsal":
            write_receipt(args.receipt, receipt)
    return receipt["exit_code"]


def _configure(args: argparse.Namespace) -> int:
    webui = Endpoint(socket_path=args.socket)
    token = signin(
        webui,
        credential("admin-email", args.credentials_dir).casefold(),
        credential("admin-final-password", args.credentials_dir),
    )
    summary = configure(
        webui, token, chat_model=args.chat_model, lemond_url=args.lemond_url, whisper_model=args.whisper_model
    )
    print(json.dumps({"configure": "PASS", **summary}, sort_keys=True))
    return EXIT_PASS


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _resmoke(args) if args.command == "resmoke" else _configure(args)
    except Blocked as error:
        print(f"open-webui-household-scenarios: BLOCKED {error}", file=sys.stderr)
        return EXIT_PRECONDITION
    except (*SCENARIO_FAILURES, subprocess.SubprocessError) as error:
        print(f"open-webui-household-scenarios: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
