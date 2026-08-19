#!/usr/bin/python3
"""Materialize and verify Open WebUI's target-specific private wheel closure."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from functools import cache
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from compression import zstd
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

FORMAT = "open-webui-python-offline-closure-v1"
TARGET = "cp314-manylinux_2_28_x86_64"
EXPECTED_DISTRIBUTION_COUNT = 222
EXPECTED_PIP_VERSION = "26.2.1"
INDEX_CUTOFF = dt.datetime.fromisoformat("2026-08-18T06:25:20+00:00")
REQUIREMENT = re.compile(r"^([a-z0-9][a-z0-9._-]*)==([^ \\]+)(?: \\)?$")
HASH = re.compile(r"^    --hash=sha256:([0-9a-f]{64})(?: \\)?$")


class ClosureError(RuntimeError):
    """The closure does not satisfy its immutable target contract."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_lock(
    path: Path, *, expected_count: int | None = EXPECTED_DISTRIBUTION_COUNT
) -> list[dict[str, object]]:
    requirements: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        requirement_match = REQUIREMENT.fullmatch(line)
        if requirement_match:
            current = {
                "name": requirement_match.group(1),
                "version": requirement_match.group(2),
                "hashes": [],
            }
            requirements.append(current)
            continue
        hash_match = HASH.fullmatch(line)
        if hash_match and current is not None:
            current["hashes"].append(hash_match.group(1))  # type: ignore[union-attr]
            continue
        raise ClosureError(f"unexpected lock syntax: {line!r}")

    names = [str(requirement["name"]) for requirement in requirements]
    if expected_count is not None and len(requirements) != expected_count:
        raise ClosureError(
            f"lock has {len(requirements)} distributions; expected {expected_count}"
        )
    if names != sorted(set(names)):
        raise ClosureError("lock requirements must have unique canonical sorted names")
    if any(not requirement["hashes"] for requirement in requirements):
        raise ClosureError("every locked distribution must carry at least one SHA-256")
    return requirements


def inventory(lock: Path) -> dict[str, object]:
    requirements = parse_lock(lock)
    return {
        "format": FORMAT,
        "target": TARGET,
        "lock_sha256": sha256(lock),
        "distribution_count": len(requirements),
        "requirements": requirements,
    }


def load_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ClosureError("manifest root must be an object")
    return value


