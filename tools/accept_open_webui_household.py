#!/usr/bin/env python3
"""Single-trial acceptance kit for the Open WebUI household candidate set.

The kit deploys the exact candidate bytes named by the build ticket's manifest
as user-level services under one disposable, marked root, wires them to the
shared Lemonade provider, and runs exactly one integrated trial set: one pass
over the scenario map, one restore drill, and one rollback drill.  Evidence
schema: ``open-webui-household-acceptance/v1``.

Subcommands: preflight [--probe-only], stage, up, down, trial, resmoke,
teardown [--keep-anchor].  The stub rehearsal (``--provider stub
--rehearsal``) is kit debugging only: it writes no evidence file.

The kit never loads, unloads, pins, pulls, restarts, or reconfigures Lemonade.
Its only Lemonade requests are ``GET /api/v1/health``, ``GET /api/v1/models``,
and inference through Open WebUI or the shared scenario module.

Exit codes for every subcommand: 0 pass, 1 failure, 2 usage error (an
unknown flag or an invalid flag combination), 3 escalate (zembed canary), 75 a
precondition is not met.
"""

from __future__ import annotations

import argparse
import ast
import base64
import dataclasses
import fnmatch
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import measure_open_webui_household as v1  # noqa: E402
import open_webui_household_scenarios as sc  # noqa: E402

SCHEMA = "open-webui-household-acceptance/v1"
MARKER = ".owui-acceptance"
KIT_STATE = "kit.json"
DEFAULT_ROOT = Path("/srv/build/arch-pkgs-owui-acceptance")
STUB_SCRIPT = TOOLS / "fixtures" / "open-webui-household-acceptance" / "stub_provider.py"

SLICE = "owui-acc.slice"
# A plain slice unit name: no template, escape, or path, and no empty
# dash-separated component (systemd nests ``a-b.slice`` under ``a.slice``).
_SLICE_NAME = re.compile(r"[A-Za-z0-9_.:]+(?:-[A-Za-z0-9_.:]+)*\.slice")
UNITS = MappingProxyType(
    {
        "qdrant": "owui-acc-qdrant.service",
        "valkey": "owui-acc-valkey.service",
        "relay": "owui-acc-rerank-relay.service",
        "open-webui": sc.ACCEPTANCE_UNIT,
        "caddy": "owui-acc-caddy.service",
        "sampler": "owui-acc-sampler.service",
        "stub": "owui-acc-stub.service",
    }
)
PORTS = MappingProxyType(
    {"qdrant": 16333, "qdrant-grpc": 16334, "valkey": 16379, "relay": 13306, "caddy": 18443, "stub": 23305}
)
STUB_URL = f"http://127.0.0.1:{PORTS['stub']}"

# The six deployed candidates (A-ID1), the archives the build ticket binds for
# publication only, and the supporting runtime dependencies absent from the
# host.  The generic CTranslate2 archives stay undeployed: the host's
# python-ctranslate2-gfx1151 provides and conflicts with them.
DEPLOYED_PACKAGES = (
    "open-webui",
    "python-rapidocr",
    "qdrant",
    "qdrant-migration",
    "qdrant-web-ui",
    "python-faster-whisper",
)
BOUND_NOT_DEPLOYED = ("ctranslate2", "python-ctranslate2")
BOUND_NOT_DEPLOYED_STATUS = (
    "bound, not deployed (host provider python-ctranslate2-gfx1151 provides and conflicts)"
)
SUPPORTING_PACKAGES = ("caddy", "python-omegaconf", "python-antlr4")
HOST_PROVIDERS = ("valkey", "python-ctranslate2-gfx1151", "python", "bubblewrap", "socat")
# The owner approved running the trial on the host's real ML provider set
# (option B), with no overlay: python-sentence-transformers is the AUR 5.7.0
# build, knowingly foreign, not the 5.5.1 the lock resolves.  The evidence
# records the pacman identity of every installed match.
PROVIDERS_OF_RECORD = (
    "python-sentence-transformers",
    "python-accelerate-gfx1151",
    "python-transformers-gfx1151",
    "python-pytorch*-gfx1151",
    "python-onnxruntime*",
    "python-ctranslate2-gfx1151",
    "python-faster-whisper",
)
PROVIDERS_OF_RECORD_NOTE = (
    "knowingly-foreign providers of record: the trial exercises the host provider set "
    "(owner decision, option B); no provider is overlaid"
)
HOST_TOOLS = (
    "bwrap", "socat", "bsdtar", "unshare", "systemd-creds", "systemd-run",
    "systemctl", "journalctl", "valkey-server", "ss",
)
PYTHON_SITE_PACKAGES = ("python-rapidocr", "python-faster-whisper", "python-omegaconf", "python-antlr4")
LEGACY_OPT = Path("/opt/open-webui")

REFUSED_ROOT_PREFIXES = (Path("/home"), Path("/tmp"), Path("/var/tmp"))
MAX_ROOT_USE_PERCENT = 80
FOOTPRINT_BYTES = 6 * 1024**3

ALEMBIC_HEAD = v1.CONTRACT["open_webui"]["alembic_head"]
QDRANT_VERSION = v1.CONTRACT["qdrant"]["version"]
QDRANT_DIMENSIONS = v1.CONTRACT["qdrant"]["dimensions"]
COLLECTIONS: tuple[str, ...] = tuple(v1.COLLECTIONS)
LIMITS = MappingProxyType({"restart_s": 25.0, "restore_s": 40.0, "rollback_state_s": 40.0})


def whisper_snapshot_input(model: str) -> str:
    """The flat snapshot directory under ``<root>/inputs/`` for one Whisper size."""

    return f"faster-whisper-{model}"


OPEN_WEBUI_SECRETS = (
    "webui-secret-key",
    "oauth-client-info-encryption-key",
    "oauth-session-token-encryption-key",
    "valkey-url",
    "qdrant-runtime-api-key",
)
BOOTSTRAP_CREDENTIALS = ("admin-email", "admin-name", "admin-bootstrap-password")
COMMISSION_CREDENTIALS = BOOTSTRAP_CREDENTIALS + ("admin-final-password",)
RESMOKE_CREDENTIALS = ("resmoke-email", "resmoke-password")
QDRANT_ADMIN_CREDENTIAL = "qdrant-admin-key"
ADMIN_EMAIL = "owui-acc-admin@household.invalid"
ADMIN_NAME = "Acceptance Administrator"
VALKEY_USER = "open-webui"

# Ported from "feat(qdrant): add production cutover route and rebind accepted
# candidates" (https://github.com/nisavid/arch-pkgs/pull/93), commit
# b99f9bded2c191ff82cca710b400384303dbeb49: the collection body, the payload
# indexes, and the HS256 JWT claims.
COLLECTION_BODY = MappingProxyType(
    {"vectors": {"size": 2560, "distance": "Cosine", "on_disk": False}, "hnsw_config": {"payload_m": 16, "m": 0}}
)
PAYLOAD_INDEXES = (
    {"field_name": "tenant_id", "field_schema": {"type": "keyword", "is_tenant": True, "on_disk": False}},
    {"field_name": "metadata.hash", "field_schema": {"type": "keyword", "on_disk": False}},
    {"field_name": "metadata.file_id", "field_schema": {"type": "keyword", "on_disk": False}},
)

# The trial's scenario map, in run order.  One pass; no step repeats.
TRIAL_STEPS: tuple[str, ...] = (
    "open-webui.acceptance.identity.archives",
    "open-webui.acceptance.identity.unit-properties",
    "open-webui.acceptance.ready.first-start",
    "open-webui.acceptance.auth.one-admin",
    "open-webui.acceptance.ready.restart",
    "open-webui.acceptance.qdrant.g4",
    "open-webui.acceptance.lemonade.no-credential",
    sc.SCENARIO_IDS[0],
    sc.SCENARIO_IDS[1],
    "open-webui.acceptance.route.caddy-uds",
    sc.SCENARIO_IDS[2],
    "open-webui.acceptance.failclosed.reranker-down",
    "open-webui.acceptance.failclosed.recovery",
    sc.SCENARIO_IDS[3],
    "open-webui.acceptance.privacy",
    "open-webui.acceptance.drill.restore",
    "open-webui.acceptance.drill.rollback",
    "open-webui.acceptance.resources",
    "open-webui.acceptance.evidence",
)


# ---------------------------------------------------------------------------
# Small pure helpers


def sha256_file(path: Path) -> str:
    return v1._file_sha256(path)


_ARCHIVE_NAME = re.compile(
    r"^(?P<package>.+)-(?P<version>[^-]+)-(?P<release>[^-]+)-(?P<arch>x86_64|any)\.pkg\.tar\.zst$"
)


def archive_package(name: str) -> str:
    match = _ARCHIVE_NAME.match(name)
    if match is None or "/" in name:
        raise ValueError(f"not a package archive name: {name}")
    return match.group("package")


def load_manifest(path: Path) -> dict[str, Any]:
    """Read the build ticket's candidate manifest (name, size, SHA-256, source commit).

    The kit reads only this file, never a directory listing.  Deployed
    archives must be exactly the six candidates; the generic CTranslate2
    archives may appear with ``"deployed": false``.
    """

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("archives"), list):
        raise ValueError("the manifest must be an object with an archives list")
    source_commit = raw.get("source_commit")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{7,40}", source_commit):
        raise ValueError("the manifest must name its source commit")
    deployed: dict[str, dict[str, Any]] = {}
    bound: dict[str, dict[str, Any]] = {}
    for item in raw["archives"]:
        if not isinstance(item, dict):
            raise ValueError("every manifest archive must be an object")
        name = item.get("name")
        size = item.get("size", item.get("size_bytes"))
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError(f"malformed manifest archive record: {name!r}")
        package = archive_package(name)
        record = {"package": package, "name": name, "size": size, "sha256": digest}
        target = deployed if item.get("deployed", True) else bound
        if package in deployed or package in bound:
            raise ValueError(f"the manifest names {package} more than once")
        target[package] = record
    if set(deployed) != set(DEPLOYED_PACKAGES):
        raise ValueError(
            "the manifest's deployed archives must be exactly "
            + ", ".join(DEPLOYED_PACKAGES)
            + f" (got {', '.join(sorted(deployed)) or 'none'})"
        )
    unexpected = set(bound) - set(BOUND_NOT_DEPLOYED)
    if unexpected:
        raise ValueError(f"unexpected undeployed archives: {', '.join(sorted(unexpected))}")
    return {
        "schema": raw.get("schema"),
        "source_commit": source_commit,
        "deployed": [deployed[package] for package in DEPLOYED_PACKAGES],
        "bound_not_deployed": [bound[package] for package in BOUND_NOT_DEPLOYED if package in bound],
        "sha256": sha256_file(path),
    }


