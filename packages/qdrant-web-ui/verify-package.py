#!/usr/bin/env python3
"""Verify the public metadata of a built qdrant-web-ui package."""

from __future__ import annotations

import argparse
import hashlib
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath


def validate_archive_members(member_names: list[str], listing: list[str]) -> None:
    if len(member_names) != len(listing):
        raise SystemExit(
            "archive member and metadata listings have different lengths: "
            f"{len(member_names)} != {len(listing)}"
        )
    if len(set(member_names)) != len(member_names):
        raise SystemExit("duplicate archive member is not allowed")

    logical_paths: set[str] = set()
    for archive_path, line in zip(member_names, listing, strict=True):
        fields = line.split()
        if len(fields) < 4:
            raise SystemExit(f"unexpected archive listing record: {line}")

        archive_mode = fields[0]
        if not archive_mode.startswith(("-", "d")):
            raise SystemExit(
                f"non-regular archive entry is not allowed: {archive_path} "
                f"({archive_mode})"
            )

        logical_path = PurePosixPath(archive_path.rstrip("/"))
        if (
            not archive_path
            or logical_path.is_absolute()
            or ".." in logical_path.parts
            or str(logical_path) in {"", "."}
        ):
            raise SystemExit(f"unsafe archive member path: {archive_path}")

        is_directory = archive_mode.startswith("d")
        canonical_path = f"{logical_path}/" if is_directory else str(logical_path)
        if archive_path != canonical_path:
            raise SystemExit(
                f"non-canonical archive member is not allowed: {archive_path}"
            )
        logical_name = str(logical_path)
        if logical_name in logical_paths:
            raise SystemExit(f"duplicate logical archive member: {logical_name}")
        logical_paths.add(logical_name)

        expected_mode = "drwxr-xr-x" if is_directory else "-rw-r--r--"
        if archive_mode != expected_mode:
            raise SystemExit(
                f"unexpected archive mode for {archive_path}: {archive_mode}"
            )
        if fields[2:4] != ["0", "0"]:
            raise SystemExit(
                f"unexpected numeric archive owner for {archive_path}: "
                f"{fields[2]}:{fields[3]}"
            )


def reject_unsafe_extracted_entries(root: Path) -> None:
    for item in root.rglob("*"):
        relative_path = item.relative_to(root)
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit(
                f"extracted package symlink is not allowed: {relative_path}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise SystemExit(
                f"non-regular extracted package entry is not allowed: {relative_path}"
            )
        if metadata.st_nlink != 1:
            raise SystemExit(
                f"hard-linked extracted package entry is not allowed: {relative_path}"
            )


def reject_unexpected_extracted_payload(root: Path) -> None:
    web_root = root / "usr/share/qdrant/web-ui"
    license_file = root / "usr/share/licenses/qdrant-web-ui/LICENSE"
    allowed_exact_paths = {
        root / ".BUILDINFO",
        root / ".MTREE",
        root / ".PKGINFO",
        root / "usr",
        root / "usr/share",
        root / "usr/share/licenses",
        root / "usr/share/licenses/qdrant-web-ui",
        root / "usr/share/qdrant",
        license_file,
    }
    unexpected_payload = sorted(
        str(item.relative_to(root))
        for item in root.rglob("*")
        if item not in allowed_exact_paths and not item.is_relative_to(web_root)
    )
    if unexpected_payload:
        raise SystemExit("unexpected package payload: " + ", ".join(unexpected_payload))


