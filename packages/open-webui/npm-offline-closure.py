#!/usr/bin/env python3
"""Materialize and seed an integrity-bound npm closure for offline builds."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from compression import zstd

FORMAT_VERSION = 1
CHUNK_SIZE = 1024 * 1024


class ClosureError(RuntimeError):
    """Raised when the lock, closure, or cache violates the offline contract."""


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode()


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ClosureError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ClosureError(f"cannot read JSON from {path}: {error}") from error
    if not isinstance(value, dict):
        raise ClosureError(f"expected a JSON object in {path}")
    return value


def sha512_from_integrity(integrity: object) -> tuple[str, bytes]:
    if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
        raise ClosureError("every npm tarball must have exactly one SHA-512 integrity")
    encoded = integrity.removeprefix("sha512-")
    if "?" in encoded:
        raise ClosureError("npm integrity options are not supported")
    try:
        digest = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ClosureError(f"invalid npm SHA-512 integrity: {integrity}") from error
    if len(digest) != hashlib.sha512().digest_size:
        raise ClosureError(f"invalid npm SHA-512 digest length: {integrity}")
    return digest.hex(), digest


def validate_source_url(url: object, allow_file_urls: bool) -> str:
    if not isinstance(url, str):
        raise ClosureError("every npm package record must have a resolved URL")
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ClosureError(f"npm source URL contains forbidden authority data: {url}")
    if parsed.scheme == "file" and allow_file_urls:
        if parsed.netloc not in ("", "localhost"):
            raise ClosureError(f"file URL must address the local host: {url}")
        return url
    if (
        parsed.scheme != "https"
        or parsed.hostname != "registry.npmjs.org"
        or parsed.port is not None
    ):
        raise ClosureError(f"npm source URL is outside the registry boundary: {url}")
    return url


def derive_plan(lock_path: Path, allow_file_urls: bool) -> dict[str, object]:
    lock_bytes = lock_path.read_bytes()
    lock = read_json(lock_path)
    if lock.get("lockfileVersion") != 3:
        raise ClosureError("the npm closure requires lockfileVersion 3")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or "" not in packages:
        raise ClosureError("package-lock.json lacks the root package record")
    root = packages[""]
    if not isinstance(root, dict):
        raise ClosureError("the root package record must be an object")
    name = root.get("name", lock.get("name"))
    version = root.get("version", lock.get("version"))
    if not isinstance(name, str) or not name:
        raise ClosureError("the npm project name is missing")
    if not isinstance(version, str) or not version:
        raise ClosureError("the npm project version is missing")

    by_url: dict[str, dict[str, object]] = {}
    by_integrity: dict[str, str] = {}
    for lock_path_name, record in packages.items():
        if lock_path_name == "":
            continue
        if not isinstance(lock_path_name, str) or not isinstance(record, dict):
            raise ClosureError("each npm package record must be an object")
        url = validate_source_url(record.get("resolved"), allow_file_urls)
        integrity = record.get("integrity")
        digest_hex, _ = sha512_from_integrity(integrity)
        assert isinstance(integrity, str)
        previous_url = by_integrity.setdefault(integrity, url)
        if previous_url != url:
            raise ClosureError(
                f"one npm integrity resolves through multiple URLs: {integrity}"
            )
        entry = by_url.setdefault(
            url,
            {
                "url": url,
                "integrity": integrity,
                "sha512": digest_hex,
                "lock_paths": [],
            },
        )
        if entry["integrity"] != integrity:
            raise ClosureError(f"one npm URL has conflicting integrities: {url}")
        lock_paths = entry["lock_paths"]
        assert isinstance(lock_paths, list)
        lock_paths.append(lock_path_name)

    archive_root = f"{name}-npm-offline-closure-{version}"
    tarballs: list[dict[str, object]] = []
    for entry in sorted(by_url.values(), key=lambda item: str(item["url"])):
        digest_hex = str(entry["sha512"])
        entry["lock_paths"] = sorted(entry["lock_paths"])
        entry["archive_path"] = (
            f"{archive_root}/tarballs/sha512/{digest_hex[:2]}/"
            f"{digest_hex[2:4]}/{digest_hex[4:]}.tgz"
        )
        tarballs.append(entry)

    return {
        "format": FORMAT_VERSION,
        "project": {"name": name, "version": version},
        "lockfile_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "lockfile_version": 3,
        "package_record_count": len(packages) - 1,
        "unique_tarball_count": len(tarballs),
        "archive_root": archive_root,
        "tarballs": tarballs,
    }


def raw_cache_path(cache: Path, entry: dict[str, object]) -> Path:
    digest = str(entry["sha512"])
    return cache / "sha512" / digest[:2] / digest[2:4] / f"{digest[4:]}.tgz"


def npm_cache_path(cache: Path, entry: dict[str, object]) -> Path:
    digest = str(entry["sha512"])
    return (
        cache
        / "_cacache"
        / "content-v2"
        / "sha512"
        / digest[:2]
        / digest[2:4]
        / digest[4:]
    )


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha512()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def download_entry(entry: dict[str, object], cache: Path, allow_file_urls: bool) -> int:
    destination = raw_cache_path(cache, entry)
    expected_digest = str(entry["sha512"])
    if destination.is_file():
        actual_digest, size = hash_file(destination)
        if actual_digest == expected_digest:
            return size
        raise ClosureError(f"cached npm tarball has the wrong digest: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        str(entry["url"]), headers={"User-Agent": "arch-pkgs-npm-offline-closure/1"}
    )
    temporary: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            validate_source_url(response.geturl(), allow_file_urls)
            digest = hashlib.sha512()
            size = 0
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=".download-", delete=False
            ) as output:
                temporary = Path(output.name)
                while chunk := response.read(CHUNK_SIZE):
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)
        if digest.hexdigest() != expected_digest:
            raise ClosureError(
                f"downloaded npm tarball failed integrity: {entry['url']}"
            )
        os.replace(temporary, destination)
        temporary = None
        return size
    except (OSError, urllib.error.URLError) as error:
        raise ClosureError(
            f"cannot download npm tarball {entry['url']}: {error}"
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_tar_member(
    archive: tarfile.TarFile, name: str, payload: BinaryIO, size: int
) -> None:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    archive.addfile(info, payload)


def build_archive(
    archive_path: Path,
    manifest: dict[str, object],
    manifest_bytes: bytes,
    cache: Path,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=archive_path.parent, prefix=f".{archive_path.name}.", delete=False
    ) as temporary_output:
        temporary_path = Path(temporary_output.name)
    try:
        with (
            zstd.open(temporary_path, "wb", level=3) as compressed,
            tarfile.open(
                fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT
            ) as archive,
        ):
            root = str(manifest["archive_root"])
            write_tar_member(
                archive,
                f"{root}/manifest.json",
                io.BytesIO(manifest_bytes),
                len(manifest_bytes),
            )
            tarballs = manifest["tarballs"]
            assert isinstance(tarballs, list)
            for entry in sorted(tarballs, key=lambda item: str(item["archive_path"])):
                assert isinstance(entry, dict)
                source = raw_cache_path(cache, entry)
                with source.open("rb") as payload:
                    write_tar_member(
                        archive,
                        str(entry["archive_path"]),
                        payload,
                        int(entry["size"]),
                    )
        os.replace(temporary_path, archive_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def verify_manifest_against_lock(
    lock_path: Path, manifest: dict[str, object], allow_file_urls: bool
) -> None:
    plan = derive_plan(lock_path, allow_file_urls)
    manifest_without_sizes = json.loads(json.dumps(manifest))
    tarballs = manifest_without_sizes.get("tarballs")
    if not isinstance(tarballs, list):
        raise ClosureError("npm closure manifest lacks tarballs")
    for entry in tarballs:
        if not isinstance(entry, dict) or not isinstance(entry.get("size"), int):
            raise ClosureError("every npm closure manifest entry needs an exact size")
        if entry["size"] <= 0:
            raise ClosureError("npm tarball sizes must be positive")
        del entry["size"]
    if manifest_without_sizes != plan:
        raise ClosureError("npm closure manifest does not match package-lock.json")


def materialize(args: argparse.Namespace) -> dict[str, object]:
    lock_path = Path(args.lock)
    manifest_path = Path(args.manifest)
    archive_path = Path(args.archive)
    cache = Path(args.cache)
    for output in (manifest_path, archive_path):
        if output.exists() and not args.force:
            raise ClosureError(f"refusing to overwrite existing output: {output}")
    plan = derive_plan(lock_path, args.allow_file_urls)
    entries = plan["tarballs"]
    assert isinstance(entries, list)
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        sizes = list(
            executor.map(
                lambda entry: download_entry(entry, cache, args.allow_file_urls),
                entries,
            )
        )
    for entry, size in zip(entries, sizes, strict=True):
        assert isinstance(entry, dict)
        entry["size"] = size
    manifest_bytes = canonical_json(plan)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    build_archive(archive_path, plan, manifest_bytes, cache)
    return plan


def canonical_member(info: tarfile.TarInfo) -> bool:
    path = PurePosixPath(info.name)
    return (
        info.isreg()
        and not path.is_absolute()
        and ".." not in path.parts
        and str(path) == info.name
        and info.mode == 0o644
        and info.uid == 0
        and info.gid == 0
        and info.uname == "root"
        and info.gname == "root"
        and info.mtime == 0
    )


def copy_member_to_cache(
    source: BinaryIO, info: tarfile.TarInfo, destination: Path, expected: str
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha512()
    size = 0
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".seed-", delete=False
        ) as output:
            temporary = Path(output.name)
            while chunk := source.read(CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
                output.write(chunk)
        if size != info.size or digest.hexdigest() != expected:
            raise ClosureError(f"npm closure member failed integrity: {info.name}")
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def seed(args: argparse.Namespace) -> dict[str, object]:
    lock_path = Path(args.lock)
    manifest_path = Path(args.manifest)
    archive_path = Path(args.archive)
    npm_cache = Path(args.npm_cache)
    manifest = read_json(manifest_path)
    verify_manifest_against_lock(lock_path, manifest, args.allow_file_urls)
    manifest_bytes = canonical_json(manifest)
    root = str(manifest["archive_root"])
    expected: dict[str, dict[str, object] | None] = {f"{root}/manifest.json": None}
    tarballs = manifest["tarballs"]
    assert isinstance(tarballs, list)
    for entry in tarballs:
        assert isinstance(entry, dict)
        expected[str(entry["archive_path"])] = entry

    seen: set[str] = set()
    with (
        zstd.open(archive_path, "rb") as compressed,
        tarfile.open(fileobj=compressed, mode="r|") as archive,
    ):
        for info in archive:
            if not canonical_member(info):
                raise ClosureError(
                    f"unsafe or noncanonical archive member: {info.name}"
                )
            if info.name not in expected or info.name in seen:
                raise ClosureError(
                    f"unexpected or duplicate archive member: {info.name}"
                )
            seen.add(info.name)
            source = archive.extractfile(info)
            if source is None:
                raise ClosureError(f"cannot read archive member: {info.name}")
            entry = expected[info.name]
            if entry is None:
                if source.read() != manifest_bytes:
                    raise ClosureError(
                        "archive manifest differs from the tracked manifest"
                    )
                continue
            if info.size != int(entry["size"]):
                raise ClosureError(
                    f"npm closure member has the wrong size: {info.name}"
                )
            copy_member_to_cache(
                source,
                info,
                npm_cache_path(npm_cache, entry),
                str(entry["sha512"]),
            )
    missing = sorted(set(expected) - seen)
    if missing:
        raise ClosureError(f"npm closure archive is incomplete: {missing[0]}")
    return manifest


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    subparsers = cli.add_subparsers(dest="command", required=True)
    materialize_parser = subparsers.add_parser(
        "materialize", help="download, verify, and archive every locked npm tarball"
    )
    materialize_parser.add_argument("--lock", required=True)
    materialize_parser.add_argument("--manifest", required=True)
    materialize_parser.add_argument("--archive", required=True)
    materialize_parser.add_argument("--cache", required=True)
    materialize_parser.add_argument("--jobs", type=int, default=16)
    materialize_parser.add_argument("--allow-file-urls", action="store_true")
    materialize_parser.add_argument("--force", action="store_true")
    materialize_parser.set_defaults(handler=materialize)

    seed_parser = subparsers.add_parser(
        "seed", help="verify a raw closure archive and seed npm's content store"
    )
    seed_parser.add_argument("--lock", required=True)
    seed_parser.add_argument("--manifest", required=True)
    seed_parser.add_argument("--archive", required=True)
    seed_parser.add_argument("--npm-cache", required=True)
    seed_parser.add_argument("--allow-file-urls", action="store_true")
    seed_parser.set_defaults(handler=seed)
    return cli


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "jobs", 1) < 1:
        raise ClosureError("--jobs must be positive")
    manifest = args.handler(args)
    print(
        json.dumps(
            {
                "archive_root": manifest["archive_root"],
                "package_records": manifest["package_record_count"],
                "unique_tarballs": manifest["unique_tarball_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClosureError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
