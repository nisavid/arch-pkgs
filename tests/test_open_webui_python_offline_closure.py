from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from compression import zstd

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "packages" / "open-webui"
TOOL = PACKAGE_ROOT / "python-offline-closure.py"
LOCK = PACKAGE_ROOT / "open-webui-private-requirements.lock"


class OpenWebUiPythonOfflineClosureTests(unittest.TestCase):
    def run_tool(self, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *(str(argument) for argument in arguments)],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_lock_inventory_is_exactly_the_targeted_222_distributions(self) -> None:
        result = self.run_tool("inventory", "--lock", LOCK)

        self.assertEqual(result.returncode, 0, result.stderr)
        inventory = json.loads(result.stdout)
        self.assertEqual(inventory["format"], "open-webui-python-offline-closure-v1")
        self.assertEqual(inventory["target"], "cp314-manylinux_2_28_x86_64")
        self.assertEqual(inventory["distribution_count"], 222)
        self.assertEqual(len(inventory["requirements"]), 222)
        self.assertEqual(
            [entry["name"] for entry in inventory["requirements"]],
            sorted(entry["name"] for entry in inventory["requirements"]),
        )
        self.assertEqual(
            hashlib.sha256(LOCK.read_bytes()).hexdigest(), inventory["lock_sha256"]
        )

    def test_verified_wheelhouse_has_digest_bound_target_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir()
            artifact = wheelhouse / "example-1.0-py3-none-any.whl"
            artifact.write_bytes(b"immutable artifact\n")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            lock = root / "requirements.lock"
            lock.write_text(
                f"example==1.0 \\\n    --hash=sha256:{digest}\n", encoding="utf-8"
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "format": "open-webui-python-offline-closure-v1",
                        "target": "cp314-manylinux_2_28_x86_64",
                        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                        "distribution_count": 1,
                        "artifacts": [
                            {
                                "name": "example",
                                "version": "1.0",
                                "filename": artifact.name,
                                "url": "https://files.pythonhosted.org/example.whl",
                                "sha256": digest,
                                "size": artifact.stat().st_size,
                            }
                        ],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_tool(
                "verify",
                "--lock",
                lock,
                "--manifest",
                manifest,
                "--wheelhouse",
                wheelhouse,
                "--allow-partial",
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            artifact.write_bytes(b"tampered! artifact\n")
            tampered = self.run_tool(
                "verify",
                "--lock",
                lock,
                "--manifest",
                manifest,
                "--wheelhouse",
                wheelhouse,
                "--allow-partial",
            )
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("SHA-256", tampered.stderr)

    def test_verify_rejects_a_wheel_for_another_platform(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir()
            artifact = wheelhouse / "example-1.0-cp314-cp314-win_amd64.whl"
            artifact.write_bytes(b"wrong platform\n")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            lock = root / "requirements.lock"
            lock.write_text(
                f"example==1.0 {chr(92)}\n    --hash=sha256:{digest}\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "format": "open-webui-python-offline-closure-v1",
                        "target": "cp314-manylinux_2_28_x86_64",
                        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                        "distribution_count": 1,
                        "artifacts": [
                            {
                                "name": "example",
                                "version": "1.0",
                                "filename": artifact.name,
                                "url": "https://files.pythonhosted.org/example.whl",
                                "sha256": digest,
                                "size": artifact.stat().st_size,
                            }
                        ],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_tool(
                "verify",
                "--lock",
                lock,
                "--manifest",
                manifest,
                "--wheelhouse",
                wheelhouse,
                "--allow-partial",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "not compatible with cp314-manylinux_2_28_x86_64", result.stderr
            )

    def test_archive_is_byte_reproducible_and_has_only_manifested_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir()
            artifact = wheelhouse / "example-1.0-py3-none-any.whl"
            artifact.write_bytes(b"immutable artifact\n")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            lock = root / "requirements.lock"
            lock.write_text(
                f"example==1.0 \\\n    --hash=sha256:{digest}\n", encoding="utf-8"
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "format": "open-webui-python-offline-closure-v1",
                        "target": "cp314-manylinux_2_28_x86_64",
                        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                        "distribution_count": 1,
                        "artifacts": [
                            {
                                "name": "example",
                                "version": "1.0",
                                "filename": artifact.name,
                                "url": "https://files.pythonhosted.org/example.whl",
                                "sha256": digest,
                                "size": artifact.stat().st_size,
                            }
                        ],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            first = root / "first.tar.zst"
            second = root / "second.tar.zst"

            for output in (first, second):
                result = self.run_tool(
                    "archive",
                    "--lock",
                    lock,
                    "--manifest",
                    manifest,
                    "--wheelhouse",
                    wheelhouse,
                    "--output",
                    output,
                    "--allow-partial",
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            verified_archive = self.run_tool(
                "verify-archive",
                "--lock",
                lock,
                "--archive",
                first,
                "--allow-partial",
            )
            self.assertEqual(verified_archive.returncode, 0, verified_archive.stderr)
            with tarfile.open(
                fileobj=io.BytesIO(zstd.decompress(first.read_bytes()))
            ) as archive:
                self.assertEqual(
                    archive.getnames(),
                    [
                        "open-webui-python-offline-closure",
                        "open-webui-python-offline-closure/manifest.json",
                        f"open-webui-python-offline-closure/wheelhouse/{artifact.name}",
                    ],
                )

    def test_verify_archive_rejects_a_wheel_for_another_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            filename = "example-1.0-cp313-cp313-manylinux_2_28_x86_64.whl"
            payload = b"wrong interpreter\n"
            digest = hashlib.sha256(payload).hexdigest()
            lock = root / "requirements.lock"
            lock.write_text(
                f"example==1.0 {chr(92)}\n    --hash=sha256:{digest}\n",
                encoding="utf-8",
            )
            manifest_bytes = (
                json.dumps(
                    {
                        "format": "open-webui-python-offline-closure-v1",
                        "target": "cp314-manylinux_2_28_x86_64",
                        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                        "distribution_count": 1,
                        "artifacts": [
                            {
                                "name": "example",
                                "version": "1.0",
                                "filename": filename,
                                "url": "https://files.pythonhosted.org/example.whl",
                                "sha256": digest,
                                "size": len(payload),
                            }
                        ],
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            uncompressed = io.BytesIO()
            archive_root = "open-webui-python-offline-closure"
            with tarfile.open(
                fileobj=uncompressed, mode="w", format=tarfile.PAX_FORMAT
            ) as archive:
                for name, content, mode in (
                    (archive_root, None, 0o755),
                    (f"{archive_root}/manifest.json", manifest_bytes, 0o644),
                    (f"{archive_root}/wheelhouse/{filename}", payload, 0o644),
                ):
                    info = tarfile.TarInfo(name)
                    info.mode = mode
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = 0
                    if content is None:
                        info.type = tarfile.DIRTYPE
                        archive.addfile(info)
                    else:
                        info.size = len(content)
                        archive.addfile(info, io.BytesIO(content))
            closure = root / "closure.tar.zst"
            closure.write_bytes(zstd.compress(uncompressed.getvalue(), level=19))

            result = self.run_tool(
                "verify-archive",
                "--lock",
                lock,
                "--archive",
                closure,
                "--allow-partial",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "not compatible with cp314-manylinux_2_28_x86_64", result.stderr
            )

    def test_verify_archive_rejects_noncanonical_member_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir()
            artifact = wheelhouse / "example-1.0-py3-none-any.whl"
            artifact.write_bytes(b"immutable artifact\n")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            lock = root / "requirements.lock"
            lock.write_text(
                f"example==1.0 {chr(92)}\n    --hash=sha256:{digest}\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "format": "open-webui-python-offline-closure-v1",
                        "target": "cp314-manylinux_2_28_x86_64",
                        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                        "distribution_count": 1,
                        "artifacts": [
                            {
                                "name": "example",
                                "version": "1.0",
                                "filename": artifact.name,
                                "url": "https://files.pythonhosted.org/example.whl",
                                "sha256": digest,
                                "size": artifact.stat().st_size,
                            }
                        ],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            canonical = root / "canonical.tar.zst"
            archived = self.run_tool(
                "archive",
                "--lock",
                lock,
                "--manifest",
                manifest,
                "--wheelhouse",
                wheelhouse,
                "--output",
                canonical,
                "--allow-partial",
            )
            self.assertEqual(archived.returncode, 0, archived.stderr)

            uncompressed = io.BytesIO(zstd.decompress(canonical.read_bytes()))
            noncanonical = io.BytesIO()
            with (
                tarfile.open(fileobj=uncompressed, mode="r:") as source,
                tarfile.open(
                    fileobj=noncanonical, mode="w", format=tarfile.PAX_FORMAT
                ) as target,
            ):
                for member in source.getmembers():
                    payload = source.extractfile(member)
                    if member.name.endswith(".whl"):
                        member.mode = 0o755
                    target.addfile(member, payload)
            closure = root / "noncanonical.tar.zst"
            closure.write_bytes(zstd.compress(noncanonical.getvalue(), level=19))

            result = self.run_tool(
                "verify-archive",
                "--lock",
                lock,
                "--archive",
                closure,
                "--allow-partial",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("noncanonical archive metadata", result.stderr)

    def test_fresh_target_installs_from_wheelhouse_with_uv_offline_no_index(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            wheelhouse = fixture / "wheelhouse"
            wheelhouse.mkdir()
            wheel = wheelhouse / "offline_fixture-1.0-py3-none-any.whl"
            members = {
                "offline_fixture/__init__.py": b"VALUE = 'offline'\n",
                "offline_fixture-1.0.dist-info/METADATA": (
                    b"Metadata-Version: 2.1\nName: offline-fixture\nVersion: 1.0\n"
                ),
                "offline_fixture-1.0.dist-info/WHEEL": (
                    b"Wheel-Version: 1.0\nGenerator: arch-pkgs-test\n"
                    b"Root-Is-Purelib: true\nTag: py3-none-any\n"
                ),
            }
            records = []
            for name, content in members.items():
                digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
                records.append(
                    f"{name},sha256={digest.rstrip(b'=').decode()},{len(content)}"
                )
            record_name = "offline_fixture-1.0.dist-info/RECORD"
            records.append(f"{record_name},,")
            members[record_name] = ("\n".join(records) + "\n").encode()
            with zipfile.ZipFile(
                wheel, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for name in sorted(members):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    archive.writestr(info, members[name], compresslevel=9)
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            lock = fixture / "requirements.lock"
            lock.write_text(
                f"offline-fixture==1.0 \\\n    --hash=sha256:{digest}\n",
                encoding="utf-8",
            )
            manifest = fixture / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "format": "open-webui-python-offline-closure-v1",
                        "target": "cp314-manylinux_2_28_x86_64",
                        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                        "distribution_count": 1,
                        "artifacts": [
                            {
                                "name": "offline-fixture",
                                "version": "1.0",
                                "filename": wheel.name,
                                "url": (
                                    "https://files.pythonhosted.org/packages/"
                                    "offline_fixture-1.0-py3-none-any.whl"
                                ),
                                "sha256": digest,
                                "size": wheel.stat().st_size,
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            verified = self.run_tool(
                "verify",
                "--lock",
                lock,
                "--manifest",
                manifest,
                "--wheelhouse",
                wheelhouse,
                "--allow-partial",
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)

            target = fixture / "target"
            environment = os.environ.copy()
            environment.update(
                {
                    "HTTP_PROXY": "http://127.0.0.1:9",
                    "HTTPS_PROXY": "http://127.0.0.1:9",
                    "ALL_PROXY": "http://127.0.0.1:9",
                    "NO_PROXY": "",
                    "UV_CACHE_DIR": str(Path(temporary_directory) / "empty-cache"),
                }
            )
            result = subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--offline",
                    "--no-index",
                    "--find-links",
                    str(wheelhouse),
                    "--python",
                    "/usr/bin/python3.14",
                    "--target",
                    str(target),
                    "--require-hashes",
                    "--no-deps",
                    "-r",
                    str(lock),
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (target / "offline_fixture" / "__init__.py").read_text(),
                "VALUE = 'offline'\n",
            )


if __name__ == "__main__":
    unittest.main()
