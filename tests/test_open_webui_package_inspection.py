import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = REPO_ROOT / "packages" / "open-webui" / "inspect-open-webui-package.py"
SITE = "opt/open-webui/lib/python3.14/site-packages"
CRITICAL_FILES = {
    "etc/open-webui/open-webui.env": (0o600, b"env\n"),
    "usr/bin/open-webui": (0o755, b"#!/bin/sh\n"),
    "usr/lib/systemd/system/open-webui.service": (0o644, b"[Service]\n"),
    "usr/lib/sysusers.d/open-webui.conf": (0o644, b"u open-webui\n"),
    "usr/lib/tmpfiles.d/open-webui.conf": (0o644, b"d /var/lib/open-webui\n"),
    "usr/lib/open-webui/open-webui-commission-admin": (0o755, b"#!/usr/bin/python\n"),
    "usr/lib/open-webui/open-webui-session-epoch-ledger": (
        0o755,
        b"#!/usr/bin/python\n",
    ),
    f"{SITE}/open_webui/retrieval/rag_gate.py": (0o644, b"class Gate: pass\n"),
    f"{SITE}/open_webui/utils/session_epoch.py": (0o644, b"EPOCH = 1\n"),
    "usr/share/licenses/open-webui/LICENSE": (0o644, b"license\n"),
    "usr/share/licenses/open-webui/LICENSE_HISTORY": (0o644, b"history\n"),
    "usr/share/licenses/open-webui/LICENSE_NOTICE": (0o644, b"notice\n"),
}


def file_info(
    name: str, body: bytes, mode: int = 0o644
) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(body)
    info.mode = mode
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    return info, body


def valid_members() -> list[tuple[tarfile.TarInfo, bytes]]:
    buildinfo = (
        b"pkgver = 0.11.0-3\n"
        b"pkgarch = x86_64\n"
        b"pkgbuild_sha256sum = aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        b"builddir = /var/tmp\n"
        b"startdir = /var/tmp\n"
    )
    pkginfo = (
        b"pkgname = open-webui\n"
        b"pkgbase = open-webui\n"
        b"pkgver = 0.11.0-3\n"
        b"arch = x86_64\n"
        b"size = 158\n"
        b"builddate = 1787172442\n"
    )
    members = [
        file_info(".BUILDINFO", buildinfo),
        file_info(".PKGINFO", pkginfo),
        file_info(".MTREE", gzip.compress(b"mtree\n", mtime=0)),
    ]
    members.extend(
        file_info(path, body, mode) for path, (mode, body) in CRITICAL_FILES.items()
    )
    members.append(
        file_info(
            f"{SITE}/open_webui/frontend/pyodide/numpy-2.4.3-py3-none-any.whl",
            b"browser wheel",
        )
    )
    return members


def write_archive(
    path: Path,
    members: list[tuple[tarfile.TarInfo, bytes | None]],
) -> None:
    with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as archive:
        for info, body in members:
            archive.addfile(info, None if body is None else io.BytesIO(body))


def run_inspector(archive: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSPECTOR), str(archive), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


