#!/usr/bin/env python3
"""Stage only the browser gate's payload; never extract a candidate runtime.

Usage: browser_payload.py <qdrant-archive> <web-ui-archive> <payload> <out>
The caller supplies fresh, private staging and host-only evidence directories.
"""

import bz2
import gzip
import hashlib
import lzma
import shutil
import subprocess
import sys
import tarfile
import zlib
from contextlib import contextmanager, nullcontext
from pathlib import Path, PurePosixPath


QDRANT_PAYLOAD = {
    "usr/bin/qdrant": "qdrant",
    "etc/qdrant/config.yaml": "config.yaml",
    "usr/share/qdrant/qdrant.spdx.json": "qdrant.spdx.json",
}
QDRANT_FILES = set(QDRANT_PAYLOAD) | {
    "usr/lib/systemd/system/qdrant.service",
    "usr/lib/sysusers.d/qdrant.conf",
    "usr/lib/tmpfiles.d/qdrant.conf",
    "usr/lib/qdrant/qdrant-secret-preflight",
    "usr/share/licenses/qdrant/LICENSE",
}
WEB_ROOT = "usr/share/qdrant/web-ui"
WEB_LICENSE = "usr/share/licenses/qdrant-web-ui/LICENSE"
METADATA = {".PKGINFO", ".BUILDINFO", ".MTREE"}


def parents(names: set[str]) -> set[str]:
    return {str(parent) for name in names for parent in PurePosixPath(name).parents}


@contextmanager
def open_archive(path: Path):
    # Python versions before 3.14 cannot decompress zstd themselves. Parse
    # decompressed bytes exactly once, including resolved PAX/GNU member names.
    with path.open("rb", buffering=0) as source:
        magic = source.read(4)
        source.seek(0)
        if magic == b"\x28\xb5\x2f\xfd":
            with subprocess.Popen(["zstd", "-dc"], stdin=source,
                                  stdout=subprocess.PIPE) as process:
                try:
                    with tarfile.open(fileobj=process.stdout, mode="r|*") as archive:
                        yield archive
                    # Consume the frame trailer too, so a bad checksum or
                    # truncated compressed input cannot become a successful run.
                    shutil.copyfileobj(process.stdout, _Discard())
                    if process.wait() != 0:
                        raise ValueError("cannot decompress candidate archive")
                finally:
                    if process.poll() is None:
                        process.terminate()
        else:
            opener = (gzip.open if magic.startswith(b"\x1f\x8b") else
                      bz2.open if magic.startswith(b"BZh") else
                      lzma.open if magic == b"\xfd7zX" else None)
            with (opener(source, "rb") if opener else nullcontext(source)) as decoded:
                with tarfile.open(fileobj=decoded, mode="r|") as archive:
                    yield archive
                # Tar iteration stops at its end marker, before a compressed
                # stream necessarily checks its trailer. Validate the remainder.
                shutil.copyfileobj(decoded, _Discard())


class _Discard:
    def write(self, data: bytes) -> int:
        return len(data)


def member_name(member: tarfile.TarInfo) -> str:
    name = member.name.removeprefix("./")
    if name.startswith("/"):
        raise ValueError(f"unsafe candidate path: {member.name!r}")
    if member.isdir():
        name = name.removesuffix("/")
    if member.isdir() and name == ".":
        return "."
    if (not name or name.startswith("/") or "\\" in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError(f"unsafe candidate path: {member.name!r}")
    return name


def stage_archive(path: Path, kind: str, payload: Path) -> None:
    allowed_files = QDRANT_FILES if kind == "qdrant" else {WEB_LICENSE}
    allowed_dirs = parents(allowed_files | ({WEB_ROOT + "/index.html"}
                                           if kind == "web-ui" else set()))
    seen: set[str] = set()
    regular: set[str] = set()
    directories: set[str] = set()
    with open_archive(path) as archive:
        for member in archive:
            name = member_name(member)
            if name in seen:
                raise ValueError(f"duplicate candidate path: {name!r}")
            seen.add(name)
            if (member.sparse is not None
                    or any(key.startswith("GNU.sparse") for key in member.pax_headers)
                    or (not member.isdir() and member.type not in
                        (tarfile.REGTYPE, tarfile.AREGTYPE))):
                raise ValueError(f"non-regular candidate member: {name!r}")
            ancestors = {str(parent) for parent in PurePosixPath(name).parents}
            if ancestors & regular:
                raise ValueError(f"candidate file used as a directory: {name!r}")
            directories.update(ancestors)
            web_asset = kind == "web-ui" and name.startswith(WEB_ROOT + "/")
            if member.isdir():
                if name not in allowed_dirs and not web_asset:
                    raise ValueError(f"unexpected candidate directory: {name!r}")
                directories.add(name)
                continue
            if name not in allowed_files | METADATA and not web_asset:
                raise ValueError(f"unexpected candidate file: {name!r}")
            if name in directories:
                raise ValueError(f"candidate directory replaced by file: {name!r}")
            regular.add(name)
            destination = QDRANT_PAYLOAD.get(name) if kind == "qdrant" else (
                "web-ui/" + name[len(WEB_ROOT) + 1:] if web_asset else None
            )
            if destination is None:
                continue
            target = payload / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            # No archive path is passed to an extraction API. Owners, modes,
            # links, special files, and extended attributes are never restored.
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"missing candidate file data: {name!r}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if destination == "qdrant" else 0o644)
    required = set(QDRANT_PAYLOAD) if kind == "qdrant" else {
        WEB_ROOT + "/index.html", WEB_ROOT + "/cloud/data.json",
    }
    if missing := required - regular:
        raise ValueError(f"missing {kind} payload: {sorted(missing)}")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_manifests(payload: Path, out: Path) -> None:
    files = [
        ("qdrant", "/usr/bin/qdrant"),
        ("config.yaml", "/etc/qdrant/config.yaml"),
        ("qdrant.spdx.json", "/usr/share/qdrant/qdrant.spdx.json"),
        ("web-ui/cloud/data.json", "/usr/share/qdrant/web-ui/cloud/data.json"),
    ]
    (out / "payload-inputs.sha256").write_text(
        "".join(f"{sha256(payload / name)}  {label}\n" for name, label in files),
        encoding="utf-8",
    )
    assets = sorted((payload / "web-ui").rglob("*"),
                    key=lambda path: path.relative_to(payload / "web-ui").as_posix().encode())
    (out / "web-ui-tree.txt").write_text(
        "".join(f"{sha256(path)}  {WEB_ROOT}/{path.relative_to(payload / 'web-ui').as_posix()}\n"
                for path in assets if path.is_file()), encoding="utf-8",
    )


def main() -> int:
    qpkg, wpkg, payload, out = map(Path, sys.argv[1:])
    try:
        stage_archive(qpkg, "qdrant", payload)
        stage_archive(wpkg, "web-ui", payload)
        write_manifests(payload, out)
    except (EOFError, OSError, ValueError, lzma.LZMAError, tarfile.TarError, zlib.error) as error:
        print(f"browser payload: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