def verify(
    lock_path: Path,
    manifest_path: Path,
    wheelhouse: Path,
    *,
    allow_partial: bool,
) -> dict[str, object]:
    requirements = parse_lock(
        lock_path,
        expected_count=None if allow_partial else EXPECTED_DISTRIBUTION_COUNT,
    )
    locked = {str(entry["name"]): entry for entry in requirements}
    manifest = load_manifest(manifest_path)
    if manifest.get("format") != FORMAT:
        raise ClosureError("manifest format is missing or unsupported")
    if manifest.get("target") != TARGET:
        raise ClosureError("manifest target is not CPython 3.14/manylinux_2_28 x86_64")
    if manifest.get("lock_sha256") != sha256(lock_path):
        raise ClosureError("manifest lock SHA-256 does not match the requirements lock")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ClosureError("manifest artifacts must be a nonempty list")
    if manifest.get("distribution_count") != len(artifacts):
        raise ClosureError("manifest distribution count does not match its artifacts")
    if not allow_partial and len(artifacts) != EXPECTED_DISTRIBUTION_COUNT:
        raise ClosureError(
            f"manifest has {len(artifacts)} artifacts; "
            f"expected {EXPECTED_DISTRIBUTION_COUNT}"
        )

    names: list[str] = []
    filenames: list[str] = []
    total_size = 0
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ClosureError("manifest contains a non-object artifact")
        name = artifact.get("name")
        version = artifact.get("version")
        filename = artifact.get("filename")
        digest = artifact.get("sha256")
        size = artifact.get("size")
        url = artifact.get("url")
        if not isinstance(name, str) or name not in locked:
            raise ClosureError(f"manifest contains an unlocked distribution: {name!r}")
        locked_requirement = locked[name]
        if version != locked_requirement["version"]:
            raise ClosureError(f"manifest version for {name} differs from the lock")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ClosureError(f"manifest filename for {name} is unsafe")
        if not filename.endswith(".whl"):
            raise ClosureError(f"manifest artifact for {name} is not a wheel")
        validate_wheel_target(filename, name, str(locked_requirement["version"]))
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ClosureError(f"manifest SHA-256 for {name} is malformed")
        if digest not in locked_requirement["hashes"]:
            raise ClosureError(f"manifest SHA-256 for {name} is absent from the lock")
        if not isinstance(size, int) or size < 1:
            raise ClosureError(f"manifest size for {name} is invalid")
        if not isinstance(url, str):
            raise ClosureError(f"manifest URL for {name} is invalid")
        parsed_url = urlsplit(url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "files.pythonhosted.org"
        ):
            raise ClosureError(
                f"manifest URL for {name} is not an immutable PyPI file URL"
            )

        path = wheelhouse / filename
        try:
            actual_size = path.stat().st_size
        except OSError as error:
            raise ClosureError(f"missing artifact for {name}: {path}") from error
        if actual_size != size:
            raise ClosureError(f"size for {filename} is {actual_size}; expected {size}")
        actual_digest = sha256(path)
        if actual_digest != digest:
            raise ClosureError(
                f"SHA-256 for {filename} is {actual_digest}; expected {digest}"
            )
        names.append(name)
        filenames.append(filename)
        total_size += size

    if names != sorted(set(names)):
        raise ClosureError(
            "manifest artifacts must have unique sorted distribution names"
        )
    if len(filenames) != len(set(filenames)):
        raise ClosureError("manifest artifact filenames must be unique")
    if set(names) != set(locked):
        raise ClosureError(
            "manifest artifacts do not exactly match the requirements lock"
        )
    actual_files = sorted(path.name for path in wheelhouse.iterdir() if path.is_file())
    if actual_files != sorted(filenames):
        raise ClosureError("wheelhouse files do not exactly match the manifest")
    return {
        "distribution_count": len(artifacts),
        "total_size": total_size,
    }


def target_platforms() -> list[str]:
    platforms: list[str] = []
    legacy = {
        17: "manylinux2014_x86_64",
        12: "manylinux2010_x86_64",
        5: "manylinux1_x86_64",
    }
    for minor in range(28, 4, -1):
        platforms.append(f"manylinux_2_{minor}_x86_64")
        if minor in legacy:
            platforms.append(legacy[minor])
    platforms.append("linux_x86_64")
    return platforms


@cache
def target_wheel_tags() -> frozenset[Tag]:
    platforms = target_platforms()
    tags = set(
        cpython_tags(
            python_version=(3, 14),
            abis=("cp314", "abi3", "none"),
            platforms=platforms,
        )
    )
    tags.update(
        compatible_tags(
            python_version=(3, 14),
            interpreter="cp314",
            platforms=platforms,
        )
    )
    return frozenset(tags)


def validate_wheel_target(filename: str, name: str, version: str) -> None:
    try:
        distribution, wheel_version, _, tags = parse_wheel_filename(filename)
    except ValueError as error:
        raise ClosureError(f"invalid wheel filename for {name}: {filename}") from error
    if str(canonicalize_name(distribution)) != str(canonicalize_name(name)):
        raise ClosureError(
            f"wheel filename distribution differs from {name}: {filename}"
        )
    try:
        locked_version = Version(version)
    except InvalidVersion as error:
        raise ClosureError(
            f"locked version for {name} is invalid: {version}"
        ) from error
    if wheel_version != locked_version:
        raise ClosureError(
            f"wheel filename version differs from {name}=={version}: {filename}"
        )
    if tags.isdisjoint(target_wheel_tags()):
        raise ClosureError(f"wheel {filename} is not compatible with {TARGET}")


