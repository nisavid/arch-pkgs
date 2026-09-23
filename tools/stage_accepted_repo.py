#!/usr/bin/env python3
"""Stage, verify, and record an accepted-only pacman repository.

The accepted manifest schema is documented in docs/usage/local-repo.md under
"Accepted-Only Staging". This tool never invokes makepkg, never writes to a
published repository, and never needs privileges.
"""

import argparse
import errno
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import NoReturn, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_repo_consistency import RETIRED_CHATGPT_PRODUCER_NAMES  # noqa: E402
from repository_manifest import repository_manifest, sha256_file  # noqa: E402

MANIFEST_SCHEMA = "arch-pkgs-accepted-publication/v1"
RECEIPT_SCHEMA = "arch-pkgs-accepted-publication-receipt/v1"
MANIFEST_KEYS = {"schema", "repository", "archives", "dispositions", "catalog_commit"}
ARCHIVE_KEYS = {"package", "version", "arch", "filename", "size", "sha256", "source"}
OPTIONAL_ARCHIVE_KEYS = {"source_commit", "promotion"}
DISPOSITION_KEYS = {"identity", "disposition", "note"}
DISPOSITIONS = {"kept-eligible", "knowingly-foreign", "dropped"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[a-z0-9@._+][a-z0-9@._+:-]*$")
T = TypeVar("T")


def fail(message: str) -> NoReturn:
    raise SystemExit(f"stage_accepted_repo: {message}")


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _value in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        fail(f"invalid manifest: duplicate JSON keys {duplicates}")
    return dict(pairs)


def load_manifest(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as error:
        fail(f"manifest is not valid JSON: {error}")
    errors = manifest_errors(manifest)
    if errors:
        fail("invalid manifest:\n  " + "\n  ".join(errors))
    return manifest, raw


def manifest_errors(manifest: object) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors = []
    unknown = manifest.keys() - MANIFEST_KEYS
    if unknown:
        errors.append(f"unknown manifest keys: {sorted(unknown)}")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append(f"schema must be {MANIFEST_SCHEMA}")
    repository = manifest.get("repository")
    if not (
        isinstance(repository, dict)
        and repository.keys() == {"name", "arch"}
        and all(isinstance(value, str) and NAME.match(value) for value in repository.values())
    ):
        errors.append("repository must be an object with string name and arch")
        repository = None
    catalog_commit = manifest.get("catalog_commit")
    if catalog_commit is not None and not (
        isinstance(catalog_commit, str) and COMMIT.match(catalog_commit)
    ):
        errors.append("catalog_commit must be a full 40-character commit SHA")
    archives = manifest.get("archives")
    if not isinstance(archives, list) or not archives:
        return errors + ["archives must be a nonempty list"]
    packages: set[str] = set()
    filenames: set[str] = set()
    for index, record in enumerate(archives):
        where = f"archives[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{where}: must be an object")
            continue
        missing = ARCHIVE_KEYS - record.keys()
        unknown = record.keys() - ARCHIVE_KEYS - OPTIONAL_ARCHIVE_KEYS
        if missing or unknown:
            errors.append(
                f"{where}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}"
            )
            continue
        package, version, arch = record["package"], record["version"], record["arch"]
        filename, size, digest = record["filename"], record["size"], record["sha256"]
        if not all(isinstance(value, str) and NAME.match(value) for value in (package, version, arch)):
            errors.append(f"{where}: package, version, and arch must be plain names")
            continue
        if repository is not None and arch not in (repository["arch"], "any"):
            errors.append(
                f"{where}: arch {arch} does not belong in repository arch {repository['arch']}"
            )
        if package in RETIRED_CHATGPT_PRODUCER_NAMES:
            errors.append(f"{where}: retired ChatGPT producer is refused: {package}")
        prefix = f"{package}-{version}-{arch}.pkg.tar."
        if not (
            isinstance(filename, str)
            and filename.startswith(prefix)
            and NAME.match(filename)
            and not filename.endswith(".sig")
        ):
            errors.append(f"{where}: filename must be a {prefix}* archive name")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{where}: size must be a positive integer")
        if not (isinstance(digest, str) and SHA256.match(digest)):
            errors.append(f"{where}: sha256 must be 64 lowercase hex digits")
        source = record["source"]
        source_path = PurePosixPath(source) if isinstance(source, str) else None
        if (
            source_path is None
            or source_path.is_absolute()
            or any(part in ("", "..") for part in source.split("/"))
        ):
            errors.append(f"{where}: source must be a relative store subdirectory")
        source_commit = record.get("source_commit")
        if source_commit is not None and not (
            isinstance(source_commit, str) and COMMIT.match(source_commit)
        ):
            errors.append(f"{where}: source_commit must be a full 40-character commit SHA")
        if "promotion" in record and not isinstance(record["promotion"], dict):
            errors.append(f"{where}: promotion must be an object")
        if package in packages:
            errors.append(f"{where}: duplicate package: {package}")
        if filename in filenames:
            errors.append(f"{where}: duplicate filename: {filename}")
        packages.add(package)
        filenames.add(filename)
    dispositions = manifest.get("dispositions", [])
    if not isinstance(dispositions, list):
        return errors + ["dispositions must be a list"]
    accepted = {f"{record.get('package')} {record.get('version')}" for record in archives if isinstance(record, dict)}
    identities: set[str] = set()
    for index, entry in enumerate(dispositions):
        where = f"dispositions[{index}]"
        if not (
            isinstance(entry, dict)
            and {"identity", "disposition"} <= entry.keys() <= DISPOSITION_KEYS
            and all(isinstance(value, str) for value in entry.values())
        ):
            errors.append(f"{where}: must hold string identity, disposition, and optional note")
            continue
        identity, disposition = entry["identity"], entry["disposition"]
        if disposition not in DISPOSITIONS:
            errors.append(f"{where}: disposition must be one of {sorted(DISPOSITIONS)}")
        if disposition == "kept-eligible" and identity not in accepted:
            errors.append(f"{where}: kept-eligible identity has no archive record: {identity}")
        if disposition != "kept-eligible" and identity in accepted:
            errors.append(f"{where}: an archive record cannot be {disposition}: {identity}")
        if identity in identities:
            errors.append(f"{where}: duplicate identity: {identity}")
        identities.add(identity)
    return errors


def expected_records(manifest: dict) -> set[tuple]:
    return {
        (
            record["package"],
            record["version"],
            record["arch"],
            record["filename"],
            record["size"],
            record["sha256"],
        )
        for record in manifest["archives"]
    }


def read_archive_members(path: Path) -> list[tuple[str, bytes]]:
    # bsdtar decompresses any repository or package format into a plain tar.
    result = subprocess.run(
        ["bsdtar", "-cf", "-", "--format=pax", f"@{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        fail(f"cannot read archive {path.name}: {result.stderr.decode().strip()}")
    members = []
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in archive:
            content = b""
            if member.isfile():
                extracted = archive.extractfile(member)
                content = extracted.read() if extracted else b""
            members.append((member.name.removeprefix("./"), content))
    return members


def parse_fields(text: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    key = None
    for line in text.splitlines():
        if line.startswith("%") and line.endswith("%") and len(line) > 2:
            key = line.strip("%")
            fields[key] = []
        elif line and key is not None:
            fields[key].append(line)
        elif not line:
            key = None
    return fields


def database_records(path: Path, *, require_files: bool) -> tuple[set[tuple], list[str]]:
    errors = []
    entries: dict[str, dict[str, bytes]] = {}
    for name, content in read_archive_members(path):
        parts = name.rstrip("/").split("/")
        if len(parts) == 1:
            entries.setdefault(parts[0], {})
        elif len(parts) == 2 and parts[1] in ("desc", "files"):
            entries.setdefault(parts[0], {})[parts[1]] = content
        else:
            errors.append(f"{path.name}: unexpected index member: {name}")
    records = set()
    names: set[str] = set()
    filenames: set[str] = set()
    for entry, members in sorted(entries.items()):
        expected_members = {"desc", "files"} if require_files else {"desc"}
        if members.keys() != expected_members:
            errors.append(f"{path.name}: {entry} has members {sorted(members)}")
            continue
        fields = parse_fields(members["desc"].decode())
        try:
            name, version, arch, filename = (
                fields[key][0] for key in ("NAME", "VERSION", "ARCH", "FILENAME")
            )
            record = (name, version, arch, filename, int(fields["CSIZE"][0]), fields["SHA256SUM"][0])
        except (KeyError, IndexError, ValueError):
            errors.append(f"{path.name}: {entry} lacks a complete package record")
            continue
        if f"{name}-{version}" != entry:
            errors.append(f"{path.name}: {entry} does not match its record")
        if name in names or filename in filenames:
            errors.append(f"{path.name}: duplicate package or filename: {name}")
        names.add(name)
        filenames.add(filename)
        records.add(record)
    return records, errors


def verify_repository(manifest: dict, repo_dir: Path, repo_name: str) -> list[str]:
    if not repo_dir.is_dir() or repo_dir.is_symlink():
        return [f"repository must be a real directory: {repo_dir}"]
    errors: list[str] = []
    database = f"{repo_name}.db.tar.zst"
    files_database = f"{repo_name}.files.tar.zst"
    aliases = {f"{repo_name}.db": database, f"{repo_name}.files": files_database}
    archives = {record["filename"] for record in manifest["archives"]}
    for path in sorted(repo_dir.iterdir()):
        name = path.name
        if name in aliases:
            if not path.is_symlink() or os.readlink(path) != aliases[name]:
                errors.append(f"{name} must be a symlink to {aliases[name]}")
        elif name in archives or name in (database, files_database):
            if path.is_symlink() or not path.is_file():
                errors.append(f"{name} must be a regular file")
        else:
            errors.append(f"unexpected repository entry: {name}")
    for name in (database, files_database, *aliases):
        if not os.path.lexists(repo_dir / name):
            errors.append(f"missing repository index: {name}")
    if errors:
        return errors

    records, database_errors = database_records(repo_dir / database, require_files=False)
    files_records, files_errors = database_records(repo_dir / files_database, require_files=True)
    errors += database_errors + files_errors
    if records != files_records:
        errors.append("database and files indexes disagree")
    expected = expected_records(manifest)
    for record in sorted(expected - records):
        errors.append(f"manifest archive is not indexed: {record[3]}")
    for record in sorted(records - expected):
        errors.append(f"indexed archive is not in the manifest: {record[3]}")
    for record in sorted(records & expected):
        path = repo_dir / record[3]
        if not path.is_file() or path.is_symlink():
            errors.append(f"indexed archive is missing: {record[3]}")
        elif path.stat().st_size != record[4] or sha256_file(path) != record[5]:
            errors.append(f"archive bytes do not match the manifest: {record[3]}")
    return errors


def document_sha256(document: dict) -> str:
    # Matches `tools/repository_manifest.py DIR | sha256sum` and the publisher.
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(text.encode()).hexdigest()


def manifest_sha256(directory: Path) -> str:
    return document_sha256(repository_manifest(directory))


def read_stable(directory: Path, label: str, read: Callable[[], T]) -> tuple[dict, T]:
    # The publisher swaps repositories atomically, so bind a read to one snapshot.
    before = repository_manifest(directory)
    result = read()
    if repository_manifest(directory) != before:
        fail(f"{label} changed while the receipt was being written: {directory.name}")
    return before, result


def pkginfo_identity(path: Path) -> tuple[str, str, str]:
    result = subprocess.run(
        ["bsdtar", "-xOf", str(path), ".PKGINFO"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        fail(f"archive has no readable .PKGINFO: {path.name}")
    fields: dict[str, str] = {}
    for line in result.stdout.decode().splitlines():
        key, separator, value = line.partition(" = ")
        if separator and key in ("pkgname", "pkgver", "arch"):
            fields.setdefault(key, value)
    return fields.get("pkgname", ""), fields.get("pkgver", ""), fields.get("arch", "")


def resolve_repo_name(manifest: dict, requested: str | None) -> str:
    name = manifest["repository"]["name"]
    if requested is not None and requested != name:
        fail(f"--repo-name {requested} does not match manifest repository {name}")
    return name


def stage(args: argparse.Namespace) -> int:
    manifest, raw = load_manifest(args.manifest)
    repo_name = resolve_repo_name(manifest, args.repo_name)
    store_root = args.store_root.resolve(strict=True)
    repo_dir = args.repo_dir.absolute()
    if repo_dir.is_symlink() or (repo_dir.exists() and not repo_dir.is_dir()):
        fail(f"--repo-dir must be a directory: {repo_dir}")
    if repo_dir.exists() and any(repo_dir.iterdir()):
        fail(f"--repo-dir must be absent or empty: {repo_dir}")
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    writer_lock = repo_dir.with_name(f"{repo_dir.name}.writer.lock")
    try:
        writer_lock.mkdir()
    except FileExistsError:
        fail(f"repository writer lock is held: {writer_lock}")
    work: Path | None = None
    try:
        work = Path(tempfile.mkdtemp(prefix=f".{repo_dir.name}.stage.", dir=repo_dir.parent))
        umask = os.umask(0)
        os.umask(umask)
        work.chmod(0o777 & ~umask)
        staged = []
        for record in manifest["archives"]:
            source = store_root / record["source"] / record["filename"]
            resolved = source.resolve()
            if source.is_symlink() or not resolved.is_relative_to(store_root):
                fail(f"source must be a regular file inside the store: {record['filename']}")
            if not source.is_file():
                fail(f"missing accepted archive: {record['source']}/{record['filename']}")
            if source.stat().st_size != record["size"]:
                fail(f"size does not match the manifest: {record['source']}/{record['filename']}")
            if sha256_file(source) != record["sha256"]:
                fail(f"sha256 does not match the manifest: {record['source']}/{record['filename']}")
            destination = work / record["filename"]
            # Copy bytes only: staging must never share inodes with the store.
            shutil.copyfile(source, destination)
            if sha256_file(destination) != record["sha256"]:
                fail(f"staged copy does not match the manifest: {record['filename']}")
            identity = pkginfo_identity(destination)
            if identity != (record["package"], record["version"], record["arch"]):
                fail(
                    f".PKGINFO identity {identity} does not match the manifest: "
                    f"{record['filename']}"
                )
            staged.append(str(destination))
        result = subprocess.run(
            ["repo-add", "--quiet", str(work / f"{repo_name}.db.tar.zst"), *staged],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            fail(f"repo-add failed:\n{result.stdout}")
        errors = verify_repository(manifest, work, repo_name)
        if errors:
            fail("staged repository does not match the manifest:\n  " + "\n  ".join(errors))
        # The manifest covers only the entries, so the rename cannot change it.
        repository_manifest_sha = manifest_sha256(work)
        try:
            os.rename(work, repo_dir)
        except OSError as error:
            if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
                fail(f"--repo-dir became nonempty during staging: {repo_dir}")
            raise
    finally:
        if work is not None and work.exists():
            shutil.rmtree(work)
        writer_lock.rmdir()
    print(f"Staged accepted repository: {repo_dir}")
    print(f"Archives: {len(manifest['archives'])}")
    print(f"Accepted manifest SHA-256: {hashlib.sha256(raw).hexdigest()}")
    print(f"Repository-manifest SHA-256: {repository_manifest_sha}")
    return 0


def verify(args: argparse.Namespace) -> int:
    manifest, raw = load_manifest(args.manifest)
    repo_name = resolve_repo_name(manifest, args.repo_name)
    errors = verify_repository(manifest, args.repo_dir, repo_name)
    if errors:
        fail("repository does not match the manifest:\n  " + "\n  ".join(errors))
    print(f"Verified accepted repository: {args.repo_dir}")
    print(f"Archives: {len(manifest['archives'])}")
    print(f"Accepted manifest SHA-256: {hashlib.sha256(raw).hexdigest()}")
    for suffix in ("db", "files"):
        index = args.repo_dir / f"{repo_name}.{suffix}.tar.zst"
        print(f"{repo_name}.{suffix}.tar.zst SHA-256: {sha256_file(index)}")
    print(f"Repository-manifest SHA-256: {manifest_sha256(args.repo_dir)}")
    return 0


def receipt(args: argparse.Namespace) -> int:
    manifest, raw = load_manifest(args.manifest)
    repo_name = resolve_repo_name(manifest, args.repo_name)
    if not SHA256.match(args.staging_manifest_sha):
        fail("--staging-manifest-sha must be 64 lowercase hex digits")
    if not args.live_dir.is_dir() or args.live_dir.is_symlink():
        fail(f"--live-dir must be a real directory: {args.live_dir}")
    # Every live field comes from this one manifest; nothing rereads the directory.
    live_manifest, errors = read_stable(
        args.live_dir,
        "live repository",
        lambda: verify_repository(manifest, args.live_dir, repo_name),
    )
    if errors:
        fail("live repository does not match the manifest:\n  " + "\n  ".join(errors))
    live_manifest_sha = document_sha256(live_manifest)
    live_entries = {entry["name"]: entry for entry in live_manifest["entries"]}
    if live_manifest_sha != args.staging_manifest_sha:
        fail(
            "live repository-manifest SHA-256 does not match the publisher-verified "
            f"staging manifest: {live_manifest_sha}"
        )

    def record_json(record: tuple) -> dict:
        keys = ("package", "version", "arch", "filename", "size", "sha256")
        return dict(zip(keys, record))

    previous_copy = None
    if args.previous_dir is not None:
        if not args.previous_dir.is_dir() or args.previous_dir.is_symlink():
            fail(f"--previous-dir must be a real directory: {args.previous_dir}")
        previous_database = args.previous_dir / f"{repo_name}.db.tar.zst"

        def read_previous_records() -> set[tuple]:
            # A previous copy without a database held no pacman repository.
            if not os.path.lexists(previous_database):
                return set()
            records, previous_errors = database_records(previous_database, require_files=False)
            if previous_errors:
                fail("previous repository index is unreadable:\n  " + "\n  ".join(previous_errors))
            return records

        previous_manifest, previous_records = read_stable(
            args.previous_dir, "previous copy", read_previous_records
        )
        previous_copy = {
            "name": args.previous_dir.name,
            "repository_manifest_sha256": document_sha256(previous_manifest),
            "records": [record_json(record) for record in sorted(previous_records)],
        }

    document = {
        "schema": RECEIPT_SCHEMA,
        "repository": manifest["repository"],
        "accepted_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "database": {
            f"{repo_name}.{suffix}.tar.zst": live_entries[f"{repo_name}.{suffix}.tar.zst"]["sha256"]
            for suffix in ("db", "files")
        },
        "published_records": [record_json(record) for record in sorted(expected_records(manifest))],
        "publisher_verified_manifest_sha256": args.staging_manifest_sha,
        "live_repository_manifest_sha256": live_manifest_sha,
        "previous_copy": previous_copy,
        "identity_dispositions": manifest.get("dispositions", []),
    }
    if "catalog_commit" in manifest:
        document["catalog_commit"] = manifest["catalog_commit"]
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    stage_parser = commands.add_parser("stage", help="build staging from empty")
    stage_parser.add_argument("--manifest", type=Path, required=True)
    stage_parser.add_argument("--store-root", type=Path, required=True)
    stage_parser.add_argument("--repo-dir", type=Path, required=True)
    stage_parser.add_argument("--repo-name")
    stage_parser.set_defaults(handler=stage)

    verify_parser = commands.add_parser("verify", help="verify a repository read-only")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--repo-dir", type=Path, required=True)
    verify_parser.add_argument("--repo-name")
    verify_parser.set_defaults(handler=verify)

    receipt_parser = commands.add_parser("receipt", help="write a publication receipt")
    receipt_parser.add_argument("--manifest", type=Path, required=True)
    receipt_parser.add_argument("--staging-manifest-sha", required=True)
    receipt_parser.add_argument("--live-dir", type=Path, required=True)
    receipt_parser.add_argument(
        "--previous-dir",
        type=Path,
        help="the copy the publisher printed as 'Retained previous pacman repo'; "
        "omit it when the publisher retained none",
    )
    receipt_parser.add_argument("--repo-name")
    receipt_parser.add_argument("--output", type=Path)
    receipt_parser.set_defaults(handler=receipt)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