def verify_archive(path: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Exact-bytes check: a regular non-symlink file with the pinned size and SHA-256."""

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{record['name']} is not a regular non-symlink file")
    size = path.stat().st_size
    if size != record["size"]:
        raise ValueError(f"size mismatch for {record['name']}: expected {record['size']}, got {size}")
    digest = sha256_file(path)
    if digest != record["sha256"]:
        raise ValueError(f"digest mismatch for {record['name']}")
    return {"name": record["name"], "size": size, "sha256": digest}


def sync_db_digests(desc_text: str) -> dict[str, str]:
    """Map archive file names to ``%SHA256SUM%`` from concatenated sync-db desc files."""

    digests: dict[str, str] = {}
    for block in desc_text.split("%FILENAME%\n")[1:]:
        name = block.split("\n", 1)[0].strip()
        match = re.search(r"%SHA256SUM%\n([0-9a-f]{64})", block)
        if name and match:
            digests[name] = match.group(1)
    return digests


def df_use_percent(total: int, used: int, free: int) -> int:
    """The ``df`` Use% figure: used over used plus available, rounded up."""

    denominator = used + free
    if denominator <= 0:
        return 100
    return -(-used * 100 // denominator)


def root_refusals(root: Path, use_percent: int, free_bytes: int, used_bytes: int | None = None) -> list[str]:
    """Why the acceptance root is unusable; empty when it qualifies.

    With ``used_bytes`` it also refuses a root whose filesystem would reach
    the use limit once the projected footprint lands, well before Qdrant's
    packaged 85% quota refuses writes mid-trial.
    """

    refusals = []
    for prefix in REFUSED_ROOT_PREFIXES:
        if root == prefix or prefix in root.parents:
            refusals.append(f"the root must not be under {prefix}")
    if use_percent >= MAX_ROOT_USE_PERCENT:
        refusals.append(
            f"the root's filesystem is at {use_percent}% use; the kit needs below {MAX_ROOT_USE_PERCENT}%"
        )
    if free_bytes < FOOTPRINT_BYTES:
        refusals.append("the root's filesystem cannot hold the projected footprint (about 6 GB)")
    elif used_bytes is not None and use_percent < MAX_ROOT_USE_PERCENT:
        projected = df_use_percent(0, used_bytes + FOOTPRINT_BYTES, free_bytes - FOOTPRINT_BYTES)
        if projected >= MAX_ROOT_USE_PERCENT:
            refusals.append(
                f"the root's filesystem would reach {projected}% use with the projected footprint "
                f"(about 6 GB); the kit needs below {MAX_ROOT_USE_PERCENT}%"
            )
    return refusals


def lemond_restarted(pre: Any, post: Any) -> bool:
    """True when Lemonade's health shows it restarted between two snapshots."""

    if not isinstance(pre, dict) or not isinstance(post, dict):
        return False
    for key in ("start_time", "started_at"):
        if key in pre and key in post:
            return pre[key] != post[key]
    before, after = pre.get("uptime"), post.get("uptime")
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return after < before
    return False


def lemond_summary(health: Any) -> dict[str, Any]:
    if not isinstance(health, dict):
        return {}
    summary = {
        key: health[key]
        for key in ("version", "start_time", "started_at", "uptime")
        if key in health
    }
    summary["loaded_models"] = sorted(sc.loaded_model_names(health))
    return summary


def mint_jwt(key: str, role: str, lifetime_s: int = 0, *, now: float | None = None) -> str:
    """HS256 Qdrant JWT for every household collection (ported from PR #93)."""

    def b64(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    claims: dict[str, Any] = {"access": [{"collection": name, "access": role} for name in COLLECTIONS]}
    if lifetime_s:
        claims["exp"] = int(now if now is not None else time.time()) + int(lifetime_s)
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = b64(hmac.new(key.encode("ascii"), head + b"." + body, hashlib.sha256).digest())
    return (head + b"." + body + b"." + signature).decode()


def jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def keyed_values(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    """Yield (dotted path, value) for every key that names an API key."""

    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            normalized = str(key).lower().replace("-", "_")
            if normalized.endswith(("api_key", "api_keys")) and not normalized.startswith("enable"):
                yield child, item
            yield from keyed_values(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from keyed_values(item, f"{path}[{index}]")


def nonempty_key_paths(*documents: Any) -> list[str]:
    """Paths of API-key fields holding anything but emptiness (A-S5)."""

    def empty(item: Any) -> bool:
        if isinstance(item, str):
            return item == ""
        if isinstance(item, list):
            return all(empty(element) for element in item)
        if isinstance(item, dict):
            return all(empty(element) for element in item.values())
        return True  # booleans, numbers, and nulls are not key material

    found = []
    for document in documents:
        for path, item in keyed_values(document):
            if not empty(item):
                found.append(path)
    return sorted(set(found))


_LOOPBACK_PORT = re.compile(r"(?:127\.0\.0\.1|\[::1\]|localhost):(\d+)")
_BARE_IPV6_LOOPBACK = re.compile(r"(?<![0-9A-Fa-f:])::1(?![0-9A-Fa-f:])")
# Any 127.0.0.0/8 address or prefix, such as systemd's rendering of
# IPAddressAllow=localhost as "127.0.0.0/8 ::1/128".
_IPV4_LOOPBACK = re.compile(r"(?<![\d.])127(?:\.\d{1,3}){3}(/\d{1,2})?(?![\d.])")


def publicize(value: Any, replacements: Sequence[tuple[str, str]]) -> Any:
    """Rewrite private paths and loopback addresses into public tokens."""

    if isinstance(value, str):
        text = value
        for private, token in replacements:
            if private:
                text = text.replace(private, token)
        text = _LOOPBACK_PORT.sub(r"loopback:\1", text)
        text = _IPV4_LOOPBACK.sub(lambda match: "loopback" + (match.group(1) or ""), text)
        return _BARE_IPV6_LOOPBACK.sub("loopback", text)
    if isinstance(value, dict):
        return {key: publicize(item, replacements) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [publicize(item, replacements) for item in value]
    return value


# ---------------------------------------------------------------------------
# Unit derivation and the A-ID2 table

KEEP = "kept"
REWRITTEN = "rewritten"
DROPPED = "dropped"
UNENFORCED = "configured-not-enforced"

_UNIT_POLICY: Mapping[tuple[str, str], tuple[str, str]] = MappingProxyType(
    {
        ("Unit", "Description"): (KEEP, ""),
        ("Unit", "Documentation"): (KEEP, ""),
        ("Unit", "After"): (DROPPED, "a system target the user manager cannot order against"),
        ("Unit", "Wants"): (DROPPED, "a system target the user manager cannot pull in"),
        ("Service", "Type"): (KEEP, ""),
        ("Service", "Restart"): (KEEP, ""),
        ("Service", "RestartSec"): (KEEP, ""),
        ("Service", "UMask"): (KEEP, ""),
        ("Service", "NoNewPrivileges"): (KEEP, ""),
        ("Service", "LimitNOFILE"): (KEEP, ""),
        ("Service", "TasksMax"): (KEEP, ""),
        ("Service", "MemoryHigh"): (KEEP, ""),
        ("Service", "MemoryMax"): (KEEP, ""),
        ("Service", "IPAddressDeny"): (UNENFORCED, "the user manager cannot attach the BPF address filter"),
        ("Service", "IPAddressAllow"): (UNENFORCED, "the user manager cannot attach the BPF address filter"),
        ("Service", "EnvironmentFile"): (REWRITTEN, "the packaged file is read from the extracted candidate tree"),
        ("Service", "LoadCredentialEncrypted"): (REWRITTEN, "sources live in the acceptance credstore"),
        ("Service", "LoadCredential"): (REWRITTEN, "sources live under the acceptance root"),
        ("Service", "WorkingDirectory"): (REWRITTEN, "state lives under the acceptance root"),
        ("Service", "Environment"): (REWRITTEN, "HOME and caches live under the acceptance root"),
        ("Service", "ExecStart"): (REWRITTEN, "runs the extracted candidate bytes"),
        ("Service", "User"): (DROPPED, "the user manager runs units as the invoking user"),
        ("Service", "Group"): (DROPPED, "the user manager runs units as the invoking user"),
        ("Service", "SupplementaryGroups"): (DROPPED, "the user manager cannot add groups"),
        ("Service", "StateDirectory"): (DROPPED, "the kit creates state under the acceptance root"),
        ("Service", "StateDirectoryMode"): (DROPPED, "the kit creates state under the acceptance root"),
        ("Service", "RuntimeDirectory"): (DROPPED, "the socket lives under $XDG_RUNTIME_DIR/owui-acc"),
        ("Service", "RuntimeDirectoryMode"): (DROPPED, "the socket lives under $XDG_RUNTIME_DIR/owui-acc"),
        ("Service", "ExecStartPre"): (DROPPED, "a privileged or root-secret preflight step"),
        ("Service", "ReadWritePaths"): (DROPPED, "belongs to the dropped ProtectSystem sandbox"),
        ("Service", "MemoryDenyWriteExecute"): (DROPPED, "sandboxing the user manager cannot apply"),
        ("Service", "CapabilityBoundingSet"): (DROPPED, "capability sets need the system manager"),
        ("Service", "AmbientCapabilities"): (DROPPED, "capability sets need the system manager"),
        ("Service", "LockPersonality"): (DROPPED, "sandboxing the user manager cannot apply"),
        ("Service", "RemoveIPC"): (DROPPED, "applies to a dedicated system user"),
        ("Service", "ProcSubset"): (DROPPED, "sandboxing the user manager cannot apply"),
    }
)
_DROPPED_PREFIXES = ("Protect", "Private", "Restrict", "SystemCall")


def classify_property(section: str, key: str) -> tuple[str, str]:
    """Return (status, reason) for one packaged unit property; unknown keys raise."""

    if section == "Install":
        return DROPPED, "runtime units are started explicitly, never enabled"
    policy = _UNIT_POLICY.get((section, key))
    if policy is not None:
        return policy
    if section == "Service" and key.startswith(_DROPPED_PREFIXES):
        return DROPPED, "sandboxing the user manager cannot apply"
    raise ValueError(f"unclassified unit property [{section}] {key}")


def parse_unit(text: str) -> list[tuple[str, str, str]]:
    properties = []
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not section:
            raise ValueError(f"malformed unit line: {line}")
        properties.append((section, key.strip(), value.strip()))
    return properties


def render_unit(sections: Sequence[tuple[str, Sequence[tuple[str, str]]]]) -> str:
    blocks = []
    for name, lines in sections:
        blocks.append(f"[{name}]\n" + "".join(f"{key}={value}\n" for key, value in lines))
    return "\n".join(blocks)


Rewrite = Callable[[str, str], list[tuple[str, str]]]


def derive_unit(
    unit: str,
    packaged: str,
    rewrite: Rewrite,
    extra: Sequence[tuple[str, str]],
    slice_unit: str = SLICE,
) -> tuple[str, list[dict[str, Any]]]:
    """Render a user unit from a packaged unit and return the A-ID2 rows.

    ``rewrite(key, value)`` returns the acceptance lines for a rewritten
    property; ``extra`` adds kit lines (containment environment);
    ``slice_unit`` is the kit slice the unit runs under.
    """

    unit_lines: list[tuple[str, str]] = []
    service_lines: list[tuple[str, str]] = [("Slice", slice_unit)]
    rows: list[dict[str, Any]] = []
    for section, key, value in parse_unit(packaged):
        status, reason = classify_property(section, key)
        target = unit_lines if section == "Unit" else service_lines
        if status == KEEP:
            target.append((key, f"Acceptance: {value}" if key == "Description" else value))
            continue
        if status == UNENFORCED:
            target.append((key, value))
            rows.append({"unit": unit, "property": key, "packaged": value, "acceptance": value,
                         "status": status, "reason": reason})
            continue
        if status == DROPPED:
            rows.append({"unit": unit, "property": key, "packaged": value, "acceptance": None,
                         "status": status, "reason": reason})
            continue
        replacement = rewrite(key, value)
        target.extend(replacement)
        rows.append({"unit": unit, "property": key, "packaged": value,
                     "acceptance": [f"{k}={v}" for k, v in replacement] or None,
                     "status": status if replacement else DROPPED, "reason": reason})
    service_lines.extend(extra)
    return render_unit((("Unit", unit_lines), ("Service", service_lines))), rows


def public_credential_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Present credential directives as ``name <- source`` so key names read as data."""

    def present(text: str) -> str:
        match = re.fullmatch(r"(LoadCredential(?:Encrypted)?)=([^:]+):(.+)", text)
        if match:
            return f"{match.group(1)} {match.group(2)} <- {match.group(3)}"
        match = re.fullmatch(r"([^:]+):(/.+)", text)
        return f"{match.group(1)} <- {match.group(2)}" if match else text

    public = []
    for row in rows:
        item = dict(row)
        for field in ("packaged", "acceptance"):
            value = item.get(field)
            if isinstance(value, str):
                item[field] = present(value)
            elif isinstance(value, list):
                item[field] = [present(entry) for entry in value]
        public.append(item)
    return public


# ---------------------------------------------------------------------------
# Peer sampling (A-P2) and listeners (A-S1)

_SS_PID = re.compile(r"pid=(\d+)")


def parse_ss_line(line: str) -> dict[str, Any] | None:
    parts = line.split()
    if len(parts) < 5:
        return None
    return {"state": parts[0], "local": parts[3], "peer": parts[4], "pids": [int(p) for p in _SS_PID.findall(line)]}


def split_hostport(text: str) -> tuple[str, int | None]:
    host, _, port = text.rpartition(":")
    host = host.strip("[]").split("%", 1)[0]
    return host, int(port) if port.isdigit() else None


def is_loopback(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def peer_violations(
    samples: Iterable[Mapping[str, Any]],
    *,
    allowed_ports: frozenset[int],
    listen_ports: Mapping[str, frozenset[int]],
) -> list[dict[str, Any]]:
    """Connections outside the allowed loopback peer set.

    Inbound connections to a unit's own listening port may come from any
    loopback client; every other connection must reach a loopback peer on an
    allowed port.  A SYN to an Ollama or hosted endpoint is a violation.
    """

    violations = []
    for sample in samples:
        if sample.get("state") in {"LISTEN", "UNCONN"}:
            continue
        _, local_port = split_hostport(str(sample.get("local", "")))
        peer_host, peer_port = split_hostport(str(sample.get("peer", "")))
        if not is_loopback(peer_host):
            violations.append(dict(sample))
        elif local_port in listen_ports.get(str(sample.get("unit")), frozenset()):
            continue
        elif peer_port not in allowed_ports:
            violations.append(dict(sample))
    return violations


def listener_findings(lines: Iterable[str], open_webui_pids: set[int], caddy_port: int) -> list[str]:
    findings = []
    for line in lines:
        parsed = parse_ss_line(line)
        if parsed is None:
            continue
        host, port = split_hostport(parsed["local"])
        if set(parsed["pids"]) & open_webui_pids:
            findings.append(f"Open WebUI TCP listener on port {port}")
        if port == caddy_port and not is_loopback(host):
            findings.append(f"non-loopback listener on the Caddy port ({host or '*'})")
    return findings


# ---------------------------------------------------------------------------
# Host interaction


class KitError(RuntimeError):
    """A host command failed."""


def run(
    command: Sequence[str],
    *,
    input: bytes | None = None,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        list(command), input=input, capture_output=True, check=False,
        env=None if env is None else {**os.environ, **env},
    )
    if check and result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        raise KitError(f"{Path(command[0]).name} exited {result.returncode}: {detail[0][:300]}")
    return result


def systemctl(*arguments: str, check: bool = True) -> str:
    return run(["systemctl", "--user", *arguments], check=check).stdout.decode().strip()


def unit_show(unit: str, *properties: str) -> dict[str, str]:
    out = systemctl("show", unit, *(f"--property={name}" for name in properties), check=False)
    shown = {}
    for line in out.splitlines():
        key, _, value = line.partition("=")
        shown[key] = value
    return shown


def unit_active(unit: str) -> bool:
    return systemctl("is-active", unit, check=False) == "active"


def unit_pids(unit: str) -> set[int]:
    cgroup = unit_show(unit, "ControlGroup").get("ControlGroup", "")
    if not cgroup:
        return set()
    try:
        text = (Path("/sys/fs/cgroup") / cgroup.lstrip("/") / "cgroup.procs").read_text()
    except OSError:
        return set()
    return {int(item) for item in text.split()}


def journal(unit: str, since: float | None = None, until: float | None = None) -> str:
    command = ["journalctl", "--user", "-u", unit, "-o", "cat", "--no-pager"]
    if since is not None:
        command += ["--since", f"@{since:.3f}"]
    if until is not None:
        command += ["--until", f"@{until:.3f}"]
    return run(command, check=False).stdout.decode("utf-8", "replace")


def host_package_version(package: str) -> str | None:
    result = run(["pacman", "-Q", package], check=False)
    return result.stdout.decode().split()[1] if result.returncode == 0 else None


HOST_IDENTITY_FIELDS = MappingProxyType(
    {"Version": "version", "Architecture": "architecture", "Build Date": "build_date", "Install Reason": "install_reason"}
)


def host_package_identity(package: str) -> dict[str, str] | None:
    """The pacman identity of a host-installed package, or None when it is absent."""

    result = run(["pacman", "-Qi", package], check=False, env={"LC_ALL": "C"})
    if result.returncode != 0:
        return None
    identity = {"package": package, "source": "host"}
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        key, _, value = line.partition(":")
        field = HOST_IDENTITY_FIELDS.get(key.strip())
        if field is not None:
            identity[field] = value.strip()
    return identity


def providers_of_record() -> dict[str, Any]:
    """The pacman identity of each installed provider of record, with a foreign flag."""

    installed = run(["pacman", "-Qq"], check=False).stdout.decode().split()
    foreign = set(run(["pacman", "-Qqm"], check=False).stdout.decode().split())
    packages: list[dict[str, Any]] = []
    absent: list[str] = []
    for pattern in PROVIDERS_OF_RECORD:
        matches = sorted(name for name in installed if fnmatch.fnmatchcase(name, pattern))
        if not matches:
            absent.append(pattern)
        for name in matches:
            identity = host_package_identity(name) or {"package": name, "source": "host"}
            packages.append({**identity, "foreign": name in foreign})
    return {"note": PROVIDERS_OF_RECORD_NOTE, "packages": packages, "absent": absent}


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def filesystem_usage(path: Path) -> tuple[int, int, int]:
    """(df Use%, available bytes, used bytes) for the filesystem holding ``path``."""

    existing = path
    while not existing.exists():
        existing = existing.parent
    usage = shutil.disk_usage(existing)
    return df_use_percent(usage.total, usage.used, usage.free), usage.free, usage.used


def make_writable(path: Path) -> None:
    if not path.exists():
        return
    for directory, _dirs, files in os.walk(path):
        os.chmod(directory, stat.S_IMODE(os.lstat(directory).st_mode) | stat.S_IWUSR | stat.S_IXUSR)
        for name in files:
            child = Path(directory) / name
            if not child.is_symlink():
                os.chmod(child, stat.S_IMODE(os.lstat(child).st_mode) | stat.S_IWUSR)


def remove_tree(path: Path) -> None:
    if path.exists() or path.is_symlink():
        make_writable(path)
        shutil.rmtree(path)


def make_read_only(path: Path) -> None:
    for directory, _dirs, files in os.walk(path, topdown=False):
        for name in files:
            child = Path(directory) / name
            if not child.is_symlink():
                os.chmod(child, stat.S_IMODE(os.lstat(child).st_mode) & ~0o222)
        os.chmod(directory, stat.S_IMODE(os.lstat(directory).st_mode) & ~0o222)


def tree_digest(path: Path) -> str:
    """SHA-256 over sorted relative paths and file digests."""

    digest = hashlib.sha256()
    for file in sorted(item for item in path.rglob("*") if item.is_file() and not item.is_symlink()):
        digest.update(f"{file.relative_to(path)}\0{sha256_file(file)}\n".encode())
    return digest.hexdigest()


def tree_sizes(path: Path) -> dict[str, int]:
    apparent = allocated = 0
    for file in path.rglob("*"):
        if file.is_file() and not file.is_symlink():
            info = file.stat()
            apparent += info.st_size
            allocated += info.st_blocks * 512
    return {"apparent_bytes": apparent, "allocated_bytes": allocated}


def wait_until(predicate: Callable[[], bool], timeout: float, what: str, interval: float = 0.5) -> float:
    started = time.monotonic()
    while not predicate():
        if time.monotonic() - started > timeout:
            raise sc.ScenarioFailure(f"timed out waiting for {what}")
        time.sleep(interval)
    return time.monotonic() - started


# ---------------------------------------------------------------------------
# The acceptance environment


@dataclasses.dataclass
class Kit:
    root: Path
    manifest_path: Path | None
    provider: str
    rehearsal: bool
    lemond_url: str
    chat_model: str | None
    embedding_model: str | None
    reranking_model: str | None
    whisper_model: str
    candidate_store: Path
    runtime_dir: Path
    slice: str = SLICE

    # Layout -----------------------------------------------------------
    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    @property
    def mode(self) -> str:
        return "rehearsal" if self.rehearsal else "record"

    @property
    def tree(self) -> Path:
        return self.path("tree")

    @property
    def credstore(self) -> Path:
        return self.path("credstore")

    @property
    def anchor(self) -> Path:
        return self.path("backups", "anchor")

    @property
    def raw(self) -> Path:
        return self.path("evidence", "raw")

    @property
    def ledger(self) -> Path:
        return self.path("ledger", "current")

    @property
    def unit_dir(self) -> Path:
        return self.runtime_dir / "systemd" / "user"

    @property
    def socket_path(self) -> Path:
        return self.runtime_dir / "owui-acc" / "open-webui.sock"

    @property
    def bootstrap_dropin(self) -> Path:
        return self.unit_dir / f"{UNITS['open-webui']}.d" / "10-bootstrap.conf"

    @property
    def lemond_port(self) -> int:
        parsed = urllib.parse.urlsplit(self.lemond_url)
        return parsed.port or (443 if parsed.scheme == "https" else 80)

    @property
    def lemond_host(self) -> str:
        return urllib.parse.urlsplit(self.lemond_url).hostname or "127.0.0.1"

    def units(self) -> tuple[str, ...]:
        names = ("qdrant", "valkey", "relay", "open-webui", "caddy", "sampler")
        return tuple(UNITS[name] for name in names + (("stub",) if self.provider == "stub" else ()))

    @property
    def lemond_origin(self) -> str:
        parsed = urllib.parse.urlsplit(self.lemond_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def replacements(self) -> list[tuple[str, str]]:
        replacements = [
            (str(self.root), "<root>"),
            (str(self.runtime_dir), "$XDG_RUNTIME_DIR"),
            (str(REPO_ROOT), "<repo>"),
            (str(Path.home()), "~"),
        ]
        if self.lemond_origin != sc.DEFAULT_LEMOND_URL:
            # A non-default provider origin never reaches public evidence.
            replacements.insert(0, (self.lemond_origin, "<lemond>"))
        return replacements

    # Persisted kit state ------------------------------------------------
    def state(self) -> dict[str, Any]:
        path = self.path(KIT_STATE)
        return json.loads(path.read_text()) if path.is_file() else {}

    def save_state(self, **changes: Any) -> dict[str, Any]:
        state = {**self.state(), **changes}
        self.path(KIT_STATE).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        return state

    # Credentials ----------------------------------------------------------
    def credential_route(self) -> str:
        return self.state().get("credential_route", "systemd-creds")

    def credential_path(self, name: str) -> Path:
        suffix = ".cred" if self.credential_route() == "systemd-creds" else ""
        return self.credstore / f"{name}{suffix}"

    def credential_directive(self, name: str) -> tuple[str, str]:
        key = "LoadCredentialEncrypted" if self.credential_route() == "systemd-creds" else "LoadCredential"
        return key, f"{name}:{self.credential_path(name)}"

    def store_credential(self, name: str, value: str) -> None:
        path = self.credential_path(name)
        if self.credential_route() == "systemd-creds":
            run(["systemd-creds", "--user", "encrypt", f"--name={name}", "-", str(path)], input=value.encode())
            os.chmod(path, 0o600)
        else:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)

    def read_credential(self, name: str) -> str:
        """Decrypt one credential into memory; the value is never printed or recorded."""

        path = self.credential_path(name)
        if self.credential_route() == "systemd-creds":
            return run(["systemd-creds", "--user", "decrypt", f"--name={name}", str(path), "-"]).stdout.decode()
        return path.read_text(encoding="utf-8")

    # Endpoints ------------------------------------------------------------
    def uds(self, timeout: float = 120.0) -> sc.Endpoint:
        return sc.Endpoint(socket_path=self.socket_path, timeout=timeout)

    def caddy(self) -> sc.Endpoint:
        return sc.Endpoint(
            origin=sc.DEFAULT_ACCEPTANCE_ORIGIN,
            cacert=sc.acceptance_caddy_root_certificate(self.root),
        )

    def lemond(self) -> sc.Endpoint:
        return sc.Endpoint(origin=self.lemond_url)

    def qdrant(self) -> Qdrant:
        return Qdrant(PORTS["qdrant"], self.read_credential(QDRANT_ADMIN_CREDENTIAL))

    # Candidate trees -------------------------------------------------------
    def packaged_env(self) -> dict[str, str]:
        return sc.parse_env_file(
            self.path("tree", "open-webui", "etc", "open-webui", "open-webui.env").read_text(encoding="utf-8")
        )

    def overlay(self, packaged_env: Mapping[str, str] | None = None) -> dict[str, str]:
        return sc.acceptance_overlay(
            packaged_env if packaged_env is not None else self.packaged_env(),
            self.root,
            lemond_url=self.lemond_url,
            qdrant_port=PORTS["qdrant"],
            relay_port=PORTS["relay"],
            rehearsal=self.rehearsal,
        )

    def site_packages(self, package: str) -> Path | None:
        matches = sorted(self.path("tree", package, "usr", "lib").glob("python3.*/site-packages"))
        return matches[-1] if matches else None

    def pythonpath(self) -> str:
        paths = [self.site_packages(package) for package in PYTHON_SITE_PACKAGES]
        return ":".join(str(path) for path in paths if path is not None)

    def caddy_binary(self) -> Path:
        """The host Caddy, unless stage had to extract the verified archive instead."""

        extracted = self.path("tree", "caddy", "usr", "bin", "caddy")
        return extracted if extracted.is_file() else Path("/usr/bin/caddy")


class Qdrant:
    def __init__(self, port: int, admin_key: str):
        self.endpoint = sc.Endpoint(origin=f"http://127.0.0.1:{port}", timeout=120.0)
        self.admin_key = admin_key

    def status(self, method: str, path: str, payload: Any = None, *, token: str | None = None) -> int:
        return self.endpoint.request(method, path, payload=payload, token=token).status

    def call(self, method: str, path: str, payload: Any = None, *, token: str | None = None) -> Any:
        response = self.endpoint.request(method, path, payload=payload, token=token or self.admin_key)
        if response.status != 200:
            raise sc.ScenarioFailure(f"Qdrant {method} {path.split('?')[0]} returned HTTP {response.status}")
        return (response.json() or {}).get("result")

    def ready(self) -> bool:
        try:
            return self.endpoint.request("GET", "/readyz").status == 200
        except OSError:
            return False

    def version(self) -> str | None:
        response = self.endpoint.request("GET", "/", token=self.admin_key)
        return (response.json() or {}).get("version") if response.status == 200 else None

    def create_collections(self) -> None:
        for name in COLLECTIONS:
            self.call("PUT", f"/collections/{name}", dict(COLLECTION_BODY))
            for index in PAYLOAD_INDEXES:
                self.call("PUT", f"/collections/{name}/index?wait=true", index)

    def shapes(self) -> dict[str, dict[str, Any]]:
        shapes = {}
        for name in COLLECTIONS:
            response = self.endpoint.request("GET", f"/collections/{name}", token=self.admin_key)
            if response.status != 200:
                shapes[name] = {"present": False}
                continue
            result = (response.json() or {}).get("result") or {}
            vectors = ((result.get("config") or {}).get("params") or {}).get("vectors") or {}
            shapes[name] = {
                "present": True,
                "size": vectors.get("size"),
                "distance": vectors.get("distance"),
                "indexes": sorted((result.get("payload_schema") or {}).keys()),
                "points": result.get("points_count"),
            }
        return shapes

    def snapshot(self, name: str, destination: Path) -> int:
        created = self.call("POST", f"/collections/{name}/snapshots?wait=true")
        snapshot = created["name"]
        response = self.endpoint.request("GET", f"/collections/{name}/snapshots/{snapshot}", token=self.admin_key)
        if response.status != 200:
            raise sc.ScenarioFailure(f"Qdrant snapshot download for {name} returned HTTP {response.status}")
        destination.write_bytes(response.body)
        self.call("DELETE", f"/collections/{name}/snapshots/{snapshot}?wait=true")
        return len(response.body)

    def recover(self, name: str, source: Path) -> None:
        if self.status("GET", f"/collections/{name}", token=self.admin_key) == 200:
            self.call("DELETE", f"/collections/{name}")
        body, content_type = sc.multipart_file("snapshot", source.name, source.read_bytes(), "application/octet-stream")
        response = self.endpoint.request(
            "POST", f"/collections/{name}/snapshots/upload?wait=true&priority=snapshot",
            body=body, content_type=content_type, token=self.admin_key,
        )
        if response.status != 200:
            raise sc.ScenarioFailure(f"Qdrant snapshot upload for {name} returned HTTP {response.status}")

    def stored_chunk(self, file_id: str) -> tuple[str, list[float]]:
        result = self.call(
            "POST",
            f"/collections/{COLLECTIONS[2]}/points/scroll",
            {
                "filter": {"must": [{"key": "tenant_id", "match": {"value": f"file-{file_id}"}}]},
                "limit": 1,
                "with_payload": True,
                "with_vector": True,
            },
        )
        points = (result or {}).get("points") or []
        if not points:
            raise sc.ScenarioFailure("no stored chunk for the indexed handbook")
        payload, vector = points[0].get("payload") or {}, points[0].get("vector")
        if not isinstance(payload.get("text"), str) or not isinstance(vector, list):
            raise sc.ScenarioFailure("the stored chunk is malformed")
        return payload["text"], [float(value) for value in vector]


# ---------------------------------------------------------------------------
# Valkey (RESP over a socket; the sentinel key for A-D3)


def valkey_command(port: int, user: str, password: str, *arguments: str) -> Any:
    def encode(parts: Sequence[str]) -> bytes:
        return f"*{len(parts)}\r\n".encode() + b"".join(
            f"${len(part.encode())}\r\n".encode() + part.encode() + b"\r\n" for part in parts
        )

    def reply(stream: Any) -> Any:
        line = stream.readline().rstrip(b"\r\n")
        kind, rest = line[:1], line[1:]
        if kind == b"+":
            return rest.decode()
        if kind == b"-":
            raise sc.ScenarioFailure(f"Valkey error: {rest.decode()[:80]}")
        if kind == b":":
            return int(rest)
        if kind == b"$":
            length = int(rest)
            return None if length < 0 else stream.read(length + 2)[:-2].decode()
        raise sc.ScenarioFailure("unexpected Valkey reply")

    with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
        stream = connection.makefile("rwb")
        stream.write(encode(["AUTH", user, password]))
        stream.write(encode(list(arguments)))
        stream.flush()
        reply(stream)
        return reply(stream)


def valkey_password(kit: Kit) -> str:
    return urllib.parse.urlsplit(kit.read_credential("valkey-url")).password or ""


# ---------------------------------------------------------------------------
# Rendering (stage and up)


def containment_environment(kit: Kit, name: str, home: Path | None = None) -> list[tuple[str, str]]:
    base = kit.path("state", name)
    values = {
        "HOME": home or base / "home",
        "XDG_CACHE_HOME": base / "cache" / "xdg",
        "XDG_DATA_HOME": base / "xdg-data",
        "XDG_CONFIG_HOME": base / "xdg-config",
        "TORCH_HOME": base / "cache" / "torch",
        "HF_HOME": base / "cache" / "huggingface",
        "TMPDIR": kit.path("tmp", name),
    }
    lines = [("Environment", f"{key}={value}") for key, value in values.items()]
    # The sampler imports repository modules; no unit writes __pycache__
    # beside a checkout that may live under /home.
    return lines + [("Environment", "PYTHONDONTWRITEBYTECODE=1")]


def containment_directories(kit: Kit) -> list[Path]:
    directories = []
    for name in ("open-webui", "qdrant", "valkey", "relay", "caddy", "sampler", "stub"):
        home = kit.path("state", name) if name == "open-webui" else None
        for _, assignment in containment_environment(kit, name, home):
            value = assignment.split("=", 1)[1]
            if value.startswith("/"):
                directories.append(Path(value))
        directories.append(kit.path("state", name))
    return directories


def open_webui_unit(kit: Kit, packaged: str) -> tuple[str, list[dict[str, Any]]]:
    state = kit.path("state", "open-webui")

    def rewrite(key: str, value: str) -> list[tuple[str, str]]:
        if key == "EnvironmentFile":
            return [
                ("EnvironmentFile", str(kit.path("tree", "open-webui") / value.lstrip("/"))),
                ("EnvironmentFile", str(kit.path("etc", "acceptance.env"))),
            ]
        if key in {"LoadCredentialEncrypted", "LoadCredential"}:
            name = value.split(":", 1)[0]
            if name == "session-epoch":
                return [("LoadCredential", f"session-epoch:{kit.ledger}")]
            return [kit.credential_directive(name)]
        if key == "WorkingDirectory":
            return [("WorkingDirectory", str(state))]
        if key == "Environment":
            name = value.split("=", 1)[0]
            return [("Environment", f"HOME={state}")] if name == "HOME" else []
        if key == "ExecStart":
            return [(
                "ExecStart",
                f"/usr/bin/bwrap --dev-bind / / --ro-bind {kit.path('tree', 'open-webui', 'opt', 'open-webui')} "
                f"{LEGACY_OPT} -- {kit.path('tree', 'open-webui', 'usr', 'bin', 'open-webui')} "
                f"serve --uds {kit.socket_path}",
            )]
        raise ValueError(f"no rewrite for {key}")

    extra = [line for line in containment_environment(kit, "open-webui", state) if not line[1].startswith("HOME=")]
    extra.append(("Environment", f"PYTHONPATH={kit.pythonpath()}"))
    extra += [("Environment", f"{key}={value}") for key, value in sc.speech_environment(kit.whisper_model).items()]
    return derive_unit("open-webui.service", packaged, rewrite, extra, kit.slice)


def qdrant_unit(kit: Kit, packaged: str) -> tuple[str, list[dict[str, Any]]]:
    state = kit.path("state", "qdrant")
    tree = kit.path("tree", "qdrant")

    def rewrite(key: str, value: str) -> list[tuple[str, str]]:
        if key == "EnvironmentFile":
            return [kit.credential_directive(QDRANT_ADMIN_CREDENTIAL)]
        if key == "WorkingDirectory":
            return [("WorkingDirectory", str(state))]
        if key == "ExecStart":
            return [(
                "ExecStart",
                f"{kit.path('etc', 'qdrant-credential-shim')} {tree / 'usr' / 'bin' / 'qdrant'} "
                f"--config-path {tree / 'etc' / 'qdrant' / 'config.yaml'}",
            )]
        raise ValueError(f"no rewrite for {key}")

    extra = containment_environment(kit, "qdrant") + [
        ("Environment", f"QDRANT__STORAGE__STORAGE_PATH={state / 'storage'}"),
        ("Environment", f"QDRANT__STORAGE__SNAPSHOTS_PATH={state / 'snapshots'}"),
        ("Environment", f"QDRANT__STORAGE__TEMP_PATH={state / 'tmp'}"),
        ("Environment", f"QDRANT__SERVICE__HTTP_PORT={PORTS['qdrant']}"),
        ("Environment", f"QDRANT__SERVICE__GRPC_PORT={PORTS['qdrant-grpc']}"),
        ("Environment", f"QDRANT__SERVICE__STATIC_CONTENT_DIR={kit.path('tree', 'qdrant-web-ui', 'usr', 'share', 'qdrant', 'web-ui')}"),
    ]
    return derive_unit("qdrant.service", packaged, rewrite, extra, kit.slice)


def kit_unit(kit: Kit, name: str, description: str, exec_start: str) -> str:
    service = [
        ("Type", "simple"),
        ("Slice", kit.slice),
        ("WorkingDirectory", str(kit.path("state", name))),
        *containment_environment(kit, name),
        ("ExecStart", exec_start),
        ("Restart", "on-failure"),
        ("RestartSec", "5s"),
        ("UMask", "0077"),
        ("NoNewPrivileges", "true"),
    ]
    return render_unit((("Unit", [("Description", f"Acceptance: {description}")]), ("Service", service)))


def render_units(kit: Kit) -> dict[str, str]:
    """Every runtime unit, keyed by unit name.  Deterministic from the root."""

    open_webui, _ = open_webui_unit(
        kit, kit.path("tree", "open-webui", "usr", "lib", "systemd", "system", "open-webui.service").read_text()
    )
    qdrant, _ = qdrant_unit(
        kit, kit.path("tree", "qdrant", "usr", "lib", "systemd", "system", "qdrant.service").read_text()
    )
    units = {
        UNITS["open-webui"]: open_webui,
        UNITS["qdrant"]: qdrant,
        UNITS["valkey"]: kit_unit(
            kit, "valkey", "dedicated RDB-only Valkey",
            f"/usr/bin/valkey-server {kit.path('etc', 'valkey-open-webui.conf')}",
        ),
        UNITS["relay"]: kit_unit(
            kit, "relay", "byte-level reranker relay",
            f"/usr/bin/socat TCP-LISTEN:{PORTS['relay']},bind=127.0.0.1,fork,reuseaddr "
            f"TCP:{kit.lemond_host}:{kit.lemond_port}",
        ),
        UNITS["caddy"]: kit_unit(
            kit, "caddy", "loopback HTTPS route to the Open WebUI socket",
            f"{kit.caddy_binary()} run --config {kit.path('etc', 'Caddyfile')} --adapter caddyfile",
        ),
        UNITS["sampler"]: kit_unit(
            kit, "sampler", "loopback peer sampler",
            f"/usr/bin/python3 {Path(__file__).resolve()} _sample --root {kit.root}",
        ),
    }
    if kit.provider == "stub":
        packaged = kit.packaged_env()
        units[UNITS["stub"]] = kit_unit(
            kit, "stub", "credential-free rehearsal provider",
            f"/usr/bin/python3 {STUB_SCRIPT} --host 127.0.0.1 --port {PORTS['stub']} "
            f"--embedding-model {packaged['RAG_EMBEDDING_MODEL']} --reranking-model {packaged['RAG_RERANKING_MODEL']}",
        )
    return units


def bootstrap_dropin(kit: Kit) -> str:
    return render_unit((("Service", [kit.credential_directive(name) for name in BOOTSTRAP_CREDENTIALS]),))


def install_units(kit: Kit) -> None:
    kit.unit_dir.mkdir(parents=True, exist_ok=True)
    for name, text in render_units(kit).items():
        (kit.unit_dir / name).write_text(text)
    systemctl("daemon-reload")


def a_id2_rows(kit: Kit) -> list[dict[str, Any]]:
    """The generated A-ID2 table: unit deviations, the overlay, and the fixed routes."""

    _, owui_rows = open_webui_unit(
        kit, kit.path("tree", "open-webui", "usr", "lib", "systemd", "system", "open-webui.service").read_text()
    )
    _, qdrant_rows = qdrant_unit(
        kit, kit.path("tree", "qdrant", "usr", "lib", "systemd", "system", "qdrant.service").read_text()
    )
    packaged_env = kit.packaged_env()
    overlay_rows = [
        {"unit": "open-webui.service", "property": f"acceptance.env {key}", "packaged": packaged_env.get(key),
         "acceptance": value, "status": "overlay", "reason": "allowlisted acceptance overlay key"}
        for key, value in sorted(kit.overlay(packaged_env).items())
    ]
    route = kit.credential_route()
    fixed = [
        ("session-epoch ledger", "/var/lib/open-webui-session-epoch/current (root)",
         f"{kit.ledger} through unshare -r", "the root ledger is exercised only in the production install"),
        ("socket", "/run/open-webui/open-webui.sock", str(kit.socket_path), "user runtime directory"),
        ("route", "production Caddy site block", f"Caddy on loopback:{PORTS['caddy']}, tls internal",
         "acceptance route; no trust-store install"),
        ("credentials", "systemd-creds (system)", route,
         "user credentials" if route == "systemd-creds" else "0400 files: a weaker restore proof"),
        ("launch", "/usr/bin/open-webui", "packaged wrapper inside bwrap; only /opt/open-webui shadowed",
         "exact candidate bytes without installing them"),
    ]
    fixed += [
        (f"Environment {key}", packaged_env.get(key), value,
         "local Whisper setting (ruling 11); the production drop-in carries the same value")
        for key, value in sorted(sc.speech_environment(kit.whisper_model).items())
    ]
    fixed_rows = [
        {"unit": "open-webui.service", "property": prop, "packaged": packaged, "acceptance": acceptance,
         "status": "recorded", "reason": reason}
        for prop, packaged, acceptance, reason in fixed
    ]
    return public_credential_rows(owui_rows + qdrant_rows) + overlay_rows + fixed_rows


# ---------------------------------------------------------------------------
# Session epoch ledger (unchanged helper bytes under a user namespace)


def ledger(kit: Kit, command: str) -> int:
    helper = kit.path("tree", "open-webui", "usr", "lib", "open-webui", "open-webui-session-epoch-ledger")
    out = run(["unshare", "-r", "/usr/bin/python3", str(helper), command, "--ledger", str(kit.ledger)]).stdout
    return int(out.decode().strip())


# ---------------------------------------------------------------------------
# Lemonade safety (ruling 8): read-only snapshots, and a refusal instead of a load


def provider_mismatch(kit: Kit, packaged_env: Mapping[str, str]) -> str | None:
    """Record mode: the kit's Lemonade must be the one the packaged env embeds against.

    The record-mode overlay keeps the packaged ``RAG_OPENAI_API_BASE_URL``, so
    a different ``--lemond-url`` would check one Lemonade while Open WebUI
    embeds against another (and loads models there implicitly).
    """

    if kit.provider != "lemond":
        return None
    expected = kit.lemond_url.rstrip("/") + "/api/v1"
    embed = packaged_env.get("RAG_OPENAI_API_BASE_URL", "").rstrip("/")
    reranker = urllib.parse.urlsplit(packaged_env.get("RAG_EXTERNAL_RERANKER_URL", ""))
    if embed != expected or f"{reranker.scheme}://{reranker.netloc}" != kit.lemond_origin:
        return (
            "NEEDS LEAD: --lemond-url differs from the packaged provider "
            "(RAG_OPENAI_API_BASE_URL and RAG_EXTERNAL_RERANKER_URL); the kit never widens the overlay"
        )
    return None


def require_lemond_ready(kit: Kit) -> Any:
    """Refuse (exit 75) unless zembed, zerank, and the chat model are already loaded."""

    mismatch = provider_mismatch(kit, kit.packaged_env())
    if mismatch:
        raise sc.Blocked(mismatch)
    try:
        health, models = sc.lemond_snapshot(kit.lemond())
    except (OSError, http.client.HTTPException, sc.ScenarioFailure) as error:
        raise sc.Blocked(f"NEEDS LEAD: Lemonade is unreachable ({type(error).__name__})") from error
    embedding, reranking = effective_models(kit)
    if not kit.chat_model:
        raise sc.Blocked("NEEDS LEAD: no chat model is designated")
    sc.require_models_ready(models, health, (embedding, reranking, kit.chat_model))
    return health


def effective_models(kit: Kit) -> tuple[str, str]:
    packaged = kit.packaged_env()
    embedding, reranking = packaged["RAG_EMBEDDING_MODEL"], packaged["RAG_RERANKING_MODEL"]
    for given, effective, label in (
        (kit.embedding_model, embedding, "embedding"),
        (kit.reranking_model, reranking, "reranking"),
    ):
        if given is not None and given != effective:
            raise sc.Blocked(f"NEEDS LEAD: {label} model {given} differs from the packaged {effective}")
    return embedding, reranking


# ---------------------------------------------------------------------------
# Service control


def snapshot_resources(kit: Kit, label: str) -> None:
    """Read memory.peak, memory.events, NRestarts, and CPU before a planned change."""

    record: dict[str, Any] = {"label": label, "t": time.time(), "units": {}}
    for unit in kit.units():
        shown = unit_show(unit, "ControlGroup", "NRestarts", "CPUUsageNSec", "ActiveState")
        entry: dict[str, Any] = {"state": shown.get("ActiveState")}
        for key in ("NRestarts", "CPUUsageNSec"):
            value = shown.get(key, "")
            entry[key] = int(value) if value.isdigit() else None
        cgroup = Path("/sys/fs/cgroup") / shown.get("ControlGroup", "").lstrip("/")
        if shown.get("ControlGroup"):
            try:
                entry["memory_peak"] = int((cgroup / "memory.peak").read_text().strip())
            except (OSError, ValueError):
                entry["memory_peak"] = None
            try:
                events = dict(line.split() for line in (cgroup / "memory.events").read_text().splitlines())
                entry["oom_kill"] = int(events.get("oom_kill", "0"))
            except (OSError, ValueError):
                entry["oom_kill"] = None
        record["units"][unit] = entry
    kit.raw.mkdir(parents=True, exist_ok=True)
    with (kit.raw / "resources.jsonl").open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(record, sort_keys=True) + "\n")


def resource_gates(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The only resource gates: no OOM kill, no unplanned restart.  The rest is recorded."""

    oom: dict[str, int] = {}
    restarts: dict[str, int] = {}
    peaks: dict[str, int] = {}
    cpu: dict[str, int] = {}
    for record in records:
        for unit, entry in (record.get("units") or {}).items():
            if isinstance(entry.get("oom_kill"), int):
                oom[unit] = max(oom.get(unit, 0), entry["oom_kill"])
            if isinstance(entry.get("NRestarts"), int):
                # systemd resets NRestarts on every explicit start or restart,
                # and a snapshot precedes every planned one, so any nonzero
                # count is an automatic (unplanned) restart.
                restarts[unit] = max(restarts.get(unit, 0), entry["NRestarts"])
            if isinstance(entry.get("memory_peak"), int):
                peaks[unit] = max(peaks.get(unit, 0), entry["memory_peak"])
            if isinstance(entry.get("CPUUsageNSec"), int):
                cpu[unit] = max(cpu.get(unit, 0), entry["CPUUsageNSec"])
    return {
        "oom_kills": oom,
        "unplanned_restarts": restarts,
        "memory_peak_max_bytes": peaks,
        "cpu_usage_nsec_max": cpu,
        "passes": not any(oom.values()) and not any(restarts.values()),
    }


def ready(kit: Kit) -> bool:
    try:
        return kit.uds(timeout=5).request("GET", sc.API["ready"]).status == 200
    except (OSError, http.client.HTTPException):
        return False


def wait_open_webui(kit: Kit, timeout: float) -> float:
    def check() -> bool:
        if systemctl("is-active", UNITS["open-webui"], check=False) == "failed":
            raise sc.ScenarioFailure("Open WebUI failed to start")
        return ready(kit)

    return wait_until(check, timeout, "Open WebUI /ready")


def start_open_webui(kit: Kit, *, restart: bool = False, timeout: float = 180.0) -> float:
    """Re-check Lemonade (ruling 8), then start and wait for /ready; returns seconds."""

    require_lemond_ready(kit)
    if not unit_active(UNITS["open-webui"]) and kit.socket_path.exists():
        kit.socket_path.unlink()
    started = time.monotonic()
    systemctl("restart" if restart else "start", UNITS["open-webui"])
    wait_open_webui(kit, timeout)
    return time.monotonic() - started


def start_qdrant(kit: Kit) -> Qdrant:
    systemctl("start", UNITS["qdrant"])
    qdrant = kit.qdrant()
    wait_until(qdrant.ready, 120, "Qdrant /readyz")
    return qdrant


def start_caddy(kit: Kit) -> None:
    systemctl("start", UNITS["caddy"])
    certificate = sc.acceptance_caddy_root_certificate(kit.root)
    wait_until(certificate.is_file, 60, "the Caddy internal root certificate")

    def serving() -> bool:
        try:
            return kit.caddy().request("GET", sc.API["ready"]).status == 200
        except (OSError, ssl.SSLError, http.client.HTTPException):
            return False

    wait_until(serving, 60, "the Caddy route")


def admin_token(kit: Kit, endpoint: sc.Endpoint | None = None) -> str:
    return sc.signin(
        endpoint or kit.uds(),
        kit.read_credential("admin-email").casefold(),
        kit.read_credential("admin-final-password"),
    )


# ---------------------------------------------------------------------------
# Anchor backup and restore (A-D1, A-D2, A-D3)


def data_dir(kit: Kit) -> Path:
    return Path(kit.overlay()["DATA_DIR"])


def whisper_dir(kit: Kit) -> Path:
    return Path(kit.overlay()["WHISPER_MODEL_DIR"])


def place_whisper(kit: Kit) -> None:
    """Pre-place the pinned Whisper snapshot in Hugging Face cache layout (offline).

    Every pinned file must match its SHA-256 before anything is written, and
    only the pinned files are placed.
    """

    pin = sc.WHISPER_PINS[kit.whisper_model]
    source = kit.path("inputs", whisper_snapshot_input(kit.whisper_model))
    for name, digest in sorted(pin["files"].items()):
        file = source / name
        if not file.is_file() or file.is_symlink() or sha256_file(file) != digest:
            raise sc.Blocked(f"the Whisper {name} is absent or does not match its pinned SHA-256")
    repository = "models--" + pin["repository"].replace("/", "--")
    base = whisper_dir(kit) / repository
    snapshot = base / "snapshots" / pin["revision"]
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in sorted(pin["files"]):
        shutil.copy2(source / name, snapshot / name)
    (base / "refs").mkdir(exist_ok=True)
    (base / "refs" / "main").write_text(pin["revision"])


def credential_fingerprints(kit: Kit) -> dict[str, str]:
    names = sorted(
        path.name.removesuffix(".cred") for path in kit.credstore.iterdir() if path.is_file()
    )
    return {name: hashlib.sha256(kit.read_credential(name).encode()).hexdigest() for name in names}


def backup_anchor(kit: Kit, qdrant: Qdrant) -> dict[str, Any]:
    """Anchor tuple with Open WebUI and Valkey stopped: SQLite and uploads, RDB,
    five Qdrant snapshots, the credstore, the epoch bound, and the archive manifest."""

    remove_tree(kit.anchor)
    (kit.anchor / "qdrant").mkdir(parents=True)
    snapshot_resources(kit, "before anchor backup")
    systemctl("stop", UNITS["open-webui"])
    systemctl("stop", UNITS["valkey"])  # SIGTERM saves the RDB at the configured save points
    shutil.copytree(data_dir(kit), kit.anchor / "data")
    shutil.copy2(kit.path("state", "valkey", "dump.rdb"), kit.anchor / "dump.rdb")
    shutil.copytree(kit.credstore, kit.anchor / "credstore")
    shapes = qdrant.shapes()
    snapshot_bytes = {name: qdrant.snapshot(name, kit.anchor / "qdrant" / f"{name}.snapshot") for name in COLLECTIONS}
    record = {
        "data_digest": tree_digest(kit.anchor / "data"),
        "rdb_sha256": sha256_file(kit.anchor / "dump.rdb"),
        "credstore_digest": tree_digest(kit.anchor / "credstore"),
        "collections": shapes,
        "snapshot_bytes": snapshot_bytes,
        "epoch_bound": ledger(kit, "current"),
        "archives": kit.state()["archives"],
        "sizes": tree_sizes(kit.anchor),
    }
    (kit.anchor / "anchor.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    private = kit.anchor / "fingerprints.json"
    private.write_text(json.dumps(credential_fingerprints(kit), sort_keys=True))
    os.chmod(private, 0o600)
    return record


def restore_tuple(kit: Kit, qdrant: Qdrant) -> dict[str, Any]:
    """Wipe and restore SQLite and uploads, the RDB, the credstore, and Qdrant."""

    remove_tree(data_dir(kit))
    shutil.copytree(kit.anchor / "data", data_dir(kit))
    kit.path("state", "valkey").mkdir(parents=True, exist_ok=True)
    shutil.copy2(kit.anchor / "dump.rdb", kit.path("state", "valkey", "dump.rdb"))
    remove_tree(kit.credstore)
    shutil.copytree(kit.anchor / "credstore", kit.credstore)
    for name in COLLECTIONS:
        qdrant.recover(name, kit.anchor / "qdrant" / f"{name}.snapshot")
    return {
        "data_digest": tree_digest(data_dir(kit)),
        "rdb_sha256": sha256_file(kit.path("state", "valkey", "dump.rdb")),
        "credstore_digest": tree_digest(kit.credstore),
    }


def restage_trees(kit: Kit, archives: Sequence[Mapping[str, Any]]) -> None:
    """Re-extract every tree from inputs/ after a digest check against the anchor."""

    for record in archives:
        verify_archive(kit.path("inputs", record["name"]), record)
    remove_tree(kit.tree)
    for record in archives:
        extract(kit, kit.path("inputs", record["name"]), archive_package(record["name"]))


def extract(kit: Kit, archive: Path, package: str) -> None:
    target = kit.path("tree", package)
    target.mkdir(parents=True)
    run(["bsdtar", "-xpf", str(archive), "-C", str(target),
         "--exclude", ".PKGINFO", "--exclude", ".BUILDINFO", "--exclude", ".MTREE", "--exclude", ".INSTALL"])
    make_read_only(target)


def create_state_directories(kit: Kit) -> None:
    for directory in containment_directories(kit):
        directory.mkdir(parents=True, exist_ok=True)
    for name in ("storage", "snapshots", "tmp"):
        kit.path("state", "qdrant", name).mkdir(parents=True, exist_ok=True)
    state_root = str(kit.path("state", "open-webui"))
    for value in kit.overlay().values():
        if value.startswith(state_root):
            Path(value).mkdir(parents=True, exist_ok=True)
    kit.socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)


MARKER_CREDENTIAL = "owui-acc-restore-marker"


def valkey_sentinel(kit: Kit) -> Any:
    return valkey_command(PORTS["valkey"], VALKEY_USER, valkey_password(kit), "GET", "owui-acc:sentinel")


def marker_divergence(kit: Kit) -> dict[str, bool]:
    """Before the restore: the live Valkey sentinel and credstore differ from the anchor."""

    anchored = json.loads((kit.anchor / "fingerprints.json").read_text())
    return {
        "valkey_sentinel_changed": valkey_sentinel(kit) != kit.state().get("sentinel"),
        "credstore_changed": credential_fingerprints(kit) != anchored,
    }


def legacy_service_state() -> dict[str, str]:
    """The host's own open-webui.service, read before and after the rollback drill."""

    out = run(["systemctl", "show", "open-webui.service", "--property=ActiveState",
               "--property=UnitFileState", "--property=ActiveEnterTimestampMonotonic"], check=False).stdout
    pairs = (line.partition("=") for line in out.decode().splitlines() if "=" in line)
    return {key: value for key, _, value in pairs}


def acceptance_listeners_on(port: int, kit: Kit) -> bool:
    """True when an acceptance unit's process listens on ``port``."""

    pids = {pid for unit in kit.units() for pid in unit_pids(unit)}
    lines = run(["ss", "-ltnpH", f"sport = :{port}"], check=False).stdout.decode("utf-8", "replace").splitlines()
    return any(set(parsed["pids"]) & pids for parsed in map(parse_ss_line, lines) if parsed)


def a_d3_checks(kit: Kit, anchor: Mapping[str, Any], restored: Mapping[str, Any], qdrant: Qdrant,
                pre_backup_session: str) -> dict[str, Any]:
    """The A-D3 checks, all before Caddy reopens."""

    db = data_dir(kit) / "webui.db"
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        head = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    shapes = qdrant.shapes()
    fingerprints = json.loads((kit.anchor / "fingerprints.json").read_text())
    session_status = kit.uds().request("GET", "/api/v1/auths/", token=pre_backup_session).status
    fresh = admin_token(kit)
    sentinel = valkey_sentinel(kit)
    values = {
        "quick_check": quick,
        "alembic_head": head,
        "digests_match": all(restored[key] == anchor[key] for key in ("data_digest", "rdb_sha256", "credstore_digest")),
        "collections_match": shapes == anchor["collections"],
        "tuple_match": credential_fingerprints(kit) == fingerprints,
        "epoch_above_bound": ledger(kit, "current") > anchor["epoch_bound"],
        "pre_backup_session_status": session_status,
        "fresh_login": bool(fresh),
        "valkey_sentinel_present": sentinel == kit.state().get("sentinel"),
    }
    values["passes"] = (
        quick == "ok" and head == ALEMBIC_HEAD and values["digests_match"] and values["collections_match"]
        and values["tuple_match"] and values["epoch_above_bound"] and session_status == 401
        and values["valkey_sentinel_present"]
    )
    return values


# ---------------------------------------------------------------------------
# Trial helpers


def upload_handbook(webui: sc.Endpoint, token: str, timeout: float = 180.0) -> str:
    body, content_type = sc.multipart_file("file", sc.HANDBOOK_NAME, sc.handbook_bytes(), "text/markdown")
    upload = webui.request("POST", sc.API["files"], body=body, content_type=content_type, token=token)
    file_id = (upload.json() or {}).get("id") if upload.status == 200 else None
    if not isinstance(file_id, str):
        raise sc.ScenarioFailure(f"handbook upload returned HTTP {upload.status}")

    def processed() -> bool:
        response = webui.request("GET", sc.API["file_status"].format(id=file_id), token=token)
        status = (response.json() or {}).get("status") if response.status == 200 else None
        if status == "failed":
            raise sc.ScenarioFailure("handbook processing failed")
        return status == "completed"

    wait_until(processed, timeout, "handbook processing")
    return file_id


def file_chat(webui: sc.Endpoint, token: str, chat_model: str, file_id: str | None) -> tuple[int, str, dict[str, Any], Any]:
    payload: dict[str, Any] = {
        "model": chat_model,
        "stream": True,
        "temperature": 0,
        "params": {"temperature": 0},
        "messages": [{"role": "user", "content": sc.CITED_ANSWER_PROMPT if file_id else "Reply with OK."}],
    }
    if file_id:
        payload["files"] = [{"type": "file", "id": file_id}]
    response = webui.request("POST", sc.API["chat"], payload=payload, token=token)
    if response.status != 200:
        try:
            detail = (response.json() or {}).get("detail")
        except (json.JSONDecodeError, AttributeError):
            detail = None
        return response.status, "", {"count": 0, "names": [], "scores": []}, detail
    text, sources = sc.parse_chat_response(response.body, response.content_type)
    return response.status, text, sc.summarize_sources(sources), None


def cited_fact(webui: sc.Endpoint, token: str, chat_model: str, file_id: str) -> bool:
    status, text, summary, _ = file_chat(webui, token, chat_model, file_id)
    return status == 200 and sc.cited_answer_passes(text, summary, sc.HANDBOOK_NAME)


def one_admin(webui: sc.Endpoint, token: str) -> dict[str, Any]:
    config = webui.json("GET", "/api/config", token=token) or {}
    users = webui.json("GET", "/api/v1/users/", token=token) or {}
    listed = users.get("users") if isinstance(users, dict) else None
    admins = [item for item in listed or [] if isinstance(item, dict) and item.get("role") == "admin"]
    values = {
        "enable_signup": (config.get("features") or {}).get("enable_signup"),
        "admin_count": len(admins),
        "user_count": users.get("total") if isinstance(users, dict) else None,
    }
    if values["enable_signup"] is not False or values["admin_count"] != 1:
        raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
    return values


def websocket_upgrade_status(port: int, cacert: Path, token: str) -> int:
    context = ssl.create_default_context(cafile=str(cacert))
    with socket.create_connection(("localhost", port), timeout=15) as raw:
        with context.wrap_socket(raw, server_hostname="localhost") as tls:
            key = base64.b64encode(os.urandom(16)).decode()
            tls.sendall(
                (
                    "GET /ws/socket.io/?EIO=4&transport=websocket HTTP/1.1\r\n"
                    f"Host: localhost:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                    f"Authorization: Bearer {token}\r\n\r\n"
                ).encode()
            )
            status_line = tls.recv(4096).split(b"\r\n", 1)[0].split()
            return int(status_line[1]) if len(status_line) > 1 and status_line[1].isdigit() else 0


def route_checks(kit: Kit, token: str) -> dict[str, Any]:
    """A-S1: HTTPS through Caddy, an authenticated WebSocket upgrade, and no stray listener."""

    https = kit.caddy().request("GET", "/").status
    upgrade = websocket_upgrade_status(PORTS["caddy"], sc.acceptance_caddy_root_certificate(kit.root), token)
    listeners = run(["ss", "-ltnpH"]).stdout.decode().splitlines()
    findings = listener_findings(listeners, unit_pids(UNITS["open-webui"]), PORTS["caddy"])
    values = {"https_status": https, "websocket_status": upgrade, "listener_findings": findings}
    if https != 200 or upgrade != 101 or findings:
        raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
    return values


def module_origins(kit: Kit) -> dict[str, str | None]:
    """Where the candidate modules resolve with the unit's search path (A-ID1, A-S7)."""

    site = sorted(kit.path("tree", "open-webui", "opt", "open-webui", "lib").glob("python3.*/site-packages"))
    pythonpath = ":".join([str(path) for path in site[-1:]] + [kit.pythonpath()])
    code = (
        "import json, importlib.util as u\n"
        "names = ('open_webui', 'faster_whisper', 'ctranslate2', 'rapidocr', 'omegaconf', 'antlr4')\n"
        "print(json.dumps({n: (lambda s: s.origin if s else None)(u.find_spec(n)) for n in names}))\n"
    )
    out = run(["/usr/bin/python3", "-c", code], env={"PYTHONPATH": pythonpath}).stdout
    return json.loads(out)


def stub_events(kit: Kit, since: float | None = None, until: float | None = None) -> list[dict[str, Any]]:
    events = []
    for line in journal(UNITS["stub"], since, until).splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "stub_request":
            events.append(event)
    return events


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# The single trial set


@dataclasses.dataclass
class Step:
    id: str
    result: str
    detail: str
    duration_s: float
    values: dict[str, Any] = dataclasses.field(default_factory=dict)

    def line(self) -> str:
        return f"{self.id} {self.result} {self.detail}"


MIGRATION_FAILURE = re.compile(r"\b(?:ERROR|CRITICAL|FAILED)\b|Traceback|\w*(?:Error|Exception):")
PYTHON_WARNING = re.compile(r"\w*Warning:")


def migration_errors(lines: Iterable[str]) -> list[str]:
    """Journal lines that report an Alembic failure.

    A Python warning is never a failure, even when its text says it may
    become an exception: Open WebUI 0.11's first start logs one for
    ``_alembic_tmp_tag``.
    """

    return [
        line for line in lines
        if "alembic" in line.lower() and not PYTHON_WARNING.search(line) and MIGRATION_FAILURE.search(line)
    ]


class Stop(Exception):
    """The trial stops after an escalation, a blocked precondition, or a critical failure."""


# A step that raises one of these is recorded as FAIL, so a malformed response
# never ends the single trial without evidence.
STEP_FAILURES = (
    sc.ScenarioFailure, KitError, OSError, http.client.HTTPException, ValueError, KeyError,
    TypeError, AttributeError, IndexError, sqlite3.Error, subprocess.SubprocessError,
)


class Trial:
    def __init__(self, kit: Kit, lemond_pre: Any = None):
        self.kit = kit
        self.steps: list[Step] = []
        self.token = ""
        self.listed_chat_model = ""
        self.seed_file = ""
        self.pre_backup_session = ""
        self.seed_window = (0.0, 0.0)
        self.anchor: dict[str, Any] = {}
        self.settings: sc.Settings | None = None
        self.lemond_pre: Any = lemond_pre
        self.lemond_post: Any = None

    def record(self, step: Step) -> None:
        self.steps.append(step)
        # A rehearsal prints no timings or measurements, but a step that does not
        # pass keeps its detail so the kit bug it found can be diagnosed.
        print(step.line() if not self.kit.rehearsal or step.result != sc.PASS else f"{step.id} {step.result}",
              flush=True)

    def step(self, step_id: str, action: Callable[[], dict[str, Any]], *, critical: bool = False) -> None:
        started = time.monotonic()
        try:
            values, result, detail = action(), sc.PASS, "ok"
        except sc.Escalation as error:
            values, result, detail = {}, sc.ESCALATE, str(error)
        except sc.Blocked as error:
            values, result, detail = {}, sc.BLOCKED, str(error)
        except STEP_FAILURES as error:
            values, result, detail = {}, sc.FAIL, f"{type(error).__name__}: {error}"
        self.record(Step(step_id, result, detail, round(time.monotonic() - started, 3), values))
        if result in {sc.ESCALATE, sc.BLOCKED} or (critical and result == sc.FAIL):
            raise Stop()

    def scenario(self, scenario_id: str, ctx: sc.Context) -> None:
        try:
            outcome = sc.run_scenario(ctx, scenario_id)
        except STEP_FAILURES as error:
            outcome = sc.ScenarioResult(scenario_id, sc.FAIL, f"{type(error).__name__}: {error}", 0.0)
        self.record(Step(outcome.id, outcome.result, outcome.detail, outcome.duration_s, outcome.values))
        if outcome.result in {sc.ESCALATE, sc.BLOCKED}:
            raise Stop()

    def chat_id(self) -> str:
        """The id Open WebUI lists for the designated chat model (maybe its bare name)."""

        if not self.listed_chat_model:
            self.listed_chat_model = sc.webui_chat_model(self.kit.uds(), self.token, self.kit.chat_model or "")
        return self.listed_chat_model

    # Steps ------------------------------------------------------------------
    def identity(self) -> dict[str, Any]:
        kit = self.kit
        manifest = load_manifest(kit.manifest_path) if kit.manifest_path else None
        state = kit.state()
        if manifest is None or manifest["sha256"] != state.get("manifest", {}).get("sha256"):
            raise sc.ScenarioFailure("the manifest differs from the one staged")
        archives = [verify_archive(kit.path("inputs", record["name"]), record) for record in manifest["deployed"]]
        origins = module_origins(kit)
        return {
            "manifest": {"source_commit": manifest["source_commit"], "sha256": manifest["sha256"], "schema": manifest["schema"]},
            "archives": archives,
            "bound_not_deployed": [{**record, "status": BOUND_NOT_DEPLOYED_STATUS} for record in manifest["bound_not_deployed"]],
            "supporting": state.get("supporting", []),
            "host_providers": {package: host_package_version(package) for package in HOST_PROVIDERS},
            "providers_of_record": providers_of_record(),
            "module_origins": origins,
            "whisper": {"model": kit.whisper_model, **sc.whisper_pin_record(kit.whisper_model)},
            "jfk_flac_sha256": sc.JFK_FLAC_SHA256,
            "speech": {
                "provider": f"{sc.SPEECH_PROVIDER_PACKAGE} {host_package_version(sc.SPEECH_PROVIDER_PACKAGE)}",
                "device": "cpu" if "USE_CUDA_DOCKER" not in kit.packaged_env() else "see USE_CUDA_DOCKER",
                "compute_type": kit.packaged_env().get("WHISPER_COMPUTE_TYPE", "int8 (upstream default)"),
                "hf_hub_offline": sc.speech_environment(kit.whisper_model)["HF_HUB_OFFLINE"],
            },
        }

    def unit_properties(self) -> dict[str, Any]:
        rows = a_id2_rows(self.kit)
        shown = unit_show(UNITS["open-webui"], "IPAddressDeny", "IPAddressAllow")
        warning = next(
            (line for line in journal(UNITS["open-webui"]).splitlines() if "IPAddress" in line or "BPF" in line),
            None,
        )
        return {"rows": rows, "effective": shown, "journal_warning": warning}

    def first_start(self) -> dict[str, Any]:
        kit = self.kit
        first = json.loads((kit.raw / "first-start.json").read_text())
        with sqlite3.connect(f"file:{data_dir(kit) / 'webui.db'}?mode=ro", uri=True) as connection:
            head = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        errors = migration_errors(journal(UNITS["open-webui"], first["started_at"]).splitlines())
        values = {"ready_s": first["ready_s"], "alembic_head": head, "migration_errors": len(errors),
                  "qdrant_fresh": first["qdrant_fresh"]}
        if head != ALEMBIC_HEAD or errors:
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def commission(self) -> dict[str, Any]:
        kit = self.kit
        command = ["systemd-run", "--user", "--wait", "--pipe", "--collect", "--quiet",
                   f"--setenv=OPEN_WEBUI_SOCKET={kit.socket_path}"]
        for name in COMMISSION_CREDENTIALS:
            key, value = kit.credential_directive(name)
            command.append(f"--property={key}={value}")
        command.append(str(kit.path("tree", "open-webui", "usr", "lib", "open-webui", "open-webui-commission-admin")))
        run(command)
        kit.bootstrap_dropin.unlink()
        systemctl("daemon-reload")
        snapshot_resources(kit, "before commissioning restart")
        start_open_webui(kit, restart=True)
        kit.save_state(commissioned=True)
        self.token = admin_token(kit)
        configured = sc.configure(kit.uds(), self.token, chat_model=kit.chat_model or "", lemond_url=kit.lemond_url,
                                  whisper_model=kit.whisper_model)
        self.listed_chat_model = configured["chat_model"]
        start_caddy(kit)
        return one_admin(kit.uds(), self.token)

    def restart(self) -> dict[str, Any]:
        kit = self.kit
        snapshot_resources(kit, "before restart")
        require_lemond_ready(kit)
        started = time.monotonic()
        systemctl("restart", UNITS["open-webui"])
        wait_open_webui(kit, 120)

        def healthy() -> bool:
            return kit.uds().request("GET", sc.API["rag_health"], token=self.token).status == 200

        wait_until(healthy, 120, "authenticated retrieval health")
        elapsed = round(time.monotonic() - started, 3)
        values = {"restart_to_ready_s": elapsed, "ceiling_s": LIMITS["restart_s"]}
        if elapsed > LIMITS["restart_s"]:
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def g4(self) -> dict[str, Any]:
        kit = self.kit
        qdrant = kit.qdrant()
        first = json.loads((kit.raw / "first-start.json").read_text())
        shapes = qdrant.shapes()
        runtime = jwt_claims(kit.read_credential("qdrant-runtime-api-key"))
        roles = sorted({entry.get("access") for entry in runtime.get("access", [])})
        admin = qdrant.admin_key
        readonly = mint_jwt(admin, "r", 300)
        prw = kit.read_credential("qdrant-runtime-api-key")
        point = {"points": [{"id": "00000000-0000-4000-8000-0000000c0de0",
                             "vector": [1.0] + [0.0] * (QDRANT_DIMENSIONS - 1),
                             "payload": {"tenant_id": "owui-acc-probe"}}]}
        probes = {
            "r_upsert": qdrant.status("PUT", f"/collections/{COLLECTIONS[1]}/points?wait=true", point, token=readonly),
            "prw_create": qdrant.status("PUT", "/collections/open-webui-rag-v1_smoke",
                                        {"vectors": {"size": 4, "distance": "Cosine"}}, token=prw),
            "prw_delete": qdrant.status("DELETE", f"/collections/{COLLECTIONS[3]}", token=prw),
        }
        owui_credentials = parse_unit((kit.unit_dir / UNITS["open-webui"]).read_text())
        holds_admin = any(QDRANT_ADMIN_CREDENTIAL in value for _, _, value in owui_credentials)
        values = {
            "version": qdrant.version(),
            "fresh_state": first["qdrant_fresh"],
            "collections": shapes,
            "runtime_roles": roles,
            "runtime_holds_admin_key": holds_admin,
            "negative_probes": probes,
        }
        good_shape = all(
            shape.get("present") and shape.get("size") == QDRANT_DIMENSIONS and shape.get("distance") == "Cosine"
            and {"tenant_id", "metadata.hash", "metadata.file_id"} <= set(shape.get("indexes", []))
            for shape in shapes.values()
        )
        if not (
            values["version"] == QDRANT_VERSION and values["fresh_state"] and good_shape and roles == ["prw"]
            and not holds_admin and set(probes.values()) == {403}
        ):
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def no_credential(self) -> dict[str, Any]:
        kit = self.kit
        owui_lines = parse_unit((kit.unit_dir / UNITS["open-webui"]).read_text())
        credentials = sorted(
            value.split(":", 1)[0] for _, key, value in owui_lines
            if key in {"LoadCredential", "LoadCredentialEncrypted"}
        )
        with sqlite3.connect(f"file:{data_dir(kit) / 'webui.db'}?mode=ro", uri=True) as connection:
            rows = [json.loads(row[0]) for row in connection.execute("SELECT data FROM config")]
        uds = kit.uds()
        exports = [uds.json("GET", sc.API["rag_config"], token=self.token),
                   uds.json("GET", sc.API["openai_config"], token=self.token)]
        findings = nonempty_key_paths(kit.packaged_env(), kit.overlay(), *rows, *exports)
        values: dict[str, Any] = {
            "runtime_credentials": credentials,
            "nonempty_key_fields": findings,
        }
        if kit.rehearsal:
            values["stub_requests_with_authorization"] = sum(
                1 for event in stub_events(kit) if event.get("authorization_present")
            )
        expected = sorted(OPEN_WEBUI_SECRETS + ("session-epoch",))
        if credentials != expected or findings or values.get("stub_requests_with_authorization"):
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def reranker_down(self) -> dict[str, Any]:
        kit = self.kit
        uds = kit.uds()
        snapshot_resources(kit, "before reranker-down")
        systemctl("stop", UNITS["relay"])
        query = {"collection_name": f"file-{self.seed_file}", "query": sc.CANONICAL_QUERY}
        latch = uds.request("POST", "/api/v1/retrieval/query/doc", payload=query, token=self.token).status
        chat_status, _, _, _ = file_chat(uds, self.token, self.chat_id(), None)
        retrieval = uds.request("POST", "/api/v1/retrieval/query/doc", payload=query, token=self.token)
        file_status, _, sources, detail = file_chat(uds, self.token, self.chat_id(), self.seed_file)
        health = uds.request("GET", sc.API["rag_health"], token=self.token).status
        retrieval_detail = (retrieval.json() or {}).get("detail") if retrieval.status != 200 else None
        from_gate = _rag_unavailable_detail()
        values = {
            "latching_retrieval_status": latch,
            "plain_chat_status": chat_status,
            "retrieval_status": retrieval.status,
            "file_chat_status": file_status,
            "health_status": health,
            "fixed_detail": retrieval_detail == from_gate and detail == from_gate,
            "file_chat_sources": sources["count"],
        }
        if not (chat_status == 200 and retrieval.status == 503 and file_status == 503 and health == 503
                and values["fixed_detail"] and sources["count"] == 0):
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def recovery(self) -> dict[str, Any]:
        kit = self.kit
        systemctl("start", UNITS["relay"])
        wait_until(lambda: port_in_use(PORTS["relay"]), 30, "the reranker relay")
        latched = kit.uds().request("GET", sc.API["rag_health"], token=self.token).status
        health = sc.resave_rag_config(kit.uds(), self.token)
        cited = cited_fact(kit.caddy(), self.token, self.chat_id(), self.seed_file)
        values = {"latched_status": latched, "health_after_resave": health, "cited_fact": cited}
        if latched != 503 or health != 200 or not cited:
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def privacy(self) -> dict[str, Any]:
        kit = self.kit
        environ = sc.read_process_environ(sc.open_webui_pid(UNITS["open-webui"]))
        telemetry = {key: environ.get(key) for key in sc.TELEMETRY_EXPECTED}
        samples = read_jsonl(kit.raw / "peers.jsonl")
        allowed = frozenset({kit.lemond_port, PORTS["relay"], PORTS["qdrant"], PORTS["valkey"]})
        listen = {
            UNITS["qdrant"]: frozenset({PORTS["qdrant"], PORTS["qdrant-grpc"]}),
            UNITS["valkey"]: frozenset({PORTS["valkey"]}),
            UNITS["relay"]: frozenset({PORTS["relay"]}),
            UNITS["caddy"]: frozenset({PORTS["caddy"]}),
            UNITS["stub"]: frozenset({PORTS["stub"]}),
        }
        violations = peer_violations(samples, allowed_ports=allowed, listen_ports=listen)
        pid = sc.open_webui_pid(UNITS["open-webui"])
        maps = Path(f"/proc/{pid}/maps").read_text(errors="replace")
        slice_units = systemctl("list-units", "--all", "--plain", "--no-legend", "owui-acc-*", check=False)
        haystack = {
            "unit_in_slice": bool(re.search(r"hayhooks|haystack", slice_units)),
            "module_mapped": "haystack" in maps,
            "env_keys": sorted(key for key in {**kit.packaged_env(), **kit.overlay()} if "HAYSTACK" in key or "HAYHOOKS" in key),
            "host_service_active": run(["systemctl", "is-active", "hayhooks.service"], check=False).stdout.decode().strip() == "active",
            "host_service_enabled": run(["systemctl", "is-enabled", "hayhooks.service"], check=False).stdout.decode().strip() == "enabled",
        }
        values = {
            "ip_address_policy": unit_show(UNITS["open-webui"], "IPAddressDeny", "IPAddressAllow"),
            "ip_address_policy_enforced": False,
            "peer_samples": len(samples),
            "peer_violations": violations,
            "telemetry": telemetry,
            "haystack": haystack,
        }
        if (violations or telemetry != dict(sc.TELEMETRY_EXPECTED) or not samples
                or any(value for value in haystack.values())):
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def restore_drill(self) -> dict[str, Any]:
        kit = self.kit
        systemctl("stop", UNITS["caddy"])
        self.pre_backup_session = admin_token(kit)
        sentinel = secrets.token_hex(16)
        kit.save_state(sentinel=sentinel)
        valkey_command(PORTS["valkey"], VALKEY_USER, valkey_password(kit), "SET", "owui-acc:sentinel", sentinel)
        qdrant = kit.qdrant()
        self.anchor = backup_anchor(kit, qdrant)
        systemctl("start", UNITS["valkey"])
        start_open_webui(kit)
        token = admin_token(kit)
        # The marker change touches every tuple member, so A-D3 proves the
        # restore rather than passing on unchanged state: the uploaded file
        # (SQLite and uploads, Qdrant), the Valkey sentinel, and a harmless
        # extra credential.
        deleted = kit.uds().request("DELETE", sc.API["file"].format(id=self.seed_file), token=token).status
        if deleted != 200:
            raise sc.ScenarioFailure(f"the marker change returned HTTP {deleted}")
        valkey_command(PORTS["valkey"], VALKEY_USER, valkey_password(kit), "SET", "owui-acc:sentinel",
                       secrets.token_hex(16))
        kit.store_credential(MARKER_CREDENTIAL, secrets.token_hex(16))
        pre_restore = marker_divergence(kit)
        snapshot_resources(kit, "before restore")
        epoch = ledger(kit, "reserve")
        started = time.monotonic()
        systemctl("stop", UNITS["open-webui"])
        systemctl("stop", UNITS["valkey"])
        restored = restore_tuple(kit, qdrant)
        systemctl("start", UNITS["valkey"])
        start_open_webui(kit)
        self.token = admin_token(kit)
        cited = cited_fact(kit.uds(), self.token, self.chat_id(), self.seed_file)
        elapsed = round(time.monotonic() - started, 3)
        checks = a_d3_checks(kit, self.anchor, restored, qdrant, self.pre_backup_session)
        start_caddy(kit)
        values = {
            "restore_s": elapsed,
            "ceiling_s": LIMITS["restore_s"],
            "cited_fact": cited,
            "reserved_epoch_above_bound": epoch > self.anchor["epoch_bound"],
            "pre_restore_divergence": pre_restore,
            "a_d3": checks,
            "route": route_checks(kit, self.token),
            "one_admin": one_admin(kit.caddy(), self.token),
        }
        # A ceiling overrun is recorded as this drill's FAIL; the trial still
        # runs the rollback drill (the step is not critical).
        if (not cited or elapsed > LIMITS["restore_s"] or not checks["passes"]
                or not all(pre_restore.values())):
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def rollback_drill(self) -> dict[str, Any]:
        kit = self.kit
        if not self.anchor.get("archives") or not (kit.anchor / "anchor.json").is_file():
            # Nothing destructive happens without an anchor to roll back to.
            raise sc.ScenarioFailure("no anchor backup exists; the rollback drill cannot run")
        legacy_before = legacy_service_state()
        snapshot_resources(kit, "before rollback")
        window = time.monotonic()
        pre_backup_session = self.pre_backup_session
        systemctl("stop", UNITS["caddy"])
        for unit in reversed(kit.units()):
            systemctl("stop", unit, check=False)
        remove_tree(kit.tree)
        remove_tree(kit.path("state"))
        restage_trees(kit, self.anchor["archives"])
        create_state_directories(kit)
        place_whisper(kit)
        epoch = ledger(kit, "reserve")
        started = time.monotonic()
        qdrant = start_qdrant(kit)
        restored = restore_tuple(kit, qdrant)
        for name in ("valkey", "relay", "sampler") + (("stub",) if kit.provider == "stub" else ()):
            systemctl("start", UNITS[name])
        start_open_webui(kit)
        self.token = admin_token(kit)
        cited = cited_fact(kit.uds(), self.token, self.chat_id(), self.seed_file)
        state_elapsed = round(time.monotonic() - started, 3)
        checks = a_d3_checks(kit, self.anchor, restored, qdrant, pre_backup_session)
        start_caddy(kit)
        legacy_after = legacy_service_state()
        port_8080 = acceptance_listeners_on(8080, kit)
        values = {
            "state_restore_s": state_elapsed,
            "ceiling_s": LIMITS["rollback_state_s"],
            "window_s": round(time.monotonic() - window, 3),
            "archives_match_anchor": True,
            "cited_fact": cited,
            "reserved_epoch_above_bound": epoch > self.anchor["epoch_bound"],
            "a_d3": checks,
            "route": route_checks(kit, self.token),
            "one_admin": one_admin(kit.caddy(), self.token),
            "legacy_service": {"before": legacy_before, "after": legacy_after},
            "legacy_service_touched": legacy_before != legacy_after,
            "acceptance_listener_on_8080": port_8080,
        }
        if (not cited or state_elapsed > LIMITS["rollback_state_s"] or not checks["passes"]
                or values["legacy_service_touched"] or port_8080):
            raise sc.ScenarioFailure(json.dumps(values, sort_keys=True))
        return values

    def resources(self) -> dict[str, Any]:
        kit = self.kit
        snapshot_resources(kit, "end of trial")
        gates = resource_gates(read_jsonl(kit.raw / "resources.jsonl"))
        qdrant = kit.qdrant()
        before = set(json.loads((kit.raw / "cache-inventory.json").read_text()))
        after = set(cache_inventory(kit))
        values = {
            **gates,
            "qdrant_storage": tree_sizes(kit.path("state", "qdrant", "storage")),
            "points": {name: shape.get("points") for name, shape in qdrant.shapes().items()},
            "anchor": self.anchor.get("sizes"),
            "snapshot_bytes": self.anchor.get("snapshot_bytes"),
            "cache_inventory_new_files": sorted(after - before),
        }
        if not gates["passes"]:
            raise sc.ScenarioFailure(json.dumps({"oom_kills": gates["oom_kills"],
                                                 "unplanned_restarts": gates["unplanned_restarts"]}))
        return values

    # The run -------------------------------------------------------------------
    def prepare_scenarios(self) -> sc.Context:
        """Index the handbook the drills keep as their marker, and bind the scenario context."""

        kit = self.kit
        self.seed_window = (time.time(), 0.0)
        self.seed_file = upload_handbook(kit.caddy(), self.token)
        self.seed_window = (self.seed_window[0], time.time())
        self.settings = sc.settings_from_environ(sc.read_process_environ(sc.open_webui_pid(UNITS["open-webui"])))
        embedding, reranking = effective_models(kit)
        sc.confirm_model_ids(self.settings, embedding, reranking)
        qdrant = kit.qdrant()
        return sc.Context(
            target="acceptance", webui=kit.caddy(), lemond=kit.lemond(), token=self.token,
            settings=self.settings, chat_model=self.chat_id(),
            audio=kit.path("inputs", "jfk.flac"), whisper_model=kit.whisper_model,
            stored_chunk=lambda: qdrant.stored_chunk(self.seed_file),
            journal=lambda: journal(UNITS["open-webui"]),
        )

    def run(self) -> int:
        kit = self.kit
        try:
            self.step(TRIAL_STEPS[0], self.identity, critical=True)
            self.step(TRIAL_STEPS[1], self.unit_properties)
            self.step(TRIAL_STEPS[2], self.first_start, critical=True)
            self.step(TRIAL_STEPS[3], self.commission, critical=True)
            self.step(TRIAL_STEPS[4], self.restart)
            self.step(TRIAL_STEPS[5], self.g4)
            self.step(TRIAL_STEPS[6], self.no_credential)
            contexts: list[sc.Context] = []
            self.step("open-webui.acceptance.handbook-indexed",
                      lambda: contexts.append(self.prepare_scenarios()) or {}, critical=True)
            ctx = contexts[0]
            self.scenario(TRIAL_STEPS[7], ctx)
            self.scenario(TRIAL_STEPS[8], ctx)
            self.step(TRIAL_STEPS[9], lambda: route_checks(kit, self.token))
            answer_started = time.time()
            self.scenario(TRIAL_STEPS[10], ctx)
            answer_ended = time.time()
            if kit.rehearsal:
                self.rehearsal_prefixes(*self.seed_window, answer_started, answer_ended)
            self.step(TRIAL_STEPS[11], self.reranker_down)
            self.step(TRIAL_STEPS[12], self.recovery)
            self.scenario(TRIAL_STEPS[13], ctx)
            self.step(TRIAL_STEPS[14], self.privacy)
            # Only a structural failure stops the trial; a restore that misses
            # its ceiling is recorded, and the rollback drill still runs.
            self.step(TRIAL_STEPS[15], self.restore_drill)
            self.step(TRIAL_STEPS[16], self.rollback_drill, critical=True)
        except Stop:
            pass
        self.step_safely(TRIAL_STEPS[17], self.resources)
        try:
            self.lemond_post, _ = sc.lemond_snapshot(kit.lemond())
        except (OSError, http.client.HTTPException, sc.ScenarioFailure):
            self.lemond_post = None
        return self.finish()

    def step_safely(self, step_id: str, action: Callable[[], dict[str, Any]]) -> None:
        try:
            self.step(step_id, action)
        except Stop:
            pass

    def rehearsal_prefixes(self, seed_started: float, seed_indexed: float, answer_started: float, answer_ended: float) -> None:
        """Rehearsal only: Open WebUI sent the packaged prefixes to the stub."""

        def heads(since: float, until: float) -> list[str]:
            return [head for event in stub_events(self.kit, since, until) for head in event.get("input_heads") or []]

        def check() -> dict[str, Any]:
            documents = heads(seed_started, seed_indexed)
            queries = heads(answer_started, answer_ended)
            settings = self.settings
            assert settings is not None
            def carries(head: str, prefix: str) -> bool:
                return prefix.startswith(head) or head.startswith(prefix)

            ok = (
                bool(documents) and all(carries(head, settings.content_prefix) for head in documents)
                and any(carries(head, settings.query_prefix) for head in queries)
            )
            if not ok:
                raise sc.ScenarioFailure("Open WebUI did not send the packaged embedding prefixes")
            return {}

        self.step("rehearsal.embedding-prefixes", check)

    def finish(self) -> int:
        kit = self.kit
        restarted = lemond_restarted(self.lemond_pre, self.lemond_post)
        results = [step.result for step in self.steps]
        exit_code = sc.aggregate_exit_code(results)
        if restarted and exit_code == sc.EXIT_PASS:
            exit_code = sc.EXIT_PRECONDITION
        evidence = build_evidence(kit, self, exit_code, restarted)
        try:
            v1.assert_public_safe(evidence)
            safe = True
            detail = "ok"
        except ValueError as error:
            safe, detail = False, str(error)
        evidence_step = Step(TRIAL_STEPS[18], sc.PASS if safe else sc.FAIL, detail, 0.0,
                             {"trial_set_count": 1, "restore_drills": 1, "rollback_drills": 1})
        self.record(evidence_step)
        if not safe and exit_code == sc.EXIT_PASS:
            exit_code = sc.EXIT_FAIL
        if kit.rehearsal:
            print(f"rehearsal bring-up {'PASS' if exit_code == sc.EXIT_PASS else 'FAIL'} (no evidence written)")
            return exit_code
        evidence = build_evidence(kit, self, exit_code, restarted)
        if restarted:
            print("NEEDS LEAD: Lemonade restarted during the trial; the run is void", file=sys.stderr)
        # The one trial's values always survive: the full document goes to a
        # private raw file first, and only the public copy waits on the
        # safety check.
        private = kit.raw / "trial-evidence.json"
        private.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        os.chmod(private, 0o600)
        if safe:
            v1.assert_public_safe(evidence)
            destination = kit.path("evidence", "public", f"open-webui-household-acceptance-{time.strftime('%Y-%m-%d', time.gmtime())}.json")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            print(f"evidence: {destination}")
        else:
            print(f"evidence: NOT public-safe ({detail}); the full document is kept privately at {private}",
                  file=sys.stderr)
        expectation = evidence.get("production_expectation")
        if expectation:
            print("production expectation for tools/open_webui_household_scenarios.py PRODUCTION_EXPECTATIONS "
                  "(add it in the evidence commit):")
            print(json.dumps({expectation["version"]: expectation["entry"]}, indent=2, sort_keys=True))
        return exit_code


_GATE_DETAIL: str | None = None


def _rag_unavailable_detail() -> str:
    global _GATE_DETAIL
    if _GATE_DETAIL is not None:
        return _GATE_DETAIL
    source = sc.RAG_GATE.read_text(encoding="utf-8")
    match = re.search(r"^RAG_UNAVAILABLE_DETAIL = (\(.*?\n\))$", source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError("the packaged RAG gate no longer defines RAG_UNAVAILABLE_DETAIL")
    detail = ast.literal_eval(match.group(1))
    if not isinstance(detail, str):
        raise RuntimeError("the packaged RAG gate's RAG_UNAVAILABLE_DETAIL is not a string")
    _GATE_DETAIL = detail
    return detail


def cache_inventory(kit: Kit) -> list[str]:
    """Files under every containment cache, HOME, and TMPDIR (uploads excluded)."""

    roots = {Path(value.split("=", 1)[1]) for directory in ("open-webui", "qdrant", "valkey", "relay", "caddy", "sampler", "stub")
             for _, value in containment_environment(kit, directory)
             if not value.startswith("HOME=") and value.split("=", 1)[1].startswith("/")}
    roots.add(Path(kit.overlay()["CACHE_DIR"]))
    files = set()
    for base in roots:
        if base.is_dir():
            for item in base.rglob("*"):
                if item.is_file() and "uploads" not in item.parts:
                    files.add(str(item.relative_to(kit.root)))
    return sorted(files)


CREDENTIAL_FALLBACK_CONDITION = "credentials: 0400-file fallback; systemd-creds --user unavailable"


def trial_conditions(kit: Kit) -> list[str]:
    """Host conditions the trial ran under; recorded, never a failure."""

    return [] if kit.credential_route() == "systemd-creds" else [CREDENTIAL_FALLBACK_CONDITION]


def private_credstore(path: Path) -> None:
    """Hold 0400 credential files in a 0700 directory owned by the operator."""

    os.chmod(path, 0o700)
    for item in path.iterdir():
        if item.is_file():
            os.chmod(item, 0o400)


def build_evidence(kit: Kit, trial: Trial, exit_code: int, lemond_restarted_: bool) -> dict[str, Any]:
    disposition = (
        "void: Lemonade restarted during the trial"
        if lemond_restarted_
        else "accepted" if exit_code == sc.EXIT_PASS else "not accepted"
    )
    state = kit.state()
    embedding, reranking = (trial.settings.embedding_model, trial.settings.reranking_model) if trial.settings else (None, None)
    document = {
        "schema": SCHEMA,
        "mode": kit.mode,
        "provider": kit.provider,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kit_commit": state.get("kit_commit"),
        "trial_set_count": 1,
        "restore_drills": 1,
        "rollback_drills": 1,
        "disposition": disposition,
        "exit_code": exit_code,
        "lemonade": {
            "receipt_ids": state.get("lemonade_receipts", []),
            "pre": lemond_summary(trial.lemond_pre),
            "post": lemond_summary(trial.lemond_post),
            "restarted": lemond_restarted_,
        },
        "models": {"embedding": embedding, "reranking": reranking, "chat": kit.chat_model},
        "canary_texts": {"query": sc.CANARY_QUERY, "relevant": sc.CANARY_RELEVANT, "unrelated": sc.CANARY_UNRELATED},
        "canonical_citation": sc.CANONICAL_CITATION,
        "limits": dict(LIMITS),
        "credential_route": kit.credential_route(),
        "conditions": trial_conditions(kit),
        "production_expectation": production_expectation_for(kit),
        "steps": [dataclasses.asdict(step) for step in trial.steps],
    }
    return publicize(document, kit.replacements())


def production_expectation_for(kit: Kit) -> dict[str, Any] | None:
    """The frozen production-settings entry for the open-webui archive this root deployed."""

    record = next(
        (item for item in kit.state().get("archives", []) if archive_package(item.get("name", "")) == "open-webui"),
        None,
    )
    env_file = kit.path("tree", "open-webui", "etc", "open-webui", "open-webui.env")
    if record is None or not env_file.is_file():
        return None
    return sc.production_expectation(record["name"], record["sha256"], kit.packaged_env())


# ---------------------------------------------------------------------------
# Subcommands


def preflight_facts(kit: Kit, *, probe_only: bool) -> tuple[dict[str, Any], list[str]]:
    """Every preflight check; returns the report and the refusals."""

    refusals: list[str] = []
    report: dict[str, Any] = {"mode": kit.mode, "provider": kit.provider}
    packaged: dict[str, str] | None = None
    use, free, used = filesystem_usage(kit.root)
    report["root_filesystem_use_percent"] = use
    refusals += root_refusals(kit.root, use, free, used)
    missing_tools = [tool for tool in HOST_TOOLS if shutil.which(tool) is None]
    if missing_tools:
        refusals.append(f"missing host tools: {', '.join(missing_tools)}")
    if host_package_version("python-ctranslate2-gfx1151") is None:
        refusals.append("the host speech provider python-ctranslate2-gfx1151 is not installed")
    if not LEGACY_OPT.is_dir():
        refusals.append(f"{LEGACY_OPT} is absent; the bwrap launch needs it as a mount point")
    busy = [port for name, port in PORTS.items() if (name != "stub" or kit.provider == "stub") and port_in_use(port)]
    if busy and not kit.path(KIT_STATE).exists():
        refusals.append(f"ports in use: {', '.join(map(str, busy))}")
    if kit.whisper_model not in sc.WHISPER_PINS:
        refusals.append(f"NEEDS LEAD: no pinned revision for Whisper model {kit.whisper_model}")
    packaged: dict[str, str] | None = None
    if kit.manifest_path is None:
        refusals.append("--manifest is required")
    else:
        try:
            manifest = load_manifest(kit.manifest_path)
            report["manifest_source_commit"] = manifest["source_commit"]
            located = {}
            for record in manifest["deployed"]:
                path = locate_archive(kit, record)
                if path is None:
                    refusals.append(f"missing pinned archive {record['name']}")
                    continue
                verify_archive(path, record)
                located[record["name"]] = "ok"
            report["archives"] = located
            packaged = packaged_env_from_archive(locate_archive(kit, manifest["deployed"][0]))
            report["packaged_models"] = [packaged["RAG_EMBEDDING_MODEL"], packaged["RAG_RERANKING_MODEL"]]
            mismatch = provider_mismatch(kit, packaged)
            if mismatch:
                refusals.append(mismatch)
        except (ValueError, OSError, KitError, KeyError, json.JSONDecodeError) as error:
            refusals.append(f"manifest: {error}")
            packaged = None
    if not probe_only:
        for package in SUPPORTING_PACKAGES:
            if host_package_version(package) is None and not list(kit.path("inputs").glob(f"{package}-*.pkg.tar.zst")):
                refusals.append(f"approved input {package} is absent (or install it system-wide)")
        if kit.whisper_model in sc.WHISPER_PINS:
            snapshot = kit.path("inputs", whisper_snapshot_input(kit.whisper_model))
            absent = [name for name in sorted(sc.WHISPER_PINS[kit.whisper_model]["files"]) if not (snapshot / name).is_file()]
            if absent:
                refusals.append(f"the pinned Whisper snapshot is incomplete in inputs/ (missing {', '.join(absent)})")
        if not kit.path("inputs", "jfk.flac").is_file():
            refusals.append("jfk.flac is absent from inputs/")
    if kit.provider == "lemond":
        if not kit.chat_model:
            refusals.append("--chat-model is required with the Lemonade provider")
        try:
            health, models = sc.lemond_snapshot(kit.lemond())
            report["lemonade"] = lemond_summary(health)
            report["served_models"] = sorted(sc.served_model_ids(models))
            if packaged is not None:
                embedding = kit.embedding_model or packaged["RAG_EMBEDDING_MODEL"]
                reranking = kit.reranking_model or packaged["RAG_RERANKING_MODEL"]
                for given, effective in ((embedding, packaged["RAG_EMBEDDING_MODEL"]), (reranking, packaged["RAG_RERANKING_MODEL"])):
                    if given != effective:
                        refusals.append(f"NEEDS LEAD: {given} differs from the packaged {effective}")
                sc.require_models_ready(models, health, [item for item in (embedding, reranking, kit.chat_model) if item])
        except sc.Blocked as error:
            refusals.append(str(error))
        except (OSError, http.client.HTTPException, sc.ScenarioFailure) as error:
            refusals.append(f"NEEDS LEAD: Lemonade is unreachable ({type(error).__name__})")
    return report, refusals


def locate_archive(kit: Kit, record: Mapping[str, Any]) -> Path | None:
    """Find one manifest archive: the staged input, else the store file with its bytes.

    The candidate store keeps superseded builds under the same file name, so
    a store match must equal the record's size and SHA-256.  When none does,
    the first name match is returned and ``verify_archive`` reports why.
    """

    name = record["name"]
    staged = kit.path("inputs", name)
    if staged.is_file():
        return staged
    if not kit.candidate_store.is_dir():
        return None
    matches = [
        candidate
        for candidate in sorted(kit.candidate_store.rglob(name))
        if candidate.is_file() and not candidate.is_symlink()
    ]
    for candidate in matches:
        if candidate.stat().st_size == record["size"] and sha256_file(candidate) == record["sha256"]:
            return candidate
    return matches[0] if matches else None


def packaged_env_from_archive(archive: Path | None) -> dict[str, str]:
    if archive is None:
        raise ValueError("the open-webui archive is unavailable")
    text = run(["bsdtar", "-xOf", str(archive), "etc/open-webui/open-webui.env"]).stdout.decode("utf-8")
    return sc.parse_env_file(text)


def cmd_preflight(kit: Kit, args: argparse.Namespace) -> int:
    report, refusals = preflight_facts(kit, probe_only=args.probe_only)
    report["refusals"] = refusals
    print(json.dumps(report, indent=2, sort_keys=True))
    return sc.EXIT_PRECONDITION if refusals else sc.EXIT_PASS


def require_marked(kit: Kit) -> None:
    if not kit.path(MARKER).is_file():
        raise sc.Blocked(f"{kit.root} is not a marked acceptance root")
    state = kit.state()
    if state and state.get("mode") != kit.mode:
        raise sc.Blocked(f"this root was staged in {state.get('mode')} mode; a rehearsal root is never reused")


def verify_supporting(kit: Kit) -> list[dict[str, Any]]:
    """Prefer the host-installed package and record its pacman identity.

    Only a package the host lacks is extracted from its approved archive, after
    the archive matches the sync database SHA-256.
    """

    records = []
    desc = None
    for package in SUPPORTING_PACKAGES:
        identity = host_package_identity(package)
        if identity is not None:
            records.append(identity)
            continue
        archives = sorted(kit.path("inputs").glob(f"{package}-*.pkg.tar.zst"))
        archives = [path for path in archives if archive_package(path.name) == package]
        if len(archives) != 1:
            raise sc.Blocked(f"approved input {package} is absent or ambiguous")
        if desc is None:
            text = ""
            for database in sorted(Path("/var/lib/pacman/sync").glob("*.db")):
                text += run(["bsdtar", "-xOf", str(database), "*/desc"], check=False).stdout.decode("utf-8", "replace")
            desc = sync_db_digests(text)
        digest = sha256_file(archives[0])
        if desc.get(archives[0].name) != digest:
            raise sc.Blocked(f"{archives[0].name} does not match the sync database SHA-256")
        extract(kit, archives[0], package)
        records.append({"package": package, "source": "sync-db", "name": archives[0].name,
                        "size": archives[0].stat().st_size, "sha256": digest})
    return records


def probe_systemd_creds() -> bool:
    """Whether both consumers can open a ``systemd-creds --user`` credential.

    The kit decrypts from its own process (``read_credential``) and the units
    through ``LoadCredentialEncrypted=``; the route is usable only if both work.
    """

    try:
        with tempfile.TemporaryDirectory(prefix="owui-acc-probe-") as directory:
            sealed = Path(directory) / "probe.cred"
            run(["systemd-creds", "--user", "encrypt", "--name=owui-acc-probe", "-", str(sealed)], input=b"probe")
            opened = run(["systemd-creds", "--user", "decrypt", "--name=owui-acc-probe", str(sealed), "-"]).stdout
            loaded = run([
                "systemd-run", "--user", "--wait", "--pipe", "--collect", "--quiet",
                f"--property=LoadCredentialEncrypted=owui-acc-probe:{sealed}",
                "sh", "-c", 'cat "$CREDENTIALS_DIRECTORY/owui-acc-probe"',
            ]).stdout
    except KitError:
        return False
    return opened == loaded == b"probe"


def render_etc(kit: Kit) -> None:
    """Render ``<root>/etc``: the overlay, Caddyfile, Valkey config and ACL, and the Qdrant shim.

    Stage calls it after minting credentials; the keep-anchor revive calls it
    after restoring the credstore, because teardown removes ``etc/``.  The ACL
    holds only the SHA-256 of the Valkey password from the ``valkey-url``
    credential.
    """

    etc = kit.path("etc")
    etc.mkdir(parents=True, exist_ok=True)
    (etc / "acceptance.env").write_text(sc.render_overlay(kit.overlay()))
    (etc / "Caddyfile").write_text(sc.render_acceptance_caddyfile(kit.root, kit.socket_path, PORTS["caddy"]))
    (etc / "valkey-open-webui.conf").write_text(
        sc.render_valkey_config(PORTS["valkey"], etc / "valkey-open-webui.acl", kit.path("state", "valkey"))
    )
    acl = etc / "valkey-open-webui.acl"
    acl.write_text(sc.render_valkey_acl(sc.valkey_password_hash(valkey_password(kit))))
    os.chmod(acl, 0o600)
    shim = etc / "qdrant-credential-shim"
    shim.write_text(
        '#!/bin/sh\n'
        f'QDRANT__SERVICE__API_KEY=$(cat "$CREDENTIALS_DIRECTORY/{QDRANT_ADMIN_CREDENTIAL}") && '
        'export QDRANT__SERVICE__API_KEY && exec "$@"\n'
    )
    os.chmod(shim, 0o700)


def mint_credentials(kit: Kit) -> None:
    kit.credstore.mkdir(mode=0o700)
    valkey = secrets.token_hex(32)
    qdrant_admin = secrets.token_hex(32)
    final_password = secrets.token_urlsafe(24)
    values = {
        "webui-secret-key": secrets.token_urlsafe(48),
        "oauth-client-info-encryption-key": secrets.token_urlsafe(48),
        "oauth-session-token-encryption-key": secrets.token_urlsafe(48),
        "valkey-url": f"redis://{VALKEY_USER}:{valkey}@127.0.0.1:{PORTS['valkey']}/0",
        "qdrant-runtime-api-key": mint_jwt(qdrant_admin, "prw"),
        QDRANT_ADMIN_CREDENTIAL: qdrant_admin,
        "admin-email": ADMIN_EMAIL,
        "admin-name": ADMIN_NAME,
        "admin-bootstrap-password": secrets.token_urlsafe(24),
        "admin-final-password": final_password,
        "resmoke-email": ADMIN_EMAIL,
        "resmoke-password": final_password,
    }
    for name, value in values.items():
        kit.store_credential(name, value)


def cmd_stage(kit: Kit, args: argparse.Namespace) -> int:
    report, refusals = preflight_facts(kit, probe_only=False)
    if refusals:
        print(json.dumps({"refusals": refusals}, indent=2))
        return sc.EXIT_PRECONDITION
    if kit.root.exists() and not kit.path(MARKER).is_file():
        foreign = [item.name for item in kit.root.iterdir() if item.name != "inputs"]
        if foreign:
            raise sc.Blocked(f"{kit.root} holds more than inputs/ and carries no acceptance marker")
    if kit.path(KIT_STATE).exists():
        raise sc.Blocked("this root is already staged; tear it down first")
    kit.root.mkdir(parents=True, exist_ok=True)
    kit.path(MARKER).write_text("open-webui household acceptance root; teardown removes it\n")
    for directory in ("inputs", "tree", "etc", "ledger", "evidence/raw", "evidence/public", "backups"):
        kit.path(directory).mkdir(parents=True, exist_ok=True)
    os.chmod(kit.path("ledger"), 0o700)
    assert kit.manifest_path is not None
    manifest = load_manifest(kit.manifest_path)
    archives = []
    for record in manifest["deployed"]:
        source = locate_archive(kit, record)
        assert source is not None
        target = kit.path("inputs", record["name"])
        if source != target:
            shutil.copy2(source, target)
        archives.append(verify_archive(target, record))
    for record in archives:
        extract(kit, kit.path("inputs", record["name"]), archive_package(record["name"]))
    supporting = verify_supporting(kit)
    route = "systemd-creds" if probe_systemd_creds() else "plaintext-0400"
    kit.save_state(
        **staged_pins(kit), credential_route=route, commissioned=False, trial_started=False,
        manifest={"sha256": manifest["sha256"], "source_commit": manifest["source_commit"]},
        archives=archives + [record for record in supporting if record["source"] == "sync-db"],
        supporting=supporting, kit_commit=kit_commit(),
    )
    if route != "systemd-creds":
        print("credentials: systemd-creds --user is unavailable; using 0400 files (recorded under A-ID2)")
    create_state_directories(kit)
    mint_credentials(kit)
    render_etc(kit)
    ledger(kit, "initialize")
    place_whisper(kit)
    if sha256_file(kit.path("inputs", "jfk.flac")) != sc.JFK_FLAC_SHA256:
        raise sc.Blocked("inputs/jfk.flac does not match its pinned SHA-256")
    (kit.raw / "a-id2.json").write_text(json.dumps(a_id2_rows(kit), indent=2, sort_keys=True) + "\n")
    (kit.raw / "cache-inventory.json").write_text(json.dumps(cache_inventory(kit)))
    print(f"staged {kit.mode} root; credentials: {route}")
    return sc.EXIT_PASS


def staged_pins(kit: Kit) -> dict[str, Any]:
    """The choices stage records and every later subcommand reads back."""

    return {
        "mode": kit.mode, "provider": kit.provider, "lemond_url": kit.lemond_url,
        "chat_model": kit.chat_model, "whisper_model": kit.whisper_model, "slice": kit.slice,
    }


def kit_commit() -> str | None:
    result = run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], check=False)
    return result.stdout.decode().strip() or None if result.returncode == 0 else None


def cmd_up(kit: Kit, args: argparse.Namespace) -> int:
    require_marked(kit)
    state = kit.state()
    revive = not kit.tree.is_dir() and kit.anchor.is_dir()
    if revive:
        if kit.rehearsal:
            raise sc.Blocked("a rehearsal root is never revived")
        revive_from_anchor(kit)
    install_units(kit)
    qdrant_storage = kit.path("state", "qdrant", "storage")
    fresh = not any(qdrant_storage.iterdir())
    qdrant = start_qdrant(kit)
    if revive:
        restore_tuple(kit, qdrant)
    elif fresh:
        qdrant.create_collections()
    for name in ("valkey", "relay", "sampler") + (("stub",) if kit.provider == "stub" else ()):
        systemctl("start", UNITS[name])
    if kit.provider == "stub":
        wait_until(lambda: port_in_use(PORTS["stub"]), 30, "the rehearsal stub")
    if not state.get("commissioned"):
        kit.bootstrap_dropin.parent.mkdir(parents=True, exist_ok=True)
        kit.bootstrap_dropin.write_text(bootstrap_dropin(kit))
        systemctl("daemon-reload")
        started_at = time.time()
        seconds = start_open_webui(kit, timeout=900.0)
        (kit.raw / "first-start.json").write_text(json.dumps(
            {"started_at": started_at, "ready_s": round(seconds, 3), "qdrant_fresh": fresh}, sort_keys=True))
        timing = "" if kit.rehearsal else f" (first start {seconds:.1f} s)"
        print(f"Open WebUI is up with the route closed{timing}; run trial next")
    else:
        start_open_webui(kit)
        start_caddy(kit)
        print("Open WebUI is up behind the acceptance route")
    snapshot_resources(kit, "after up")
    return sc.EXIT_PASS


def revive_from_anchor(kit: Kit) -> None:
    """Rebuild everything ``teardown --keep-anchor`` removed, before ``up`` restores state."""

    anchor = json.loads((kit.anchor / "anchor.json").read_text())
    restage_trees(kit, anchor["archives"])
    remove_tree(kit.credstore)
    shutil.copytree(kit.anchor / "credstore", kit.credstore)
    if kit.credential_route() != "systemd-creds":
        private_credstore(kit.credstore)
    create_state_directories(kit)
    place_whisper(kit)
    render_etc(kit)


def cmd_down(kit: Kit, args: argparse.Namespace) -> int:
    require_marked(kit)
    snapshot_resources(kit, "before down")
    systemctl("stop", UNITS["caddy"], check=False)
    systemctl("stop", kit.slice, check=False)
    print(f"{kit.slice} stopped")
    return sc.EXIT_PASS


def cmd_trial(kit: Kit, args: argparse.Namespace) -> int:
    require_marked(kit)
    state = kit.state()
    if state.get("trial_started"):
        raise sc.Blocked("this root already ran its trial set; X8 allows exactly one")
    if state.get("commissioned") or not (kit.raw / "first-start.json").is_file():
        raise sc.Blocked("run up on a freshly staged root first")
    if not kit.rehearsal and not args.lemonade_receipt:
        raise sc.Blocked("NEEDS LEAD: pass the Lemonade M4 receipt ids with --lemonade-receipt")
    if not unit_active(UNITS["open-webui"]):
        raise sc.Blocked("the acceptance environment is not up")
    lemond_pre = require_lemond_ready(kit)
    kit.save_state(trial_started=True, lemonade_receipts=list(args.lemonade_receipt))
    return Trial(kit, lemond_pre).run()


def cmd_resmoke(kit: Kit, args: argparse.Namespace) -> int:
    require_marked(kit)
    if kit.rehearsal:
        raise sc.Blocked("the rehearsal writes no receipt; resmoke is record mode only")
    receipt = args.receipt or kit.path("evidence", f"resmoke-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
    module = [
        "/usr/bin/python3", str(TOOLS / "open_webui_household_scenarios.py"), "resmoke",
        "--target", "acceptance", "--root", str(kit.root), "--chat-model", kit.chat_model or "",
        "--lemond-url", kit.lemond_url, "--whisper-model", kit.whisper_model,
        "--audio", str(kit.path("inputs", "jfk.flac")), "--receipt", str(receipt),
        "--mode", kit.mode, "--unit", UNITS["open-webui"],
    ]
    for scenario in args.scenario or ["all"]:
        module += ["--scenario", scenario]
    if kit.credential_route() != "systemd-creds":
        result = subprocess.run(module + ["--credentials-dir", str(kit.credstore)], check=False,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return result.returncode
    command = ["systemd-run", "--user", "--wait", "--pipe", "--collect", "--quiet",
               "--setenv=PYTHONDONTWRITEBYTECODE=1"]
    for name in RESMOKE_CREDENTIALS:
        key, value = kit.credential_directive(name)
        command.append(f"--property={key}={value}")
    return subprocess.run(command + module, check=False).returncode


def cmd_teardown(kit: Kit, args: argparse.Namespace) -> int:
    if not kit.path(MARKER).is_file():
        raise sc.Blocked(f"{kit.root} carries no acceptance marker; nothing is removed")
    state = kit.state()
    keep = args.keep_anchor
    if keep and state.get("mode") == "rehearsal":
        print("teardown: a rehearsal root is never kept as an anchor; ignoring --keep-anchor")
        keep = False
    plaintext = state.get("credential_route") != "systemd-creds"
    if keep and plaintext and not args.keep_plaintext_credentials:
        raise sc.Blocked("--keep-anchor refuses to keep plaintext credential files; "
                         "pass --keep-plaintext-credentials to keep the test-only 0400 files")
    if keep and not kit.anchor.is_dir():
        raise sc.Blocked("there is no anchor to keep")
    systemctl("stop", kit.slice, check=False)
    if kit.unit_dir.is_dir():
        for item in kit.unit_dir.glob("owui-acc-*"):
            remove_tree(item) if item.is_dir() else item.unlink()
    systemctl("daemon-reload", check=False)
    systemctl("reset-failed", "owui-acc-*", check=False)
    if kit.socket_path.parent.is_dir():
        remove_tree(kit.socket_path.parent)
    public = sorted(kit.path("evidence", "public").glob("*.json")) if kit.path("evidence", "public").is_dir() else []
    if public and state.get("mode") == "record":
        args.evidence_out.mkdir(parents=True, exist_ok=True)
        for item in public:
            shutil.copy2(item, args.evidence_out / item.name)
            print(f"evidence copied: {item.name}")
    if keep:
        if plaintext and (kit.anchor / "credstore").is_dir():
            private_credstore(kit.anchor / "credstore")
            print("teardown: kept the test-only 0400 credential files in backups/anchor/credstore")
        kept = {MARKER, KIT_STATE, "inputs", "backups", "ledger"}
        for item in kit.root.iterdir():
            if item.name not in kept:
                remove_tree(item) if item.is_dir() else item.unlink()
        print("teardown: kept the marker, kit.json, inputs/, backups/, and the session-epoch ledger")
    else:
        remove_tree(kit.root)
        print("teardown: removed the acceptance root")
    return sc.EXIT_PASS


# ---------------------------------------------------------------------------
# Peer sampler (runs as owui-acc-sampler.service)


def cmd_sample(kit: Kit, args: argparse.Namespace) -> int:
    watched = [unit for unit in kit.units() if unit != UNITS["sampler"]]
    sink = kit.raw / "peers.jsonl"
    sink.parent.mkdir(parents=True, exist_ok=True)
    while True:
        owners = {pid: unit for unit in watched for pid in unit_pids(unit)}
        lines = run(["ss", "-tanpH"], check=False).stdout.decode("utf-8", "replace").splitlines()
        now = time.time()
        with sink.open("a", encoding="utf-8") as output:
            for line in lines:
                parsed = parse_ss_line(line)
                if parsed is None:
                    continue
                units = {owners[pid] for pid in parsed["pids"] if pid in owners}
                for unit in sorted(units):
                    output.write(json.dumps({"t": round(now, 3), "unit": unit, "state": parsed["state"],
                                             "local": parsed["local"], "peer": parsed["peer"]}) + "\n")
        time.sleep(2)


# ---------------------------------------------------------------------------
# CLI


def _default_candidate_store() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "arch-pkgs" / "candidates"


def slice_name(value: str) -> str:
    """A plain slice name with a leaf of its own under a parent slice.

    ``down`` and ``teardown`` stop the whole slice, so a top-level slice such
    as ``builds.slice`` (shared by other lanes' builds) is refused.
    """

    if len(value) > 255 or not _SLICE_NAME.fullmatch(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a plain systemd slice unit name ending in .slice")
    if "-" not in value:
        raise argparse.ArgumentTypeError(
            f"{value!r} is a top-level slice that other units may share; name a dedicated child "
            "such as builds-owui_acc.slice, because down and teardown stop the whole slice"
        )
    return value


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"disposable acceptance root (default {DEFAULT_ROOT})")
    common.add_argument("--manifest", type=Path, help="the candidate manifest of record (name, size, SHA-256, source commit)")
    common.add_argument("--lemond-url", help=f"Lemonade origin (default {sc.DEFAULT_LEMOND_URL}; the stub origin with --provider stub)")
    common.add_argument("--chat-model", help=f"the designated resident chat model; its bare name also matches (default {sc.DEFAULT_CHAT_MODEL})")
    common.add_argument("--embedding-model", help="zembed id to confirm (default: the packaged env)")
    common.add_argument("--reranking-model", help="zerank id to confirm (default: the packaged env)")
    common.add_argument("--whisper-model", choices=tuple(sc.WHISPER_PINS),
                        help=f"pinned Whisper size (default {sc.DEFAULT_WHISPER_MODEL}; tiny only when named)")
    common.add_argument("--provider", choices=("lemond", "stub"), default="lemond")
    common.add_argument("--rehearsal", action="store_true", help="required with --provider stub; writes no evidence")
    common.add_argument("--candidate-store", type=Path, default=_default_candidate_store(),
                        help="where preflight and stage look for the pinned archives (default: the arch-pkgs candidate store)")
    common.add_argument("--slice", type=slice_name,
                        help=f"user slice the kit units run under; stage records it (default {SLICE}; "
                             "builds-owui_acc.slice nests under builds.slice)")

    top = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = top.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", parents=[common], help="read-only checks")
    preflight.add_argument("--probe-only", action="store_true", help="check only what needs no approved download")
    commands.add_parser("stage", parents=[common], help="extract, render, mint, initialize")
    commands.add_parser("up", parents=[common], help="start the kit slice")
    commands.add_parser("down", parents=[common], help="stop the kit slice")
    trial = commands.add_parser("trial", parents=[common], help="the one trial set, then evidence")
    trial.add_argument("--lemonade-receipt", action="append", default=[], metavar="ID",
                       help="an arch-strix-halo-pkgs M4 receipt id bound into the evidence (repeatable)")
    resmoke = commands.add_parser("resmoke", parents=[common], help="the open-webui.resmoke.* scenarios on the acceptance route")
    resmoke.add_argument("--scenario", action="append", default=[], help="scenario id or all (default all)")
    resmoke.add_argument("--receipt", type=Path, help="receipt path (default under <root>/evidence/)")
    teardown = commands.add_parser("teardown", parents=[common], help="stop, remove units, remove the marked root")
    teardown.add_argument("--keep-anchor", action="store_true", help="keep backups/anchor and inputs for a later re-smoke")
    teardown.add_argument("--keep-plaintext-credentials", action="store_true",
                          help="with --keep-anchor in record mode: keep the test-only 0400 credential files "
                               "that stage used because systemd-creds --user was unavailable")
    teardown.add_argument("--evidence-out", type=Path, default=REPO_ROOT / "docs" / "maintainers" / "evidence",
                          help="where record-mode public evidence is copied")
    commands.add_parser("_sample", parents=[common], help=argparse.SUPPRESS)
    return top


def kit_from_args(args: argparse.Namespace) -> Kit:
    if (args.provider == "stub") != args.rehearsal:
        raise ValueError("--provider stub and --rehearsal go together")
    if getattr(args, "keep_plaintext_credentials", False) and not args.keep_anchor:
        raise ValueError("--keep-plaintext-credentials is valid only with --keep-anchor")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise sc.Blocked("XDG_RUNTIME_DIR is unset; the kit needs a user manager session")
    root = Path(os.path.realpath(args.root))
    staged: dict[str, Any] = {}
    if (root / KIT_STATE).is_file():
        staged = json.loads((root / KIT_STATE).read_text())
    lemond_url = args.lemond_url or staged.get("lemond_url") or (STUB_URL if args.provider == "stub" else sc.DEFAULT_LEMOND_URL)
    if args.provider == "stub" and lemond_url != STUB_URL:
        raise ValueError(f"the rehearsal provider is the stub at {STUB_URL}")
    for flag, field in (("--chat-model", "chat_model"), ("--whisper-model", "whisper_model"), ("--slice", "slice")):
        given, pinned = getattr(args, field), staged.get(field)
        if given and pinned and given != pinned:
            raise ValueError(f"{flag} differs from the staged {pinned}; tear down and restage")
    chat_model = args.chat_model or staged.get("chat_model") or (
        "household-chat-stub-v1" if args.provider == "stub" else sc.DEFAULT_CHAT_MODEL
    )
    whisper_model = args.whisper_model or staged.get("whisper_model") or sc.DEFAULT_WHISPER_MODEL
    slice_unit = args.slice or staged.get("slice") or SLICE
    try:
        slice_name(slice_unit)
    except argparse.ArgumentTypeError as error:
        raise ValueError(str(error)) from None
    return Kit(
        root=root,
        manifest_path=args.manifest,
        provider=args.provider,
        rehearsal=args.rehearsal,
        lemond_url=lemond_url,
        chat_model=chat_model,
        embedding_model=args.embedding_model,
        reranking_model=args.reranking_model,
        whisper_model=whisper_model,
        candidate_store=args.candidate_store,
        runtime_dir=Path(runtime),
        slice=slice_unit,
    )


COMMANDS: Mapping[str, Callable[[Kit, argparse.Namespace], int]] = MappingProxyType(
    {
        "preflight": cmd_preflight,
        "stage": cmd_stage,
        "up": cmd_up,
        "down": cmd_down,
        "trial": cmd_trial,
        "resmoke": cmd_resmoke,
        "teardown": cmd_teardown,
        "_sample": cmd_sample,
    }
)


def main(argv: list[str] | None = None) -> int:
    top = parser()
    args = top.parse_args(argv)
    try:
        kit = kit_from_args(args)
    except ValueError as error:
        top.error(str(error))
    try:
        return COMMANDS[args.command](kit, args)
    except sc.Blocked as error:
        print(f"accept-open-webui-household: BLOCKED {error}", file=sys.stderr)
        return sc.EXIT_PRECONDITION
    except sc.Escalation as error:
        print(f"accept-open-webui-household: {error}", file=sys.stderr)
        return sc.EXIT_ESCALATE
    except STEP_FAILURES as error:
        print(f"accept-open-webui-household: {type(error).__name__}: {error}", file=sys.stderr)
        return sc.EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