def download_wheels(lock_path: Path, wheelhouse: Path) -> None:
    try:
        import pip
    except ImportError as error:
        raise ClosureError(
            "python-pip is required to materialize the wheel closure"
        ) from error
    if pip.__version__ != EXPECTED_PIP_VERSION:
        raise ClosureError(
            f"pip {pip.__version__} is installed; expected {EXPECTED_PIP_VERSION}"
        )
    command = [
        sys.executable,
        "-m",
        "pip",
        "--isolated",
        "download",
        "--requirement",
        str(lock_path),
        "--dest",
        str(wheelhouse),
        "--require-hashes",
        "--no-deps",
        "--only-binary=:all:",
        "--python-version",
        "3.14",
        "--implementation",
        "cp",
        "--abi",
        "cp314",
        "--abi",
        "abi3",
        "--abi",
        "none",
    ]
    for platform in target_platforms():
        command.extend(("--platform", platform))
    command.extend(
        (
            "--index-url",
            "https://pypi.org/simple",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--quiet",
        )
    )
    result = subprocess.run(command, check=False, text=True)
    if result.returncode != 0:
        raise ClosureError(
            f"pip failed to materialize the target wheels (exit {result.returncode})"
        )


def pypi_artifact(requirement: dict[str, object], filename: str) -> dict[str, object]:
    name = str(requirement["name"])
    version = str(requirement["version"])
    endpoint = (
        f"https://pypi.org/pypi/{quote(name, safe='')}/{quote(version, safe='')}/json"
    )
    request = Request(
        endpoint, headers={"User-Agent": "arch-pkgs-open-webui-closure/1"}
    )
    try:
        with urlopen(request, timeout=60) as response:
            metadata = json.load(response)
    except (OSError, json.JSONDecodeError) as error:
        raise ClosureError(
            f"cannot read PyPI metadata for {name}=={version}: {error}"
        ) from error
    urls = metadata.get("urls")
    if not isinstance(urls, list):
        raise ClosureError(f"PyPI metadata for {name}=={version} has no file inventory")
    matches = [file for file in urls if file.get("filename") == filename]
    if len(matches) != 1:
        raise ClosureError(
            f"PyPI metadata selects {len(matches)} records for {name} artifact {filename}"
        )
    file = matches[0]
    if file.get("packagetype") != "bdist_wheel":
        raise ClosureError(f"selected artifact for {name} is not a wheel")
    if file.get("yanked"):
        raise ClosureError(f"selected artifact for {name} is yanked")
    digests = file.get("digests")
    digest = digests.get("sha256") if isinstance(digests, dict) else None
    if digest not in requirement["hashes"]:
        raise ClosureError(
            f"selected artifact SHA-256 for {name} is absent from the lock"
        )
    uploaded_at = file.get("upload_time_iso_8601")
    if not isinstance(uploaded_at, str):
        raise ClosureError(f"selected artifact for {name} has no upload timestamp")
    uploaded = dt.datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
    if uploaded > INDEX_CUTOFF:
        raise ClosureError(
            f"selected artifact for {name} was uploaded after the lock cutoff"
        )
    url = file.get("url")
    size = file.get("size")
    if not isinstance(url, str) or not isinstance(size, int):
        raise ClosureError(f"selected artifact metadata for {name} is incomplete")
    return {
        "name": name,
        "version": version,
        "filename": filename,
        "url": url,
        "sha256": digest,
        "size": size,
        "uploaded_at": uploaded_at,
    }


