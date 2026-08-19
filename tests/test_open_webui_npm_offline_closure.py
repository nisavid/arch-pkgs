import base64
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "packages" / "open-webui" / "npm-offline-closure.py"
RELEASE_MANIFEST = (
    REPO_ROOT / "packages" / "open-webui" / "npm-offline-closure-manifest.json"
)


def make_package_tarball(path: Path, name: str, version: str) -> str:
    package_json = json.dumps(
        {"name": name, "version": version, "main": "index.js"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    members = {
        "package/index.js": b"module.exports = 'offline';\n",
        "package/package.json": package_json + b"\n",
    }
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for member_name, payload in sorted(members.items()):
            info = tarfile.TarInfo(member_name)
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha512(path.read_bytes()).digest()
    return "sha512-" + base64.b64encode(digest).decode()


class OpenWebUINpmOfflineClosureTests(unittest.TestCase):
    def test_release_manifest_binds_the_exact_open_webui_011_graph(self):
        manifest_bytes = RELEASE_MANIFEST.read_bytes()
        manifest = json.loads(manifest_bytes)

        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(),
            "a45a76bc4d81fafeae69c61a3de2e1dc471e103069f43a03709f474167beedc7",
        )
        self.assertEqual(
            manifest["lockfile_sha256"],
            "664ff34f1d8273e2e6a7a6b6437d27fd195d289ea3df9c56cdd30c4afbd62b02",
        )
        self.assertEqual(
            manifest["project"], {"name": "open-webui", "version": "0.11.0"}
        )
        self.assertEqual(manifest["package_record_count"], 1275)
        self.assertEqual(manifest["unique_tarball_count"], 1233)
        self.assertEqual(
            sum(entry["size"] for entry in manifest["tarballs"]), 886851096
        )
        self.assertEqual(
            sum(len(entry["lock_paths"]) for entry in manifest["tarballs"]),
            1275,
        )
        urls = [entry["url"] for entry in manifest["tarballs"]]
        self.assertEqual(urls, sorted(set(urls)))
        self.assertTrue(
            all(url.startswith("https://registry.npmjs.org/") for url in urls)
        )
        self.assertTrue(
            all(
                entry["integrity"].startswith("sha512-")
                for entry in manifest["tarballs"]
            )
        )

    def test_materializer_binds_every_lock_record_to_an_integrity_checked_tarball(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tarball = root / "fixture-dependency-1.0.0.tgz"
            integrity = make_package_tarball(tarball, "fixture-dependency", "1.0.0")
            lock = {
                "name": "fixture-app",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {
                        "name": "fixture-app",
                        "version": "1.0.0",
                        "dependencies": {"fixture-dependency": "1.0.0"},
                    },
                    "node_modules/fixture-dependency": {
                        "version": "1.0.0",
                        "resolved": tarball.as_uri(),
                        "integrity": integrity,
                    },
                },
            }
            lock_path = root / "package-lock.json"
            lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            archive_path = root / "closure.tar.zst"
            cache_path = root / "cache"

            result = subprocess.run(
                [
                    str(MATERIALIZER),
                    "materialize",
                    "--lock",
                    str(lock_path),
                    "--manifest",
                    str(manifest_path),
                    "--archive",
                    str(archive_path),
                    "--cache",
                    str(cache_path),
                    "--allow-file-urls",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["lockfile_sha256"],
                hashlib.sha256(lock_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(manifest["package_record_count"], 1)
            self.assertEqual(manifest["unique_tarball_count"], 1)
            self.assertEqual(manifest["tarballs"][0]["integrity"], integrity)
            self.assertEqual(
                manifest["tarballs"][0]["lock_paths"],
                ["node_modules/fixture-dependency"],
            )
            self.assertTrue(archive_path.is_file())

    def test_raw_bundle_is_deterministic_and_seeds_a_networkless_npm_ci(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap is required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tarball = root / "fixture-dependency-1.0.0.tgz"
            integrity = make_package_tarball(tarball, "fixture-dependency", "1.0.0")
            package = {
                "name": "fixture-app",
                "version": "1.0.0",
                "private": True,
                "dependencies": {"fixture-dependency": "1.0.0"},
            }
            lock = {
                "name": "fixture-app",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": package,
                    "node_modules/fixture-dependency": {
                        "version": "1.0.0",
                        "resolved": tarball.as_uri(),
                        "integrity": integrity,
                    },
                },
            }
            package_path = root / "package.json"
            lock_path = root / "package-lock.json"
            package_path.write_text(
                json.dumps(package, indent=2) + "\n", encoding="utf-8"
            )
            lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
            cache_path = root / "raw-cache"
            artifacts = []
            for suffix in ("first", "second"):
                manifest_path = root / f"manifest-{suffix}.json"
                archive_path = root / f"closure-{suffix}.tar.zst"
                result = subprocess.run(
                    [
                        str(MATERIALIZER),
                        "materialize",
                        "--lock",
                        str(lock_path),
                        "--manifest",
                        str(manifest_path),
                        "--archive",
                        str(archive_path),
                        "--cache",
                        str(cache_path),
                        "--allow-file-urls",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                artifacts.append((manifest_path, archive_path))

            self.assertEqual(artifacts[0][0].read_bytes(), artifacts[1][0].read_bytes())
            self.assertEqual(artifacts[0][1].read_bytes(), artifacts[1][1].read_bytes())

            npm_cache = root / "npm-cache"
            archive_link = root / "makepkg-noextract-link.tar.zst"
            archive_link.symlink_to(artifacts[0][1])
            seed = subprocess.run(
                [
                    str(MATERIALIZER),
                    "seed",
                    "--lock",
                    str(lock_path),
                    "--manifest",
                    str(artifacts[0][0]),
                    "--archive",
                    str(archive_link),
                    "--npm-cache",
                    str(npm_cache),
                    "--allow-file-urls",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(seed.returncode, 0, seed.stderr)
            tarball.unlink()

            environment = {
                **os.environ,
                "PATH": "/usr/bin:/bin",
                "NPM_CONFIG_AUDIT": "false",
                "NPM_CONFIG_FUND": "false",
                "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            }
            install = subprocess.run(
                [
                    "bwrap",
                    "--unshare-net",
                    "--bind",
                    "/",
                    "/",
                    "/usr/bin/npm",
                    "ci",
                    "--offline",
                    "--ignore-scripts",
                    "--cache",
                    str(npm_cache),
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            self.assertEqual(
                (root / "node_modules/fixture-dependency/index.js").read_text(
                    encoding="utf-8"
                ),
                "module.exports = 'offline';\n",
            )

    def test_seed_rejects_a_path_traversal_member_before_writing_the_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tarball = root / "fixture-dependency-1.0.0.tgz"
            integrity = make_package_tarball(tarball, "fixture-dependency", "1.0.0")
            lock = {
                "name": "fixture-app",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {"name": "fixture-app", "version": "1.0.0"},
                    "node_modules/fixture-dependency": {
                        "version": "1.0.0",
                        "resolved": tarball.as_uri(),
                        "integrity": integrity,
                    },
                },
            }
            lock_path = root / "package-lock.json"
            lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            valid_archive = root / "valid.tar.zst"
            materialize = subprocess.run(
                [
                    str(MATERIALIZER),
                    "materialize",
                    "--lock",
                    str(lock_path),
                    "--manifest",
                    str(manifest_path),
                    "--archive",
                    str(valid_archive),
                    "--cache",
                    str(root / "raw-cache"),
                    "--allow-file-urls",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(materialize.returncode, 0, materialize.stderr)

            uncompressed = io.BytesIO()
            with tarfile.open(fileobj=uncompressed, mode="w") as archive:
                payload = b"must not escape\n"
                info = tarfile.TarInfo("../escaped")
                info.size = len(payload)
                info.mode = 0o644
                info.uid = 0
                info.gid = 0
                info.uname = "root"
                info.gname = "root"
                info.mtime = 0
                archive.addfile(info, io.BytesIO(payload))
            compressed = subprocess.run(
                ["zstd", "-q", "-3", "-c"],
                input=uncompressed.getvalue(),
                capture_output=True,
                check=True,
            )
            malicious_archive = root / "malicious.tar.zst"
            malicious_archive.write_bytes(compressed.stdout)
            npm_cache = root / "npm-cache"

            seed = subprocess.run(
                [
                    str(MATERIALIZER),
                    "seed",
                    "--lock",
                    str(lock_path),
                    "--manifest",
                    str(manifest_path),
                    "--archive",
                    str(malicious_archive),
                    "--npm-cache",
                    str(npm_cache),
                    "--allow-file-urls",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(seed.returncode, 2)
            self.assertIn("unsafe or noncanonical archive member", seed.stderr)
            self.assertFalse((root.parent / "escaped").exists())
            self.assertFalse(npm_cache.exists())


if __name__ == "__main__":
    unittest.main()
