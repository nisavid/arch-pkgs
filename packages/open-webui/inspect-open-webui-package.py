#!/usr/bin/python
"""Inspect an Open WebUI Arch package without extracting its payload."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

SCHEMA = "arch-pkgs.open-webui.package-inspection.v1"
GENERIC_BUILD_PATHS = {"/build", "/tmp", "/var/tmp"}
PYODIDE_PREFIX = "open_webui/frontend/pyodide/"
CRITICAL_FILES = (
    "etc/open-webui/open-webui.env",
    "usr/bin/open-webui",
    "usr/lib/systemd/system/open-webui.service",
    "usr/lib/sysusers.d/open-webui.conf",
    "usr/lib/tmpfiles.d/open-webui.conf",
    "usr/lib/open-webui/open-webui-commission-admin",
    "usr/lib/open-webui/open-webui-session-epoch-ledger",
    "opt/open-webui/lib/python3.14/site-packages/open_webui/retrieval/rag_gate.py",
    "opt/open-webui/lib/python3.14/site-packages/open_webui/utils/session_epoch.py",
    "usr/share/licenses/open-webui/LICENSE",
    "usr/share/licenses/open-webui/LICENSE_HISTORY",
    "usr/share/licenses/open-webui/LICENSE_NOTICE",
)
PROVIDER_ROOTS = {
    "accelerate": ("accelerate",),
    "av": ("av",),
    "ctranslate2": ("ctranslate2",),
    "faster-whisper": ("faster_whisper",),
    "numpy": ("numpy",),
    "onnxruntime": ("onnxruntime",),
    "opencv-python": ("cv2",),
    "opencv-python-headless": ("cv2",),
    "pandas": ("pandas",),
    "pillow": ("PIL",),
    "pyarrow": ("pyarrow",),
    "pyclipper": ("pyclipper",),
    "rapidocr": ("rapidocr",),
    "scikit-learn": ("sklearn",),
    "scipy": ("scipy",),
    "sentence-transformers": ("sentence_transformers",),
    "sentencepiece": ("sentencepiece", "_sentencepiece"),
    "shapely": ("shapely",),
    "tokenizers": ("tokenizers",),
    "torch": ("torch", "torchgen"),
    "transformers": ("transformers",),
}


class InspectionError(RuntimeError):
    """The archive cannot produce an accepted inspection receipt."""


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def normalized_path(name: str) -> str | None:
    if not name or name.startswith(("/", "\\")) or "\\" in name:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        return None
    raw_parts = name.rstrip("/").split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        return None
    path = PurePosixPath(*raw_parts)
    normalized = path.as_posix()
    if normalized in {"", "."}:
        return None
    return normalized


def member_type(member: tarfile.TarInfo) -> str:
    if member.isfile():
        return "file"
    if member.isdir():
        return "directory"
    if member.issym():
        return "symlink"
    if member.islnk():
        return "hardlink"
    return "other"


def parse_build_value(body: bytes, key: str) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InspectionError(".BUILDINFO is not UTF-8") from error
    values = [
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if line.split("=", 1)[0].strip() == key and "=" in line
    ]
    if len(values) != 1:
        raise InspectionError(f".BUILDINFO must contain exactly one {key}")
    return values[0]


def parse_pkginfo(body: bytes) -> dict[str, object]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InspectionError(".PKGINFO is not UTF-8") from error
    values: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (item.strip() for item in line.split("=", 1))
        values.setdefault(key, []).append(value)

    def one(key: str) -> str:
        matches = values.get(key, [])
        if len(matches) != 1:
            raise InspectionError(f".PKGINFO must contain exactly one {key}")
        return matches[0]

    package_name = one("pkgname")
    package_base = one("pkgbase")
    package_version = one("pkgver")
    architecture = one("arch")
    if package_name != "open-webui" or package_base != "open-webui":
        raise InspectionError(".PKGINFO does not describe the Open WebUI package")
    if architecture != "x86_64" or not package_version:
        raise InspectionError(".PKGINFO has an unexpected package identity")
    try:
        installed_size = int(one("size"), 10)
        build_timestamp = int(one("builddate"), 10)
    except ValueError as error:
        raise InspectionError(".PKGINFO size/builddate are not integers") from error
    if installed_size < 0 or build_timestamp < 0:
        raise InspectionError(".PKGINFO size/builddate must be non-negative")
    return {
        "architecture": architecture,
        "build_timestamp": build_timestamp,
        "installed_size_bytes": installed_size,
        "package_base": package_base,
        "package_name": package_name,
        "package_version": package_version,
    }


def parse_buildinfo_identity(body: bytes) -> dict[str, str]:
    package_version = parse_build_value(body, "pkgver")
    architecture = parse_build_value(body, "pkgarch")
    pkgbuild_sha256 = parse_build_value(body, "pkgbuild_sha256sum")
    if architecture != "x86_64" or not package_version:
        raise InspectionError(".BUILDINFO has an unexpected package identity")
    if re.fullmatch(r"[0-9a-f]{64}", pkgbuild_sha256) is None:
        raise InspectionError(".BUILDINFO pkgbuild_sha256sum is not canonical SHA-256")
    return {
        "architecture": architecture,
        "package_version": package_version,
        "pkgbuild_sha256": pkgbuild_sha256,
    }


def decode_mtree(body: bytes) -> bytes:
    try:
        return gzip.decompress(body)
    except (OSError, EOFError) as error:
        raise InspectionError(".MTREE is not a valid gzip stream") from error


def load_providers() -> list[str]:
    provider_file = Path(__file__).with_name("open-webui-system-providers.txt")
    providers = provider_file.read_text(encoding="utf-8").splitlines()
    if len(providers) != 21 or providers != sorted(set(providers)):
        raise InspectionError("system-provider list is not the audited 21-name set")
    if set(providers) != set(PROVIDER_ROOTS):
        raise InspectionError("system-provider roots do not cover the audited set")
    return providers


def site_packages_prefix(paths: list[str]) -> str:
    matches = {
        "/".join(PurePosixPath(path).parts[:5]) + "/"
        for path in paths
        if len(PurePosixPath(path).parts) >= 5
        and PurePosixPath(path).parts[:3] == ("opt", "open-webui", "lib")
        and re.fullmatch(r"python\d+\.\d+", PurePosixPath(path).parts[3])
        and PurePosixPath(path).parts[4] == "site-packages"
    }
    if len(matches) != 1:
        raise InspectionError(
            "archive must contain exactly one private site-packages root"
        )
    return next(iter(matches))


def provider_for_dist_info(root: str, providers: list[str]) -> str | None:
    match = re.fullmatch(r"(?P<distribution>.+)-\d.*\.dist-info", root)
    if match is None:
        return None
    distribution = canonical_name(match.group("distribution"))
    for provider in providers:
        if distribution == canonical_name(provider):
            return provider
    return None


def provider_for_wheel(filename: str, providers: list[str]) -> str | None:
    if not filename.endswith(".whl") or "-" not in filename:
        return None
    distribution = canonical_name(filename.split("-", 1)[0])
    for provider in providers:
        if distribution == canonical_name(provider):
            return provider
    return None


def residue_matches(paths: list[str]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {
        "build_home": [],
        "closure_archives": [],
        "closure_materializers": [],
        "cypress_cache": [],
        "node_modules": [],
        "npm_cache": [],
        "private_requirements_lock": [],
        "python_wheelhouse": [],
        "source_archives": [],
        "uv_cache": [],
        "uv_python": [],
    }
    for path in paths:
        parts = PurePosixPath(path).parts
        basename = parts[-1]
        lowered_parts = {part.casefold() for part in parts}
        if (
            parts[0] in {"build", "home", "pkg", "src", "tmp"}
            or "build-home" in lowered_parts
        ):
            matches["build_home"].append(path)
        if "offline-closure" in basename and basename.endswith(
            (".tar", ".tar.gz", ".tar.zst")
        ):
            matches["closure_archives"].append(path)
        if basename in {"npm-offline-closure.py", "python-offline-closure.py"}:
            matches["closure_materializers"].append(path)
        if "cypress-cache" in lowered_parts:
            matches["cypress_cache"].append(path)
        if "node_modules" in parts:
            matches["node_modules"].append(path)
        if lowered_parts.intersection(
            {".npm", "_cacache", "npm-cache", "npm-offline-cache"}
        ):
            matches["npm_cache"].append(path)
        if basename == "open-webui-private-requirements.lock":
            matches["private_requirements_lock"].append(path)
        if "wheelhouse" in lowered_parts:
            matches["python_wheelhouse"].append(path)
        if re.fullmatch(r"open[_-]webui-\d.*\.(?:tar\.gz|tar\.zst)", basename):
            matches["source_archives"].append(path)
        if "uv-cache" in lowered_parts:
            matches["uv_cache"].append(path)
        if "uv-python" in lowered_parts:
            matches["uv_python"].append(path)
    return {label: sorted(found) for label, found in sorted(matches.items())}


def inspect_archive(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise InspectionError("package archive is not a regular file")
    providers = load_providers()
    archive_sha256 = sha256_file(path)
    archive_size = path.stat().st_size

    try:
        with tarfile.open(path, "r:*") as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as error:
        raise InspectionError("package archive is malformed or unsupported") from error

    normalized: list[tuple[str, tarfile.TarInfo]] = []
    unsafe_names: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    non_root: list[str] = []
    links: list[str] = []
    unsafe_modes: list[str] = []
    unsupported: list[str] = []
    type_counts = {
        kind: 0 for kind in ("file", "directory", "symlink", "hardlink", "other")
    }
    for member in members:
        kind = member_type(member)
        type_counts[kind] += 1
        name = normalized_path(member.name)
        if name is None:
            unsafe_names.append(member.name)
            continue
        if name in seen:
            duplicates.append(name)
        seen.add(name)
        if (
            member.uid != 0
            or member.gid != 0
            or member.uname not in {"", "root"}
            or member.gname not in {"", "root"}
        ):
            non_root.append(name)
        if member.mode & 0o6002:
            unsafe_modes.append(name)
        if kind in {"symlink", "hardlink"}:
            links.append(name)
        elif kind not in {"file", "directory"}:
            unsupported.append(name)
        normalized.append((name, member))

    errors = []
    if unsafe_names:
        errors.append(f"{len(unsafe_names)} unsafe path member(s)")
    if duplicates:
        errors.append(f"{len(duplicates)} duplicate normalized path member(s)")
    if non_root:
        errors.append(f"{len(non_root)} non-root member(s)")
    if links:
        errors.append(f"{len(links)} link member(s)")
    if unsafe_modes:
        errors.append(f"{len(unsafe_modes)} unsafe mode member(s)")
    if unsupported:
        errors.append(f"{len(unsupported)} unsupported member type(s)")
    if errors:
        raise InspectionError("; ".join(errors))

    paths = [name for name, _member in normalized]
    site_prefix = site_packages_prefix(paths)
    metadata_bodies: dict[str, bytes] = {}
    file_records: dict[str, dict[str, object]] = {}
    manifest_records: list[dict[str, object]] = []
    dist_metadata: list[tuple[str, bytes]] = []
    pyodide_wheels: list[dict[str, object]] = []

    try:
        with tarfile.open(path, "r:*") as archive:
            for name, member in sorted(normalized, key=lambda item: item[0]):
                kind = member_type(member)
                content_sha256: str | None = None
                body: bytes | None = None
                if kind == "file":
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise InspectionError(f"unable to read regular member: {name}")
                    if name in {".BUILDINFO", ".PKGINFO", ".MTREE"} or (
                        name.startswith(site_prefix)
                        and name.endswith(".dist-info/METADATA")
                    ):
                        body = extracted.read()
                        if len(body) != member.size:
                            raise InspectionError(f"short regular member: {name}")
                        content_sha256 = hashlib.sha256(body).hexdigest()
                    else:
                        content_sha256 = sha256_stream(extracted)
                    record = {
                        "mode": f"{member.mode & 0o7777:04o}",
                        "owner": "root:root",
                        "sha256": content_sha256,
                        "size_bytes": member.size,
                    }
                    file_records[name] = record
                    if name in {".BUILDINFO", ".PKGINFO", ".MTREE"}:
                        if body is None:
                            raise AssertionError("metadata body was not retained")
                        metadata_bodies[name] = body
                    if name.startswith(site_prefix) and name.endswith(
                        ".dist-info/METADATA"
                    ):
                        if body is None:
                            raise AssertionError(
                                "distribution metadata body was not retained"
                            )
                        dist_metadata.append((name, body))
                    relative = name.removeprefix(site_prefix)
                    if relative.startswith(PYODIDE_PREFIX) and relative.endswith(
                        ".whl"
                    ):
                        pyodide_wheels.append(
                            {
                                "path": name,
                                "sha256": content_sha256,
                                "size_bytes": member.size,
                            }
                        )
                manifest_records.append(
                    {
                        "content_sha256": content_sha256,
                        "gid": member.gid,
                        "link_target": member.linkname or None,
                        "mode": f"{member.mode & 0o7777:04o}",
                        "path": name,
                        "size": member.size,
                        "type": kind,
                        "uid": member.uid,
                    }
                )
    except (OSError, tarfile.TarError) as error:
        raise InspectionError("package member content is malformed") from error

    missing_metadata = sorted(
        {".BUILDINFO", ".PKGINFO", ".MTREE"} - metadata_bodies.keys()
    )
    if missing_metadata:
        raise InspectionError(
            f"missing package metadata: {', '.join(missing_metadata)}"
        )
    missing_critical = sorted(set(CRITICAL_FILES) - file_records.keys())
    if missing_critical:
        raise InspectionError(f"missing critical file: {missing_critical[0]}")

    builddir = parse_build_value(metadata_bodies[".BUILDINFO"], "builddir")
    startdir = parse_build_value(metadata_bodies[".BUILDINFO"], "startdir")
    if builddir != startdir or builddir not in GENERIC_BUILD_PATHS:
        raise InspectionError(
            ".BUILDINFO builddir/startdir are not the same generic public path"
        )
    pkginfo_fields = parse_pkginfo(metadata_bodies[".PKGINFO"])
    buildinfo_fields = parse_buildinfo_identity(metadata_bodies[".BUILDINFO"])
    if (
        buildinfo_fields["package_version"] != pkginfo_fields["package_version"]
        or buildinfo_fields["architecture"] != pkginfo_fields["architecture"]
    ):
        raise InspectionError(".BUILDINFO and .PKGINFO package identities differ")
    decoded_mtree = decode_mtree(metadata_bodies[".MTREE"])

    manifest_digest = hashlib.sha256()
    for record in manifest_records:
        manifest_digest.update(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )

    lock_matches = sorted(path for path in paths if PurePosixPath(path).name == ".lock")
    uv_cache_matches = sorted(
        path for path in paths if PurePosixPath(path).name == "uv_cache.json"
    )
    if lock_matches or uv_cache_matches:
        raise InspectionError("uv installer metadata remains in the package payload")

    distribution_violations: list[dict[str, str]] = []
    top_level_violations: list[dict[str, str]] = []
    for name in paths:
        if not name.startswith(site_prefix):
            continue
        relative = name.removeprefix(site_prefix)
        if not relative or relative.startswith(PYODIDE_PREFIX):
            continue
        root = PurePosixPath(relative).parts[0]
        provider = provider_for_dist_info(root, providers)
        if provider is not None:
            distribution_violations.append({"path": name, "provider": provider})
        for candidate, roots in PROVIDER_ROOTS.items():
            if any(root == item or root.startswith(f"{item}.") for item in roots):
                top_level_violations.append(
                    {"path": name, "provider": candidate, "root": root}
                )

    for name, body in dist_metadata:
        for raw_line in body.splitlines():
            if raw_line.lower().startswith(b"name:"):
                package_name = (
                    raw_line.split(b":", 1)[1].strip().decode("utf-8", "replace")
                )
                for provider in providers:
                    if canonical_name(package_name) == canonical_name(provider):
                        distribution_violations.append(
                            {"path": name, "provider": provider}
                        )
                break
    distribution_violations = [
        dict(items)
        for items in sorted(
            {tuple(sorted(item.items())) for item in distribution_violations}
        )
    ]
    top_level_violations = [
        dict(items)
        for items in sorted(
            {tuple(sorted(item.items())) for item in top_level_violations}
        )
    ]
    if distribution_violations or top_level_violations:
        raise InspectionError("server-side externalized provider payload is present")

    pyodide_wheels.sort(key=lambda item: str(item["path"]))
    provider_exceptions = []
    for wheel in pyodide_wheels:
        provider = provider_for_wheel(PurePosixPath(str(wheel["path"])).name, providers)
        if provider is not None:
            provider_exceptions.append({"path": wheel["path"], "provider": provider})

    frontend_root = f"{site_prefix}open_webui/frontend"
    frontend_prefix = f"{frontend_root}/"
    pyodide_prefix = f"{site_prefix}{PYODIDE_PREFIX}"
    pyodide_files = [
        (path, record)
        for path, record in sorted(file_records.items())
        if path.startswith(pyodide_prefix)
    ]
    pyodide_manifest = hashlib.sha256()
    for member_path, record in pyodide_files:
        relative = member_path.removeprefix(pyodide_prefix)
        pyodide_manifest.update(relative.encode("utf-8"))
        pyodide_manifest.update(b"\0")
        pyodide_manifest.update(str(record["size_bytes"]).encode("ascii"))
        pyodide_manifest.update(b"\0")
        pyodide_manifest.update(str(record["sha256"]).encode("ascii"))
        pyodide_manifest.update(b"\n")
    private_distributions = {
        PurePosixPath(path.removeprefix(site_prefix)).parts[0]
        for path in paths
        if path.startswith(site_prefix)
        and path.removeprefix(site_prefix)
        and PurePosixPath(path.removeprefix(site_prefix))
        .parts[0]
        .endswith(".dist-info")
    }

    residue = residue_matches(paths)
    all_residue = sorted({path for matches in residue.values() for path in matches})
    if all_residue:
        raise InspectionError(
            "build-input or cache residue remains in the package payload"
        )

    payload_file_records = {
        member_path: record
        for member_path, record in file_records.items()
        if member_path not in {".BUILDINFO", ".MTREE", ".PKGINFO"}
    }
    regular_file_bytes = sum(
        int(record["size_bytes"]) for record in payload_file_records.values()
    )
    if regular_file_bytes != pkginfo_fields["installed_size_bytes"]:
        raise InspectionError(
            "payload regular-file bytes differ from .PKGINFO installed size"
        )

    metadata = {
        name: {
            "sha256": file_records[name]["sha256"],
            "size_bytes": file_records[name]["size_bytes"],
        }
        for name in (".BUILDINFO", ".PKGINFO", ".MTREE")
    }
    metadata.update(
        {
            "build_paths_public_safe": True,
            "builddir": builddir,
            "startdir": startdir,
        }
    )
    metadata[".BUILDINFO"]["fields"] = buildinfo_fields
    metadata[".PKGINFO"]["fields"] = pkginfo_fields
    metadata[".MTREE"].update(
        {
            "decoded_line_count": len(decoded_mtree.splitlines()),
            "decoded_sha256": hashlib.sha256(decoded_mtree).hexdigest(),
            "decoded_size_bytes": len(decoded_mtree),
        }
    )
    return {
        "archive": {
            "duplicate_path_count": len(duplicates),
            "link_member_count": len(links),
            "manifest_algorithm": "SHA-256 over canonical JSON Lines sorted by path; each record binds path, type, mode, uid, gid, size, file-content SHA-256, and link target.",
            "manifest_record_count": len(manifest_records),
            "manifest_sha256": manifest_digest.hexdigest(),
            "member_count": len(members),
            "non_root_member_count": len(non_root),
            "sha256": archive_sha256,
            "size_bytes": archive_size,
            "type_counts": type_counts,
            "unsafe_mode_member_count": len(unsafe_modes),
            "unsafe_path_count": len(unsafe_names),
        },
        "critical_files": {path: file_records[path] for path in CRITICAL_FILES},
        "metadata": metadata,
        "payload": {
            "directory_count": type_counts["directory"],
            "entry_count": len(members) - 3,
            "frontend_entry_count": sum(
                member_path == frontend_root or member_path.startswith(frontend_prefix)
                for member_path in paths
            ),
            "installer_metadata": {
                "lock_matches": lock_matches,
                "uv_cache_json_matches": uv_cache_matches,
            },
            "installer_metadata_absent": True,
            "installed_size_matches_pkginfo": True,
            "private_distribution_count": len(private_distributions),
            "pyodide_payload": {
                "file_count": len(pyodide_files),
                "manifest_algorithm": "For each lexically sorted relative path: path, NUL, byte count, NUL, file SHA-256, newline.",
                "manifest_sha256": pyodide_manifest.hexdigest(),
                "total_bytes": sum(
                    int(record["size_bytes"]) for _path, record in pyodide_files
                ),
            },
            "pyodide_wheels": {
                "count": len(pyodide_wheels),
                "files": pyodide_wheels,
                "provider_exception_count": len(provider_exceptions),
                "provider_exceptions": provider_exceptions,
                "scope": "Browser-side Pyodide wheel artifacts; not installed server distributions.",
                "total_bytes": sum(int(item["size_bytes"]) for item in pyodide_wheels),
            },
            "regular_file_bytes": regular_file_bytes,
            "regular_file_count": len(payload_file_records),
            "server_provider_boundary": {
                "distribution_metadata_violations": distribution_violations,
                "passed": True,
                "providers_absent": providers,
                "scope": site_prefix,
                "top_level_root_violations": top_level_violations,
            },
        },
        "residue": {"all_matches": all_residue, "matches": residue, "passed": True},
        "schema": SCHEMA,
    }


def reject_archive_output_alias(archive: Path, output: Path) -> None:
    try:
        resolved_archive = archive.resolve(strict=True)
        resolved_output = output.resolve(strict=False)
        same_file = output.exists() and archive.samefile(output)
    except OSError as error:
        raise InspectionError("unable to verify archive/output identity") from error
    if resolved_archive == resolved_output or same_file:
        raise InspectionError("output aliases package archive")


def write_receipt_atomically(output: Path, encoded: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        os.replace(temporary_path, output)
        temporary_path = None
    except OSError as error:
        raise InspectionError(
            "unable to atomically write inspection receipt"
        ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed inspection for an Open WebUI Arch package archive."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.output is not None:
            reject_archive_output_alias(arguments.archive, arguments.output)
        receipt = inspect_archive(arguments.archive)
        encoded = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
        if arguments.output is not None:
            write_receipt_atomically(arguments.output, encoded)
    except InspectionError as error:
        print(f"inspection failed: {error}", file=sys.stderr)
        return 1
    if arguments.output is None:
        sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
