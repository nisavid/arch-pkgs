#!/usr/bin/env python3

import hashlib
import json
import os
import stat
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_manifest(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise SystemExit(f"repository must be a real directory: {root}")

    entries = []
    # Pacman repository publication is intentionally flat; never recurse.
    for path in sorted(root.iterdir(), key=lambda item: os.fsencode(item.name)):
        metadata = path.lstat()
        common = {
            "gid": metadata.st_gid,
            "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
            "mtimeNs": metadata.st_mtime_ns,
            "name": path.name,
            "uid": metadata.st_uid,
        }
        if path.is_symlink():
            target = os.readlink(path)
            if "/" in target or target in ("", ".", ".."):
                raise SystemExit(f"unsafe repository symlink: {path.name} -> {target}")
            if not (root / target).is_file():
                raise SystemExit(
                    f"repository symlink target is missing: {path.name} -> {target}"
                )
            entries.append({**common, "target": target, "type": "symlink"})
        elif path.is_file():
            entries.append(
                {
                    **common,
                    "sha256": sha256_file(path),
                    "size": metadata.st_size,
                    "type": "file",
                }
            )
        else:
            raise SystemExit(f"unsupported repository entry: {path.name}")

    return {"entries": entries, "schemaVersion": 3}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} REPOSITORY")
    print(json.dumps(repository_manifest(Path(sys.argv[1])), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