class OpenWebUIPackageInspectionTests(unittest.TestCase):
    def test_cli_emits_a_deterministic_canonical_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "open-webui.pkg.tar"
            write_archive(archive, valid_members())
            expected_archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()

            first = run_inspector(archive)
            second = run_inspector(archive)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(
            first.stdout,
            json.dumps(json.loads(first.stdout), sort_keys=True, indent=2) + "\n",
        )
        receipt = json.loads(first.stdout)
        self.assertEqual(
            receipt["schema"], "arch-pkgs.open-webui.package-inspection.v1"
        )
        self.assertEqual(receipt["archive"]["sha256"], expected_archive_sha256)
        self.assertEqual(receipt["archive"]["duplicate_path_count"], 0)
        self.assertEqual(receipt["archive"]["unsafe_path_count"], 0)
        self.assertEqual(receipt["archive"]["non_root_member_count"], 0)
        self.assertEqual(receipt["archive"]["unsafe_mode_member_count"], 0)
        self.assertEqual(receipt["archive"]["link_member_count"], 0)
        self.assertTrue(receipt["metadata"]["build_paths_public_safe"])
        self.assertEqual(
            receipt["metadata"][".PKGINFO"]["fields"],
            {
                "architecture": "x86_64",
                "build_timestamp": 1787172442,
                "installed_size_bytes": 158,
                "package_base": "open-webui",
                "package_name": "open-webui",
                "package_version": "0.11.0-3",
            },
        )
        self.assertEqual(
            receipt["metadata"][".BUILDINFO"]["fields"],
            {
                "architecture": "x86_64",
                "package_version": "0.11.0-3",
                "pkgbuild_sha256": "a" * 64,
            },
        )
        self.assertEqual(receipt["metadata"][".MTREE"]["decoded_line_count"], 1)
        self.assertEqual(
            receipt["metadata"][".MTREE"]["decoded_sha256"],
            "af12c3edbb8c0eb0f1a230bb0eb1f3b8f5cf64c669d7311410154e5f79e9f395",
        )
        self.assertEqual(
            receipt["payload"]["server_provider_boundary"]["providers_absent"],
            (INSPECTOR.parent / "open-webui-system-providers.txt")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
        self.assertTrue(receipt["payload"]["server_provider_boundary"]["passed"])
        self.assertEqual(receipt["payload"]["pyodide_wheels"]["count"], 1)
        self.assertEqual(
            receipt["payload"]["pyodide_wheels"]["provider_exceptions"][0]["provider"],
            "numpy",
        )
        self.assertTrue(receipt["payload"]["installer_metadata_absent"])
        self.assertEqual(receipt["payload"]["frontend_entry_count"], 1)
        self.assertEqual(receipt["payload"]["directory_count"], 0)
        self.assertEqual(receipt["payload"]["regular_file_count"], 13)
        self.assertEqual(receipt["payload"]["regular_file_bytes"], 158)
        self.assertTrue(receipt["payload"]["installed_size_matches_pkginfo"])
        self.assertEqual(receipt["payload"]["private_distribution_count"], 0)
        self.assertEqual(
            receipt["payload"]["pyodide_payload"],
            {
                "file_count": 1,
                "manifest_algorithm": "For each lexically sorted relative path: path, NUL, byte count, NUL, file SHA-256, newline.",
                "manifest_sha256": "7ad0e413c037de5a9db275d82e19df8f1a665981f6f46e566f873f8c805c387f",
                "total_bytes": 13,
            },
        )
        self.assertTrue(receipt["residue"]["passed"])
        self.assertEqual(
            receipt["critical_files"]["etc/open-webui/open-webui.env"],
            {
                "mode": "0600",
                "owner": "root:root",
                "sha256": "367c9b4686a777259cfcbff592b674e7c523655a2eb413cf37e8125a72bb5cad",
                "size_bytes": 4,
            },
        )

    def test_manifest_identity_is_independent_of_archive_member_order(self):
        with tempfile.TemporaryDirectory() as directory:
            first_archive = Path(directory) / "first.pkg.tar"
            second_archive = Path(directory) / "second.pkg.tar"
            members = valid_members()
            write_archive(first_archive, members)
            write_archive(second_archive, list(reversed(members)))

            first = run_inspector(first_archive)
            second = run_inspector(second_archive)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_receipt = json.loads(first.stdout)
        second_receipt = json.loads(second.stdout)
        self.assertNotEqual(
            first_receipt["archive"]["sha256"], second_receipt["archive"]["sha256"]
        )
        self.assertEqual(
            first_receipt["archive"]["manifest_sha256"],
            second_receipt["archive"]["manifest_sha256"],
        )

    def test_output_option_writes_the_canonical_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "open-webui.pkg.tar"
            output = Path(directory) / "receipt.json"
            write_archive(archive, valid_members())

            result = run_inspector(archive, "--output", str(output))
            body = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            body, json.dumps(json.loads(body), sort_keys=True, indent=2) + "\n"
        )

    def test_output_aliases_archive_fail_without_modifying_it(self):
        for alias_kind in ("same path", "hardlink", "symlink"):
            with (
                self.subTest(alias_kind=alias_kind),
                tempfile.TemporaryDirectory() as directory,
            ):
                archive = Path(directory) / "open-webui.pkg.tar"
                write_archive(archive, valid_members())
                original = archive.read_bytes()
                if alias_kind == "same path":
                    output = archive
                elif alias_kind == "hardlink":
                    output = Path(directory) / "hardlink-receipt.json"
                    output.hardlink_to(archive)
                else:
                    output = Path(directory) / "symlink-receipt.json"
                    output.symlink_to(archive)

                result = run_inspector(archive, "--output", str(output))
                final_archive = archive.read_bytes()

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output aliases package archive", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(final_archive, original)

    def test_successful_output_atomically_replaces_an_existing_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "open-webui.pkg.tar"
            output = Path(directory) / "receipt.json"
            write_archive(archive, valid_members())
            output.write_text("stale receipt\n", encoding="utf-8")
            previous_inode = output.stat().st_ino

            result = run_inspector(archive, "--output", str(output))
            replacement_inode = output.stat().st_ino
            body = output.read_text(encoding="utf-8")
            temporary_files = list(Path(directory).glob(".receipt.json.*.tmp"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(replacement_inode, previous_inode)
        self.assertEqual(
            body, json.dumps(json.loads(body), sort_keys=True, indent=2) + "\n"
        )
        self.assertEqual(temporary_files, [])

    def test_malformed_archive_fails_without_writing_a_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "malformed.pkg.tar"
            output = Path(directory) / "receipt.json"
            archive.write_bytes(b"not an archive")

            result = run_inspector(archive, "--output", str(output))
            output_exists = output.exists()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("malformed or unsupported", result.stderr)
        self.assertFalse(output_exists)

    def test_unsafe_duplicate_non_root_and_special_members_fail_closed(self):
        cases: list[tuple[str, tarfile.TarInfo, bytes | None, str]] = []
        unsafe, unsafe_body = file_info("../escape", b"unsafe")
        cases.append(("unsafe", unsafe, unsafe_body, "unsafe path"))
        duplicate, duplicate_body = file_info(".PKGINFO", b"duplicate")
        cases.append(
            ("duplicate", duplicate, duplicate_body, "duplicate normalized path")
        )
        non_root, non_root_body = file_info("usr/share/non-root", b"owned")
        non_root.uid = 1000
        cases.append(("non-root", non_root, non_root_body, "non-root member"))
        named_non_root, named_non_root_body = file_info(
            "usr/share/named-non-root", b"owned"
        )
        named_non_root.uname = "builder"
        cases.append(
            ("named-non-root", named_non_root, named_non_root_body, "non-root member")
        )
        for label, mode in (
            ("setuid", 0o4755),
            ("setgid", 0o2755),
            ("world-writable", 0o666),
        ):
            unsafe_mode, unsafe_mode_body = file_info(
                f"usr/share/{label}", b"unsafe", mode
            )
            cases.append((label, unsafe_mode, unsafe_mode_body, "unsafe mode member"))
        symlink = tarfile.TarInfo("usr/share/unsafe-link")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "/etc/passwd"
        symlink.mode = 0o777
        cases.append(("symlink", symlink, None, "link member"))
        hardlink = tarfile.TarInfo("usr/share/unsafe-hardlink")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = ".PKGINFO"
        hardlink.mode = 0o644
        cases.append(("hardlink", hardlink, None, "link member"))
        fifo = tarfile.TarInfo("usr/share/unsafe-fifo")
        fifo.type = tarfile.FIFOTYPE
        fifo.mode = 0o644
        cases.append(("special", fifo, None, "unsupported member type"))

        for label, malicious, body, error_fragment in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "malicious.pkg.tar"
                write_archive(archive, [*valid_members(), (malicious, body)])

                result = run_inspector(archive)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error_fragment, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_host_specific_build_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "host-specific.pkg.tar"
            members = valid_members()
            members[0] = file_info(
                ".BUILDINFO",
                b"builddir = /var/tmp/job-123\nstartdir = /var/tmp/job-123\n",
            )
            write_archive(archive, members)

            result = run_inspector(archive)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("generic public path", result.stderr)

    def test_metadata_identity_and_installed_size_mismatches_fail_closed(self):
        cases = {
            "identity": (0, b"pkgver = 0.11.0-4", "package identities differ"),
            "installed size": (1, b"size = 159", "regular-file bytes differ"),
        }
        for label, (member_index, replacement, error_fragment) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "metadata-mismatch.pkg.tar"
                members = valid_members()
                info, body = members[member_index]
                if label == "identity":
                    changed = body.replace(b"pkgver = 0.11.0-3", replacement)
                else:
                    changed = body.replace(b"size = 158", replacement)
                members[member_index] = file_info(info.name, changed, info.mode)
                write_archive(archive, members)

                result = run_inspector(archive)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error_fragment, result.stderr)

    def test_server_provider_payload_fails_but_browser_wheels_are_enumerated(self):
        provider_cases = {
            "distribution": file_info(
                f"{SITE}/numpy-2.4.3.dist-info/METADATA",
                b"Name: numpy\nVersion: 2.4.3\n",
            ),
            "top-level root": file_info(f"{SITE}/numpy/__init__.py", b""),
        }
        for label, malicious in provider_cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "provider.pkg.tar"
                write_archive(archive, [*valid_members(), malicious])

                result = run_inspector(archive)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("server-side externalized provider payload", result.stderr)

    def test_nearby_distribution_names_do_not_match_externalized_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "nearby-name.pkg.tar"
            dist_metadata = b"Name: numpy-financial\nVersion: 1.0\n"
            nearby_wheel = b"nearby browser wheel"
            members = valid_members()
            members[1] = file_info(
                ".PKGINFO",
                (
                    b"pkgname = open-webui\n"
                    b"pkgbase = open-webui\n"
                    b"pkgver = 0.11.0-3\n"
                    b"arch = x86_64\n"
                    + f"size = {158 + len(dist_metadata) + len(nearby_wheel)}\n".encode()
                    + b"builddate = 1787172442\n"
                ),
            )
            write_archive(
                archive,
                [
                    *members,
                    file_info(
                        f"{SITE}/numpy_financial-1.0.dist-info/METADATA",
                        dist_metadata,
                    ),
                    file_info(
                        f"{SITE}/open_webui/frontend/pyodide/numpy_financial-1.0-py3-none-any.whl",
                        nearby_wheel,
                    ),
                ],
            )

            result = run_inspector(archive)

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["payload"]["pyodide_wheels"]["count"], 2)
        self.assertEqual(
            receipt["payload"]["pyodide_wheels"]["provider_exception_count"], 1
        )

    def test_installer_metadata_and_build_input_residue_fail_closed(self):
        residue_cases = {
            ".lock": file_info(f"{SITE}/.lock", b""),
            "uv_cache.json": file_info(
                f"{SITE}/fixture-1.0.dist-info/uv_cache.json", b"{}"
            ),
            "node_modules": file_info("opt/open-webui/node_modules/module.js", b""),
            "closure archive": file_info(
                "opt/open-webui/open-webui-npm-offline-closure-0.11.0.tar.zst",
                b"archive",
            ),
            "build home": file_info("opt/open-webui/build-home/state", b""),
            "uv cache": file_info("opt/open-webui/uv-cache/state", b""),
            "Cypress cache": file_info("opt/open-webui/cypress-cache/state", b""),
            "uv Python": file_info("opt/open-webui/uv-python/state", b""),
        }
        for label, malicious in residue_cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "residue.pkg.tar"
                write_archive(archive, [*valid_members(), malicious])

                result = run_inspector(archive)

            self.assertNotEqual(result.returncode, 0)
            if label in {".lock", "uv_cache.json"}:
                self.assertIn("uv installer metadata", result.stderr)
            else:
                self.assertIn("build-input or cache residue", result.stderr)


if __name__ == "__main__":
    unittest.main()