def materialize(lock_path: Path, output: Path) -> dict[str, object]:
    requirements = parse_lock(lock_path)
    if output.exists() and any(output.iterdir()):
        raise ClosureError(f"refusing to replace nonempty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    wheelhouse = output / "wheelhouse"
    wheelhouse.mkdir()
    download_wheels(lock_path, wheelhouse)

    wheel_by_name: dict[str, str] = {}
    for path in wheelhouse.iterdir():
        if not path.is_file() or not path.name.endswith(".whl"):
            raise ClosureError(f"materializer produced an unexpected file: {path.name}")
        try:
            distribution, _, _, _ = parse_wheel_filename(path.name)
        except ValueError as error:
            raise ClosureError(f"invalid wheel filename: {path.name}") from error
        name = str(canonicalize_name(distribution))
        if name in wheel_by_name:
            raise ClosureError(f"materializer selected multiple wheels for {name}")
        wheel_by_name[name] = path.name
    expected_names = [str(requirement["name"]) for requirement in requirements]
    if set(wheel_by_name) != set(expected_names):
        raise ClosureError(
            "materialized wheel names differ from the exact target closure; "
            f"missing={sorted(set(expected_names) - set(wheel_by_name))}, "
            f"extra={sorted(set(wheel_by_name) - set(expected_names))}"
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        pending = {
            str(requirement["name"]): executor.submit(
                pypi_artifact,
                requirement,
                wheel_by_name[str(requirement["name"])],
            )
            for requirement in requirements
        }
        artifacts = [pending[name].result() for name in expected_names]
    manifest = {
        "format": FORMAT,
        "target": TARGET,
        "selector": f"pip=={EXPECTED_PIP_VERSION}",
        "index_cutoff": INDEX_CUTOFF.isoformat().replace("+00:00", "Z"),
        "lock_sha256": sha256(lock_path),
        "distribution_count": len(artifacts),
        "artifacts": artifacts,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verified = verify(lock_path, manifest_path, wheelhouse, allow_partial=False)
    return {
        **verified,
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
    }


def tar_info(name: str, *, size: int = 0, directory: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = 0o755 if directory else 0o644
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    info.size = 0 if directory else size
    return info


def verify_tar_metadata(member: tarfile.TarInfo, *, directory: bool) -> None:
    expected_mode = 0o755 if directory else 0o644
    allowed_pax_headers = not member.pax_headers or member.pax_headers == {
        "path": member.name
    }
    if (
        member.mode != expected_mode
        or member.uid != 0
        or member.gid != 0
        or member.uname != "root"
        or member.gname != "root"
        or member.mtime != 0
        or not allowed_pax_headers
    ):
        raise ClosureError(f"noncanonical archive metadata for {member.name!r}")


def archive(
    lock_path: Path,
    manifest_path: Path,
    wheelhouse: Path,
    output: Path,
    *,
    allow_partial: bool,
) -> dict[str, object]:
    verified = verify(
        lock_path,
        manifest_path,
        wheelhouse,
        allow_partial=allow_partial,
    )
    manifest = load_manifest(manifest_path)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    root = "open-webui-python-offline-closure"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tar",
        delete=False,
    ) as temporary:
        temporary_tar: Path | None = Path(temporary.name)
    try:
        assert temporary_tar is not None
        with tarfile.open(temporary_tar, "w", format=tarfile.PAX_FORMAT) as target:
            target.addfile(tar_info(root, directory=True))
            manifest_bytes = manifest_path.read_bytes()
            target.addfile(
                tar_info(f"{root}/manifest.json", size=len(manifest_bytes)),
                io.BytesIO(manifest_bytes),
            )
            for artifact in sorted(artifacts, key=lambda value: value["filename"]):
                filename = artifact["filename"]
                assert isinstance(filename, str)
                source = wheelhouse / filename
                with source.open("rb") as wheel:
                    target.addfile(
                        tar_info(
                            f"{root}/wheelhouse/{filename}",
                            size=source.stat().st_size,
                        ),
                        wheel,
                    )
        if output.name.endswith(".tar.zst"):
            with (
                temporary_tar.open("rb") as source,
                zstd.open(output, "wb", level=19) as compressed,
            ):
                shutil.copyfileobj(source, compressed, length=1024 * 1024)
        elif output.name.endswith(".tar"):
            temporary_tar.replace(output)
            temporary_tar = None
        else:
            raise ClosureError("archive output must end in .tar or .tar.zst")
    finally:
        if temporary_tar is not None and temporary_tar.exists():
            temporary_tar.unlink()
    return {
        **verified,
        "archive": str(output),
        "archive_size": output.stat().st_size,
        "archive_sha256": sha256(output),
    }


def verify_archive(
    lock_path: Path,
    manifest_path: Path | None,
    archive_path: Path,
    *,
    allow_partial: bool,
) -> dict[str, object]:
    requirements = parse_lock(
        lock_path,
        expected_count=None if allow_partial else EXPECTED_DISTRIBUTION_COUNT,
    )
    locked = {str(requirement["name"]): requirement for requirement in requirements}
    opener = zstd.open if archive_path.name.endswith(".tar.zst") else open
    with (
        opener(archive_path, "rb") as source,
        tarfile.open(fileobj=source, mode="r|") as archive_reader,
    ):
        members = iter(archive_reader)
        root_member = next(members, None)
        manifest_member = next(members, None)
        if (
            root_member is None
            or root_member.name != "open-webui-python-offline-closure"
            or not root_member.isdir()
            or manifest_member is None
            or manifest_member.name != "open-webui-python-offline-closure/manifest.json"
            or not manifest_member.isfile()
            or manifest_member.issym()
            or manifest_member.islnk()
        ):
            raise ClosureError("archive does not begin with its safe manifest boundary")
        embedded = archive_reader.extractfile(manifest_member)
        if embedded is None:
            raise ClosureError("cannot read the archive manifest")
        manifest_bytes = embedded.read()
    if manifest_path is not None and manifest_bytes != manifest_path.read_bytes():
        raise ClosureError("archive manifest bytes differ from the bound manifest")
    manifest_value = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest_value, dict):
        raise ClosureError("archive manifest root must be an object")
    manifest = manifest_value
    if manifest.get("format") != FORMAT or manifest.get("target") != TARGET:
        raise ClosureError("archive manifest format or target is invalid")
    if manifest.get("lock_sha256") != sha256(lock_path):
        raise ClosureError("archive manifest lock SHA-256 does not match")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or manifest.get("distribution_count") != len(
        artifacts
    ):
        raise ClosureError("archive manifest artifact inventory is invalid")
    if not allow_partial and len(artifacts) != EXPECTED_DISTRIBUTION_COUNT:
        raise ClosureError(
            "archive manifest is not the complete 222-distribution closure"
        )

    artifact_by_filename: dict[str, dict[str, object]] = {}
    names: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ClosureError("archive manifest contains a non-object artifact")
        name = artifact.get("name")
        filename = artifact.get("filename")
        digest = artifact.get("sha256")
        size = artifact.get("size")
        if not isinstance(name, str) or name not in locked:
            raise ClosureError(
                f"archive manifest contains unlocked distribution {name!r}"
            )
        if artifact.get("version") != locked[name]["version"]:
            raise ClosureError(
                f"archive manifest version for {name} differs from the lock"
            )
        if digest not in locked[name]["hashes"]:
            raise ClosureError(
                f"archive manifest SHA-256 for {name} is absent from the lock"
            )
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or not filename.endswith(".whl")
            or not isinstance(size, int)
            or size < 1
        ):
            raise ClosureError(f"archive manifest artifact for {name} is invalid")
        validate_wheel_target(filename, name, str(locked[name]["version"]))
        if filename in artifact_by_filename:
            raise ClosureError(f"archive manifest repeats artifact {filename}")
        artifact_by_filename[filename] = artifact
        names.append(name)
    if names != sorted(set(names)) or set(names) != set(locked):
        raise ClosureError("archive manifest names do not exactly match the lock")

    root = "open-webui-python-offline-closure"
    expected_members = [root, f"{root}/manifest.json"] + [
        f"{root}/wheelhouse/{filename}" for filename in sorted(artifact_by_filename)
    ]
    actual_members: list[str] = []
    with (
        opener(archive_path, "rb") as source,
        tarfile.open(fileobj=source, mode="r|") as archive_reader,
    ):
        for member in archive_reader:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or member.name != path.as_posix()
                or any(part in ("", ".", "..") for part in path.parts)
            ):
                raise ClosureError(f"archive contains unsafe member {member.name!r}")
            actual_members.append(member.name)
            position = len(actual_members) - 1
            if (
                position >= len(expected_members)
                or member.name != expected_members[position]
            ):
                raise ClosureError(
                    f"archive contains unexpected member {member.name!r}"
                )
            if position == 0:
                if not member.isdir():
                    raise ClosureError("archive root is not a directory")
                verify_tar_metadata(member, directory=True)
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise ClosureError(
                    f"archive member {member.name!r} is not a regular file"
                )
            verify_tar_metadata(member, directory=False)
            extracted = archive_reader.extractfile(member)
            if extracted is None:
                raise ClosureError(f"cannot read archive member {member.name!r}")
            if member.name == f"{root}/manifest.json":
                if extracted.read() != manifest_bytes:
                    raise ClosureError(
                        "archive manifest changed between verification passes"
                    )
                continue
            filename = path.name
            artifact = artifact_by_filename[filename]
            digest = hashlib.sha256()
            size = 0
            while block := extracted.read(1024 * 1024):
                digest.update(block)
                size += len(block)
            if size != artifact["size"] or digest.hexdigest() != artifact["sha256"]:
                raise ClosureError(
                    f"archive artifact {filename} differs from its digest"
                )
    if actual_members != expected_members:
        raise ClosureError("archive member inventory is incomplete")
    return {
        "archive_sha256": sha256(archive_path),
        "archive_size": archive_path.stat().st_size,
        "distribution_count": len(artifacts),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--lock", required=True, type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--lock", required=True, type=Path)
    verify_parser.add_argument("--manifest", required=True, type=Path)
    verify_parser.add_argument("--wheelhouse", required=True, type=Path)
    verify_parser.add_argument("--allow-partial", action="store_true")
    archive_parser = subparsers.add_parser("archive")
    archive_parser.add_argument("--lock", required=True, type=Path)
    archive_parser.add_argument("--manifest", required=True, type=Path)
    archive_parser.add_argument("--wheelhouse", required=True, type=Path)
    archive_parser.add_argument("--output", required=True, type=Path)
    archive_parser.add_argument("--allow-partial", action="store_true")
    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("--lock", required=True, type=Path)
    materialize_parser.add_argument("--output", required=True, type=Path)
    verify_archive_parser = subparsers.add_parser("verify-archive")
    verify_archive_parser.add_argument("--lock", required=True, type=Path)
    verify_archive_parser.add_argument("--manifest", type=Path)
    verify_archive_parser.add_argument("--archive", required=True, type=Path)
    verify_archive_parser.add_argument("--allow-partial", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.command == "inventory":
            print(json.dumps(inventory(arguments.lock), indent=2, sort_keys=True))
            return 0
        if arguments.command == "verify":
            result = verify(
                arguments.lock,
                arguments.manifest,
                arguments.wheelhouse,
                allow_partial=arguments.allow_partial,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "archive":
            result = archive(
                arguments.lock,
                arguments.manifest,
                arguments.wheelhouse,
                arguments.output,
                allow_partial=arguments.allow_partial,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "materialize":
            result = materialize(arguments.lock, arguments.output)
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.command == "verify-archive":
            result = verify_archive(
                arguments.lock,
                arguments.manifest,
                arguments.archive,
                allow_partial=arguments.allow_partial,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        raise AssertionError(f"unhandled command {arguments.command}")
    except (ClosureError, OSError, json.JSONDecodeError) as error:
        print(f"python offline closure: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
