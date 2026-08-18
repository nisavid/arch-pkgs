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


if __name__ == "__main__":
    unittest.main()