def parse_package_metadata(metadata: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for line_number, line in enumerate(metadata.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        if " = " not in line:
            raise SystemExit(
                f"malformed package metadata at line {line_number}: {line}"
            )
        field, value = line.split(" = ", 1)
        if not field or not value:
            raise SystemExit(
                f"malformed package metadata at line {line_number}: {line}"
            )
        parsed.setdefault(field, []).append(value)
    return parsed


def validate_package_metadata(metadata: str) -> None:
    parsed = parse_package_metadata(metadata)
    expected_exact = {
        "pkgname": "qdrant-web-ui",
        "pkgbase": "qdrant-web-ui",
        "xdata": "pkgtype=pkg",
        "pkgver": "0.2.16-1",
        "pkgdesc": "Static dashboard assets for Qdrant",
        "url": "https://github.com/qdrant/qdrant-web-ui",
        "arch": "any",
        "license": "Apache-2.0",
        "makedepend": "python",
    }
    variable_single = {"builddate", "packager", "size"}
    allowed_fields = set(expected_exact) | variable_single
    unexpected_fields = sorted(set(parsed) - allowed_fields)
    if unexpected_fields:
        raise SystemExit(
            "unexpected package metadata field is not allowed: "
            + ", ".join(unexpected_fields)
        )

    for field, expected_value in expected_exact.items():
        values = parsed.get(field, [])
        if values != [expected_value]:
            raise SystemExit(
                f"package metadata {field} must occur exactly once with value "
                f"{expected_value}: {values or ['<missing>']}"
            )

    for field in sorted(variable_single):
        values = parsed.get(field, [])
        if len(values) != 1 or not values[0]:
            raise SystemExit(
                f"package metadata {field} must occur exactly once with a value"
            )
    for field in ("builddate", "size"):
        if not parsed[field][0].isdecimal():
            raise SystemExit(f"package metadata {field} must be a decimal integer")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()

    if not args.package.is_file():
        parser.error(f"package does not exist: {args.package}")

    member_names = subprocess.run(
        ["bsdtar", "-tf", str(args.package)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    listing = subprocess.run(
        ["bsdtar", "--numeric-owner", "-tvf", str(args.package)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    validate_archive_members(member_names, listing)

    with tempfile.TemporaryDirectory(prefix="qdrant-web-ui-verify-") as tmp:
        root = Path(tmp)
        subprocess.run(
            ["bsdtar", "-xf", str(args.package), "-C", str(root)],
            check=True,
        )
        reject_unsafe_extracted_entries(root)
        reject_unexpected_extracted_payload(root)
        required_metadata = tuple(
            root / name for name in (".PKGINFO", ".BUILDINFO", ".MTREE")
        )
        missing_metadata = sorted(
            item.name for item in required_metadata if not item.is_file()
        )
        if missing_metadata:
            raise SystemExit(
                "missing required package metadata: " + ", ".join(missing_metadata)
            )
        metadata = (root / ".PKGINFO").read_text()
        validate_package_metadata(metadata)

        install_hook = root / ".INSTALL"
        if install_hook.exists() or install_hook.is_symlink():
            raise SystemExit("unexpected package install hook: .INSTALL")

        web_root = root / "usr/share/qdrant/web-ui"
        license_file = root / "usr/share/licenses/qdrant-web-ui/LICENSE"

        required = {
            web_root / "index.html",
            web_root / "manifest.json",
            web_root / "openapi.json",
            web_root / "qdrant-web-ui.spdx.json",
            license_file,
        }
        required.update(web_root.glob("assets/index-*.js"))
        required.update(web_root.glob("assets/editor.worker-*.js"))
        required.update(web_root.glob("assets/json.worker-*.js"))
        required.update(web_root.glob("assets/graph_layout_wasm_bg-*.wasm"))

        missing_payload = sorted(
            str(item.relative_to(root)) for item in required if not item.is_file()
        )
        if missing_payload:
            raise SystemExit("missing package payload: " + ", ".join(missing_payload))

        if len(list(web_root.glob("assets/index-*.js"))) != 1:
            raise SystemExit("expected exactly one dashboard application bundle")
        if len(list(web_root.glob("assets/editor.worker-*.js"))) != 1:
            raise SystemExit("expected exactly one Monaco editor worker")
        if len(list(web_root.glob("assets/json.worker-*.js"))) != 1:
            raise SystemExit("expected exactly one Monaco JSON worker")
        if len(list(web_root.glob("assets/graph_layout_wasm_bg-*.wasm"))) != 1:
            raise SystemExit("expected exactly one graph-layout WASM module")

        main_bundle = next(iter(web_root.glob("assets/index-*.js")))
        bundle_text = main_bundle.read_text()
        forbidden_runtime_urls = {
            "https://qdrant.tech/web-ui-info.json",
            "snapshots.qdrant.io",
        }
        present_urls = sorted(
            item for item in forbidden_runtime_urls if item in bundle_text
        )
        if present_urls:
            raise SystemExit(
                "external runtime URL remains in dashboard bundle: "
                + ", ".join(present_urls)
            )

        expected_local_urls = {
            "/cloud/data.json",
            "/dashboard/web-ui-info.json",
            "/dashboard/datasets.json",
        }
        missing_local_urls = sorted(
            item for item in expected_local_urls if item not in bundle_text
        )
        if missing_local_urls:
            raise SystemExit(
                "missing package-owned dashboard URL: " + ", ".join(missing_local_urls)
            )

        expected_json = {
            web_root / "cloud/data.json": b"null\n",
            web_root / "web-ui-info.json": b"{}\n",
            web_root / "datasets.json": b"[]\n",
        }
        bad_json = sorted(
            str(item.relative_to(root))
            for item, expected_bytes in expected_json.items()
            if not item.is_file() or item.read_bytes() != expected_bytes
        )
        if bad_json:
            raise SystemExit(
                "missing or unexpected package-owned JSON: " + ", ".join(bad_json)
            )

        forbidden_payload_parts = {
            "node_modules",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
        }
        bad_payload = sorted(
            str(item.relative_to(root))
            for item in root.rglob("*")
            if forbidden_payload_parts.intersection(item.parts)
        )
        if bad_payload:
            raise SystemExit(
                "runtime bootstrap payload is not allowed: " + ", ".join(bad_payload)
            )

        license_hash = hashlib.sha256(license_file.read_bytes()).hexdigest()
        if (
            license_hash
            != "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
        ):
            raise SystemExit(f"unexpected Apache license SHA-256: {license_hash}")

    print("qdrant-web-ui package contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
