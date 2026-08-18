import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_MANIFEST = REPO_ROOT / "tools" / "repository_manifest.py"


class RepositoryManifestTests(unittest.TestCase):
    def _run_manifest(self, repository: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPOSITORY_MANIFEST), str(repository)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_records_flat_file_and_symlink_metadata_with_nanosecond_mtimes(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            repository = Path(temporary) / "repo"
            repository.mkdir()
            package = repository / "fixture-1-1-x86_64.pkg.tar.zst"
            package.write_bytes(b"package payload\n")
            package.chmod(0o640)
            os.utime(package, ns=(1_800_000_000_123_456_789,) * 2)
            database = repository / "fixture.db"
            database.symlink_to(package.name)
            os.utime(
                database,
                ns=(1_800_000_000_987_654_321,) * 2,
                follow_symlinks=False,
            )
            package_metadata = package.stat()
            database_metadata = database.lstat()

            result = subprocess.run(
                [sys.executable, str(REPOSITORY_MANIFEST), str(repository)],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        self.assertEqual(
            json.loads(result.stdout),
            {
                "entries": [
                    {
                        "gid": package_metadata.st_gid,
                        "mode": f"{stat.S_IMODE(package_metadata.st_mode):04o}",
                        "mtimeNs": package_metadata.st_mtime_ns,
                        "name": package.name,
                        "sha256": hashlib.sha256(b"package payload\n").hexdigest(),
                        "size": len(b"package payload\n"),
                        "type": "file",
                        "uid": package_metadata.st_uid,
                    },
                    {
                        "gid": database_metadata.st_gid,
                        "mode": f"{stat.S_IMODE(database_metadata.st_mode):04o}",
                        "mtimeNs": database_metadata.st_mtime_ns,
                        "name": database.name,
                        "target": package.name,
                        "type": "symlink",
                        "uid": database_metadata.st_uid,
                    },
                ],
                "schemaVersion": 3,
            },
        )

    def test_rejects_symlink_chain_in_flat_repository(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            repository = Path(temporary) / "repo"
            repository.mkdir()
            package = repository / "fixture-1-1-x86_64.pkg.tar.zst"
            package.write_bytes(b"package payload\n")
            direct_alias = repository / "fixture.db.tar.zst"
            direct_alias.symlink_to(package.name)
            chained_alias = repository / "fixture.db"
            chained_alias.symlink_to(direct_alias.name)

            result = self._run_manifest(repository)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "repository symlink target must be a direct regular file: "
            "fixture.db -> fixture.db.tar.zst",
            result.stderr,
        )

    def test_rejects_non_directory_and_symlinked_repository_roots(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            file_root = root / "not-a-repository"
            file_root.write_bytes(b"not a directory\n")
            real_root = root / "repository"
            real_root.mkdir()
            linked_root = root / "linked-repository"
            linked_root.symlink_to(real_root, target_is_directory=True)

            cases = (file_root, linked_root)
            for repository in cases:
                with self.subTest(repository=repository.name):
                    result = self._run_manifest(repository)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(
                        f"repository must be a real directory: {repository}",
                        result.stderr,
                    )

    def test_rejects_unsafe_or_missing_symlink_targets(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            cases = (
                ("slash", "subdirectory/payload", "unsafe repository symlink"),
                ("dot", ".", "unsafe repository symlink"),
                ("dotdot", "..", "unsafe repository symlink"),
                (
                    "missing",
                    "missing.pkg.tar.zst",
                    "repository symlink target is missing",
                ),
            )
            for name, target, message in cases:
                with self.subTest(name=name):
                    repository = root / name
                    repository.mkdir()
                    alias = repository / "fixture.db"
                    alias.symlink_to(target)
                    result = self._run_manifest(repository)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(
                        f"{message}: fixture.db -> {target}", result.stderr
                    )

    def test_rejects_unsupported_directory_and_fifo_entries(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            cases = ("directory", "fifo")
            for entry_type in cases:
                with self.subTest(entry_type=entry_type):
                    repository = root / entry_type
                    repository.mkdir()
                    unsupported = repository / "unsupported"
                    if entry_type == "directory":
                        unsupported.mkdir()
                    else:
                        os.mkfifo(unsupported)
                    result = self._run_manifest(repository)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(
                        "unsupported repository entry: unsupported", result.stderr
                    )


if __name__ == "__main__":
    unittest.main()
