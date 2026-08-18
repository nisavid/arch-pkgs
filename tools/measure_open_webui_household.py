#!/usr/bin/env python3
"""Disposable Open WebUI household-envelope fixture and evidence contract.

The executable surface is intentionally plan-only: every declared input is
hashed before a plan is emitted, and runtime execution is not exposed yet.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


MIB = 1024 * 1024
ACCEPTED_UPLOAD_MIB = 250
ACCEPTED_UPLOAD_SIZE = ACCEPTED_UPLOAD_MIB * MIB
REJECTED_UPLOAD_SIZE = ACCEPTED_UPLOAD_SIZE + 1
EMBEDDING_CANARY_MINIMUM_COSINE_MARGIN = 0.20
EMBEDDING_CANARY_UNIT_NORM_TOLERANCE = 0.001

COLLECTIONS = [
    "open-webui-rag-v1_memories",
    "open-webui-rag-v1_knowledge",
    "open-webui-rag-v1_files",
    "open-webui-rag-v1_web-search",
    "open-webui-rag-v1_hash-based",
]

CONTRACT: dict[str, Any] = {
    "schema": "open-webui-household-envelope-contract/v1",
    "execution": {"mode": "plan-only", "measured_finalization": False},
    "authority": {
        "issue_66": "https://github.com/nisavid/arch-pkgs/issues/66#issuecomment-5327054348",
        "issue_67": "https://github.com/nisavid/arch-pkgs/issues/67#issuecomment-5332310242",
        "issue_68": "https://github.com/nisavid/arch-pkgs/issues/68",
        "prototype_commit": "6063df80ff34e91f642f3bd98cd5fec9418d4bd5",
        "prototype_sha256": "3664ccc0c736920c645bb730cf60ef35d4369585d41d6621cf09527252d562d7",
    },
    "open_webui": {
        "version": "0.11.0",
        "commit": "f9590b8017199e56d5e953657e6498e3cef1d246",
        "sdist_sha256": "e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9",
        "wheel_sha256": "71c266be87d0fb2cd79d9172d0e86a3b1b59d550d7054622b831344df07d361b",
        "alembic_head": "f0bd01a18a3d",
        "fresh_state": True,
        "transport": "unix-socket-only",
    },
    "qdrant": {
        "version": "1.19.0",
        "accepted_package_sha256": "15f15fe2c0c774691bf3193bc8fc7883fa530c89db697f7c0bcc2720d231b011",
        "collections": COLLECTIONS,
        "dimensions": 2560,
        "distance": "Cosine",
        "payload_indexes": ["tenant_id", "metadata.hash", "metadata.file_id"],
        "runtime_role": "prw",
    },
    "providers": {
        "shape": "direct-patched-lemonade",
        "embedding_model": "zembed-1-Q4_K_M-GGUF-Q4_K_M",
        "embedding_artifact": {
            "repository": "Abiray/zembed-1-Q4_K_M-GGUF",
            "revision": "c1fed1b47f407fdf5ceb25d6919ac7e5237151c9",
            "filename": "zembed-1-Q4_K_M.gguf",
            "size_bytes": 2497280960,
            "sha256": "3098f7963ca0563e8b39a55ee09a53697e57e49be5b9082892739bf24e075836",
        },
        "embedding_pooling": {
            "strategy": "last-token",
            "llama_cpp_value": "last",
            "gguf_metadata": {"key": "qwen3.pooling_type", "value": 3},
            "required_arguments": ["--embedding", "--pooling", "last"],
        },
        "embedding_canary": {
            "dimensions": 2560,
            "minimum_cosine_margin": EMBEDDING_CANARY_MINIMUM_COSINE_MARGIN,
            "unit_norm_absolute_tolerance": EMBEDDING_CANARY_UNIT_NORM_TOLERANCE,
        },
        "reranking_model": "zerank-2-GGUF-Q8_0",
        "reranking_artifact": {
            "repository": "mradermacher/zerank-2-GGUF",
            "revision": "c3c0d69a75b8dad9f56e99aec416d6aff12b85c7",
            "filename": "zerank-2.Q8_0.gguf",
            "size_bytes": 4280405664,
            "sha256": "7b9ba05a0509151c911582a4d62b14003f6a4fafa0e7ccdf572c7598cde1c100",
        },
        "measured_llama_cpp_runtime": {
            "package": "llama.cpp-hip-gfx1151",
            "version": "b9442-1",
            "reported_build": "version 459 (baffb2e)",
            "executable_size_bytes": 7672,
            "executable_sha256": "9d3b6e271548ec85a67951c86a48f131e306d152c22e79266d050a240a9f2f78",
            "server_impl_size_bytes": 9478760,
            "server_impl_sha256": "6c93a4a9bfaa11065d89760142bcf8ce5761147ebe0c65221e09a4ad9e99215b",
            "complete_dynamic_closure_bound": False,
        },
        "embedding_batch_size": 1,
        "embedding_concurrency": 1,
        "rerank_fanout": 3,
        "canaries_after_every_start": True,
    },
    "state": {
        "sqlite": "fresh-local-wal",
        "valkey": "dedicated-noeviction-persistent",
        "session_epoch": "external-forward-only-non-restored",
        "rollback": "whole-compatible-tuple",
    },
    "accepted_inputs_not_policy_outputs": {
        "maximum_file_mib": ACCEPTED_UPLOAD_MIB,
        "maximum_files_per_operation": 25,
    },
}

REQUIRED_INPUTS: dict[str, dict[str, Any]] = {
    "open_webui_sdist": {
        "size_bytes": 49568784,
        "sha256": CONTRACT["open_webui"]["sdist_sha256"],
    },
    "open_webui_wheel": {
        "size_bytes": 145492176,
        "sha256": CONTRACT["open_webui"]["wheel_sha256"],
    },
    "qdrant_package": {
        "size_bytes": 28018464,
        "sha256": CONTRACT["qdrant"]["accepted_package_sha256"],
    },
    "caddy_package": {
        "size_bytes": 14660413,
        "sha256": "65a2fb6ea32f9d8313944b443c164b923092db0e3aa320321e1ca518ec8c0f1a",
    },
    "valkey_package": {
        "size_bytes": 1465234,
        "sha256": "599177b7843027b58296b50e9f2302f438212365e51029f36dbd3f19385a64dd",
    },
    "zembed_gguf": copy.deepcopy(CONTRACT["providers"]["embedding_artifact"]),
    "zerank_gguf": copy.deepcopy(CONTRACT["providers"]["reranking_artifact"]),
    "llama_server_executable": {
        "size_bytes": 7672,
        "sha256": CONTRACT["providers"]["measured_llama_cpp_runtime"][
            "executable_sha256"
        ],
    },
    "llama_server_impl": {
        "size_bytes": 9478760,
        "sha256": CONTRACT["providers"]["measured_llama_cpp_runtime"][
            "server_impl_sha256"
        ],
    },
    "provider_fixture": {
        "size_bytes": 17870,
        "sha256": "82d35955227f955f2fc6e4a62fd0284f2163a68b6b2d3587de05dd11fd5a5b6b",
    },
    "open_webui_pristine_init": {
        "size_bytes": 3266,
        "sha256": "11cd2fad929db12c687795239ab3b6af1b5ea6f3ad7363deedfabf9651dd22d4",
    },
    "open_webui_uds_patch": {
        "size_bytes": 1568,
        "sha256": "ab095e77ba03ce3244ee44397c4bb84b09cdf0638a13c3ff317f63752c4d796a",
    },
}

MEASURED_REQUIRED_ARTIFACTS = frozenset(
    {
        "open_webui_sdist",
        "open_webui_wheel",
        "qdrant_package",
        "caddy_package",
        "valkey_package",
        "zembed_gguf",
        "zerank_gguf",
        "lemonade_package",
        "llama_cpp_package",
    }
)
MEASURED_CONTRACT_OWNED_ARTIFACTS = frozenset(
    {
        "open_webui_sdist",
        "open_webui_wheel",
        "qdrant_package",
        "caddy_package",
        "valkey_package",
        "zembed_gguf",
        "zerank_gguf",
    }
)
MEASURED_REQUIRED_EVIDENCE_ROLES = frozenset(
    {
        "execution_recipe",
        "run_receipt",
        "raw_samples",
        "backup_manifest",
        "cleanup_receipt",
    }
)
MEASURED_REQUIRED_CONFIG = {
    "open_webui_transport": "unix-socket-only",
    "qdrant_dimensions": 2560,
    "qdrant_distance": "Cosine",
    "qdrant_runtime_role": "prw",
    "provider_shape": "direct-patched-lemonade",
}
MEASURED_PUBLIC_SAFETY = {
    "synthetic_identities_only": True,
    "private_paths_included": False,
    "private_hostnames_or_addresses_included": False,
    "credentials_or_headers_included": False,
    "raw_logs_included": False,
    "production_data_included": False,
}

REQUIRED_OBLIGATIONS = [
    "exact_subject_identity",
    "fresh_schema_head",
    "unix_socket_only",
    "five_collection_schema",
    "scoped_qdrant_runtime_authority",
    "embedding_semantic_canary",
    "reranking_semantic_canary",
    "private_owner_retrieval",
    "explicit_sharing_and_revocation",
    "anonymous_denial_before_lookup",
    "accepted_and_rejected_upload_boundaries",
    "failed_index_has_no_stale_vector_or_citation",
    "reranker_failure_isolates_rag",
    "websocket_sse_and_long_response",
    "whole_runtime_restore",
    "versioned_generation_rollback",
    "old_session_rejection",
    "no_live_state_contact",
    "no_unexpected_egress",
    "runtime_quiescence_cleanup",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _minimal_pdf_bytes(title: str, body: str) -> bytes:
    """Return a deterministic, born-digital one-page PDF."""

    escaped = body.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Title ({title}) >>".encode("ascii"),
    ]
    output = bytearray(b"%PDF-1.4\n% household measurement fixture\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _portable_graymap_bytes() -> bytes:
    width, height = 128, 32
    pixels = bytearray()
    seed = hashlib.sha256(b"Winter Garden Handbook scan fixture").digest()
    for y in range(height):
        for x in range(width):
            pixels.append(32 if seed[(x + y) % len(seed)] & (1 << (x % 8)) else 240)
    return f"P5\n{width} {height}\n255\n".encode() + bytes(pixels)


def _small_fixture_files() -> list[tuple[str, bytes]]:
    handbook = (
        "# Winter Garden Handbook\n\n"
        "## 1. Beds\nKeep paths clear.\n\n"
        "## 2. Seeds\nLabel every tray.\n\n"
        "## 3. Seed cabinet\nThe brass key opens the seed cabinet.\n"
    ).encode()
    files: list[tuple[str, bytes]] = [
        ("documents/winter-garden-handbook.md", handbook),
        (
            "documents/winter-garden-handbook.pdf",
            _minimal_pdf_bytes(
                "Winter Garden Handbook",
                "Section 3: The brass key opens the seed cabinet.",
            ),
        ),
        ("documents/winter-garden-scan.pgm", _portable_graymap_bytes()),
    ]
    for index in range(1, 23):
        body = (
            f"# Household reference {index:02d}\n\n"
            f"Synthetic measurement marker: reference-{index:02d}.\n"
            "This document contains no private or production data.\n"
        ).encode()
        files.append((f"documents/reference-{index:02d}.md", body))
    return files


@lru_cache(maxsize=4)
def _repeated_payload_sha256(size: int, byte: int) -> str:
    digest = hashlib.sha256()
    chunk = bytes([byte]) * MIB
    remaining = size
    while remaining:
        current = chunk if remaining >= len(chunk) else chunk[:remaining]
        digest.update(current)
        remaining -= len(current)
    return digest.hexdigest()


def _write_repeated_payload(path: Path, size: int, byte: int) -> None:
    chunk = bytes([byte]) * MIB
    remaining = size
    with path.open("wb") as output:
        while remaining:
            current = chunk if remaining >= len(chunk) else chunk[:remaining]
            output.write(current)
            remaining -= len(current)


def generate_fixture(root: Path, *, materialize_heavy: bool) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    manifest_items: list[dict[str, Any]] = []
    small_files = _small_fixture_files()
    for name, data in small_files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest_items.append(
            {"name": name, "size": len(data), "sha256": _sha256_bytes(data), "materialized": True}
        )

    heavy = [
        ("boundaries/accepted-250-mib.bin", ACCEPTED_UPLOAD_SIZE, 0x41, "accepted_file"),
        ("boundaries/rejected-250-mib-plus-one.bin", REJECTED_UPLOAD_SIZE, 0x52, "rejected_file"),
    ]
    heavy_records: dict[str, dict[str, Any]] = {}
    for name, size, byte, key in heavy:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if materialize_heavy:
            _write_repeated_payload(path, size, byte)
        record = {
            "name": name,
            "size": size,
            "sha256": _repeated_payload_sha256(size, byte),
            "materialized": materialize_heavy,
        }
        heavy_records[key] = record
        manifest_items.append(record)

    accepted_batch = {"files": [name for name, _ in small_files]}
    rejected_batch = {
        "files": [name for name, _ in small_files]
        + ["documents/rejected-extra-reference.md"]
    }
    for name, value in (
        ("boundaries/accepted-batch.json", accepted_batch),
        ("boundaries/rejected-batch.json", rejected_batch),
    ):
        data = _canonical_json_bytes(value)
        path = root / name
        path.write_bytes(data)
        manifest_items.append(
            {"name": name, "size": len(data), "sha256": _sha256_bytes(data), "materialized": True}
        )

    manifest_items.sort(key=lambda item: item["name"])
    return {
        "schema": "open-webui-household-fixture/v1",
        "corpus_id": "open-webui-household-measurement-v1",
        "principals": {
            "administrator": "admin@household.invalid",
            "users": ["alex@household.invalid", "blair@household.invalid", "casey@household.invalid"],
            "group": {"name": "Gardeners", "members": ["blair@household.invalid"]},
        },
        "canonical_fact": "The brass key opens the seed cabinet.",
        "canonical_query": "Which key opens the seed cabinet?",
        "canonical_citation": "Winter Garden Handbook § 3",
        "small_file_count": len(small_files),
        "accepted_batch_count": len(accepted_batch["files"]),
        "rejected_batch_count": len(rejected_batch["files"]),
        "accepted_file": heavy_records["accepted_file"],
        "rejected_file": heavy_records["rejected_file"],
        "files": manifest_items,
    }


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def deterministic_embedding(text: str, *, input_type: str) -> list[float]:
    if input_type not in {"query", "document"}:
        raise ValueError("input_type must be query or document")
    vector = [0.0] * 2560
    for token in sorted(_tokens(text)):
        token_digest = hashlib.sha256(token.encode()).digest()
        index = 2 + int.from_bytes(token_digest[:4], "big") % 2558
        vector[index] += 1.0
    vector[0 if input_type == "query" else 1] = 0.05
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("embedding input must contain a token")
    return [value / norm for value in vector]


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def embedding_canary_passes(
    query: list[float], matching: list[float], unrelated: list[float]
) -> bool:
    vectors = (query, matching, unrelated)
    norms = [math.sqrt(sum(value * value for value in vector)) for vector in vectors]
    return (
        all(len(vector) == 2560 for vector in vectors)
        and all(math.isfinite(value) for vector in vectors for value in vector)
        and all(
            math.isclose(
                norm,
                1.0,
                abs_tol=EMBEDDING_CANARY_UNIT_NORM_TOLERANCE,
            )
            for norm in norms
        )
        and _cosine(query, matching) - _cosine(query, unrelated)
        >= EMBEDDING_CANARY_MINIMUM_COSINE_MARGIN
    )


def deterministic_rerank(query: str, documents: list[str]) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    scored: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        document_tokens = _tokens(document)
        overlap = len(query_tokens & document_tokens) / max(1, len(query_tokens))
        score = overlap + (0.25 if "paris" in document_tokens and "france" in query_tokens else 0.0)
        scored.append({"index": index, "score": float(score)})
    return sorted(scored, key=lambda item: (-item["score"], item["index"]))


def new_evidence_manifest() -> dict[str, Any]:
    return {
        "schema": "open-webui-household-envelope/v1",
        "disposition": "incomplete",
        "scope": "Disposable measurement evidence; not package or production acceptance.",
        "contract_refs": copy.deepcopy(CONTRACT["authority"]),
        "subject": {"integrated_provider": False, "artifacts": {}, "configs": {}},
        "environment": {},
        "fixture": {},
        "protocol": {},
        "observations": {},
        "obligations": [
            {"id": obligation, "status": "pending"} for obligation in REQUIRED_OBLIGATIONS
        ],
        "limitations": [],
        "cleanup": {},
        "public_safety": {},
        "evidence_files": [],
    }


def minimum_complete_observations() -> dict[str, list[dict[str, Any]]]:
    def samples(count: int, scenario: str, concurrency: int = 1) -> list[dict[str, Any]]:
        return [
            {
                "scenario": scenario,
                "repetition": index + 1,
                "concurrency": concurrency,
                "duration_seconds": (index + 1) / 1000,
            }
            for index in range(count)
        ]

    return {
        "fresh_start": samples(5, "fresh_start"),
        "restart": samples(5, "restart"),
        "restore": samples(5, "restore"),
        "rollback": samples(5, "rollback"),
        "heavy_upload_index": samples(3, "heavy_upload_index"),
        "generation_rebuild": samples(3, "generation_rebuild"),
        "query_concurrency_1": samples(30, "query", 1),
        "query_concurrency_3": samples(30, "query", 3),
    }


_SAMPLE_CONTRACTS = {
    "fresh_start": (5, "fresh_start", 1),
    "restart": (5, "restart", 1),
    "restore": (5, "restore", 1),
    "rollback": (5, "rollback", 1),
    "heavy_upload_index": (3, "heavy_upload_index", 1),
    "generation_rebuild": (3, "generation_rebuild", 1),
    "query_concurrency_1": (30, "query", 1),
    "query_concurrency_3": (30, "query", 3),
}


def _identity_record_valid(record: Any) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("size_bytes"), int)
        and not isinstance(record.get("size_bytes"), bool)
        and record["size_bytes"] > 0
        and isinstance(record.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is not None
    )


def _evidence_file_valid(record: Any) -> bool:
    if not _identity_record_valid(record):
        return False
    role = record.get("role")
    if not isinstance(role, str) or not role:
        return False
    path_value = record.get("path")
    if not isinstance(path_value, str) or not path_value:
        return False
    path = Path(path_value)
    return not path.is_absolute() and ".." not in path.parts


def _sample_records_valid(
    records: Any, minimum: int, scenario: str, concurrency: int
) -> bool:
    if not isinstance(records, list) or len(records) < minimum:
        return False
    repetitions: set[int] = set()
    for record in records:
        if not isinstance(record, dict):
            return False
        repetition = record.get("repetition")
        duration = record.get("duration_seconds")
        if (
            record.get("scenario") != scenario
            or isinstance(record.get("concurrency"), bool)
            or record.get("concurrency") != concurrency
            or isinstance(repetition, bool)
            or not isinstance(repetition, int)
            or repetition < 1
            or repetition in repetitions
            or isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
            or duration <= 0
        ):
            return False
        repetitions.add(repetition)
    return True


def finalize_evidence(manifest: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(manifest)
    raw_limitations = result.get("limitations", [])
    limitations = (
        list(raw_limitations)
        if isinstance(raw_limitations, list)
        and all(isinstance(item, str) for item in raw_limitations)
        else ["manifest structure is malformed"]
    )
    subject = result.get("subject", {})
    if not isinstance(subject, dict):
        subject = {}
        limitations.append("manifest structure is malformed")
    if subject.get("integrated_provider") is not True:
        limitations.append("exact integrated provider evidence is absent")
    obligations = result.get("obligations", [])
    obligations_well_formed = isinstance(obligations, list) and all(
        isinstance(item, dict) and isinstance(item.get("id"), str)
        for item in obligations
    )
    obligation_ids = (
        [item["id"] for item in obligations] if obligations_well_formed else []
    )
    if (
        not obligations_well_formed
        or len(obligation_ids) != len(REQUIRED_OBLIGATIONS)
        or set(obligation_ids) != set(REQUIRED_OBLIGATIONS)
    ):
        limitations.append("obligation contract does not match the required exact set")
    else:
        failed = [
            item["id"] for item in obligations if item.get("status") != "pass"
        ]
        if failed:
            limitations.append("non-passing obligations: " + ", ".join(failed))

    artifacts = subject.get("artifacts", {})
    if (
        not isinstance(artifacts, dict)
        or not MEASURED_REQUIRED_ARTIFACTS.issubset(artifacts)
        or any(
            not _identity_record_valid(artifacts.get(name))
            for name in MEASURED_REQUIRED_ARTIFACTS
        )
    ):
        limitations.append("measured subject artifact identities are incomplete")
    elif any(
        artifacts[name].get("size_bytes") != REQUIRED_INPUTS[name]["size_bytes"]
        or artifacts[name].get("sha256") != REQUIRED_INPUTS[name]["sha256"]
        for name in MEASURED_CONTRACT_OWNED_ARTIFACTS
    ):
        limitations.append("measured subject artifacts differ from the contract-owned inputs")

    configs = subject.get("configs", {})
    config_manifest = configs.get("manifest_sha256") if isinstance(configs, dict) else None
    if (
        not isinstance(configs, dict)
        or any(configs.get(name) != value for name, value in MEASURED_REQUIRED_CONFIG.items())
        or not isinstance(config_manifest, str)
        or re.fullmatch(r"[0-9a-f]{64}", config_manifest) is None
    ):
        limitations.append("measured subject configuration identity is incomplete")

    evidence_files = result.get("evidence_files", [])
    valid_evidence = (
        [item for item in evidence_files if _evidence_file_valid(item)]
        if isinstance(evidence_files, list)
        else []
    )
    evidence_roles = [item.get("role") for item in valid_evidence]
    if (
        not isinstance(evidence_files, list)
        or len(valid_evidence) != len(evidence_files)
        or len(evidence_roles) != len(set(evidence_roles))
        or not MEASURED_REQUIRED_EVIDENCE_ROLES.issubset(evidence_roles)
    ):
        limitations.append("digest-bound execution evidence is incomplete")

    public_safety = result.get("public_safety", {})
    if (
        not isinstance(public_safety, dict)
        or any(public_safety.get(name) is not value for name, value in MEASURED_PUBLIC_SAFETY.items())
    ):
        limitations.append("public-safety disposition is incomplete")
    try:
        assert_public_safe(result)
    except (TypeError, ValueError):
        limitations.append("public-safety validation failed")

    observations = result.get("observations", {})
    for name, (minimum, scenario, concurrency) in _SAMPLE_CONTRACTS.items():
        records = observations.get(name) if isinstance(observations, dict) else None
        if not isinstance(records, list) or len(records) < minimum:
            limitations.append(f"sample floor not met for {name}: need {minimum}")
        elif not _sample_records_valid(records, minimum, scenario, concurrency):
            limitations.append(f"sample contract not met for {name}")
    result["limitations"] = sorted(set(limitations))
    result["limitations"] = sorted(
        set(
            result["limitations"]
            + ["measured finalization is unavailable in plan-only mode"]
        )
    )
    result["disposition"] = "incomplete"
    return result


_ABSOLUTE_PRIVATE_PATH = re.compile(
    r"(?:^|[\s\"'])/(?:home|root|tmp|mnt|media)(?:/|$)"
)
_PRIVATE_IPV4 = re.compile(
    r"\b(?:127\.\d{1,3}\.\d{1,3}\.\d{1,3}|169\.254\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
)
_PRIVATE_IPV6 = re.compile(
    r"(?i)(?<![0-9a-f:])(?:(?:f[cd][0-9a-f]{2}|fe[89ab][0-9a-f]):[0-9a-f:]+|::1)(?![0-9a-f:])"
)
_PRIVATE_HOSTNAME = re.compile(
    r"(?i)\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:lan|local|internal|home|corp)\b"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:token|password|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+"
)
_AUTHENTICATION_MATERIAL = re.compile(
    r"(?:-----BEGIN [A-Z0-9 ]+-----|(?i:\bbearer\s+[^\s\",;}]+|\b(?:set-)?cookie\s*:|\bauthorization\s*:))"
)
_SECRET_FIELD_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "bearer",
        "cookie",
        "password",
        "secret",
        "set_cookie",
        "token",
    }
)


def _contains_secret_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _SECRET_FIELD_NAMES or normalized.endswith(
                ("_password", "_secret", "_api_key")
            ) or (normalized.endswith("_token") and normalized != "selected_token"):
                return True
            if _contains_secret_field(item):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_field(item) for item in value)
    return False


def assert_public_safe(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    if _ABSOLUTE_PRIVATE_PATH.search(serialized):
        raise ValueError("public evidence contains an absolute private path")
    if _PRIVATE_IPV4.search(serialized):
        raise ValueError("public evidence contains a private network address")
    if _PRIVATE_IPV6.search(serialized):
        raise ValueError("public evidence contains a private IPv6 address")
    if _PRIVATE_HOSTNAME.search(serialized):
        raise ValueError("public evidence contains a private hostname")
    if _SECRET_ASSIGNMENT.search(serialized):
        raise ValueError("public evidence contains secret-like material")
    if _AUTHENTICATION_MATERIAL.search(serialized):
        raise ValueError("public evidence contains authentication material")
    if _contains_secret_field(value):
        raise ValueError("public evidence contains a secret-valued field")
    for match in _EMAIL.finditer(serialized):
        if match.group(1).lower() != "household.invalid":
            raise ValueError("public evidence contains a non-fixture email address")


def _parse_assignments(values: list[str], flag: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{flag} requires NAME=VALUE")
        name, assigned = value.split("=", 1)
        if not name or name in parsed:
            raise ValueError(f"{flag} has an empty or duplicate name")
        parsed[name] = assigned
    return parsed


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(MIB), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_inputs(inputs: dict[str, str]) -> dict[str, Any]:
    if set(inputs) != set(REQUIRED_INPUTS):
        raise ValueError("input names must match the contract-owned required set exactly")
    records: dict[str, Any] = {}
    for name in sorted(inputs):
        path = Path(inputs[name])
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"input {name} is not a regular non-symlink file")
        actual = _file_sha256(path)
        expected = REQUIRED_INPUTS[name]
        if actual != expected["sha256"]:
            raise ValueError(
                f"digest mismatch for {name}: expected {expected['sha256']}, got {actual}"
            )
        actual_size = path.stat().st_size
        if actual_size != expected["size_bytes"]:
            raise ValueError(
                f"size mismatch for {name}: expected {expected['size_bytes']}, got {actual_size}"
            )
        records[name] = {"sha256": actual, "size_bytes": actual_size}
    return records


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", required=True)
    parser.add_argument("--input", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--work-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        inputs = _parse_assignments(args.input, "--input")
        records = _validate_inputs(inputs)
        print(
            json.dumps(
                {
                    "schema": "open-webui-household-envelope-plan/v1",
                    "contract": CONTRACT,
                    "inputs": records,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"measure-open-webui-household: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
