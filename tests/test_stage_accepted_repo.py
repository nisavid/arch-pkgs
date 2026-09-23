import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STAGER = REPO_ROOT / "tools" / "stage_accepted_repo.py"
REPOSITORY_MANIFEST = REPO_ROOT / "tools" / "repository_manifest.py"
REQUIRED_TOOLS = ("bsdtar", "repo-add", "zstd")
MISSING_TOOLS = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database_records(database: Path) -> set[tuple]:
    records = set()
    members = subprocess.run(
        ["bsdtar", "-tf", str(database)], text=True, stdout=subprocess.PIPE, check=True
    ).stdout.splitlines()
    for member in members:
        if not member.endswith("/desc"):
            continue
        lines = subprocess.run(
            ["bsdtar", "-xOf", str(database), member],
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.splitlines()

        def field(key: str) -> str:
            return lines[lines.index(f"%{key}%") + 1]

        records.add(
            (field("NAME"), field("FILENAME"), int(field("CSIZE")), field("SHA256SUM"))
        )
    return records


@unittest.skipIf(MISSING_TOOLS, f"missing required tools: {MISSING_TOOLS}")
class StageAcceptedRepoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        self.staging = self.root / "staging" / "x86_64"
        self.manifest_path = self.root / "manifest.json"
        self.archives = [
            self._create_package("alpha", "1.0-1", "x86_64", "lane-a/abc1234"),
            self._create_package("beta", "2.1-3", "any", "lane-b"),
        ]
        # A same-named archive with different bytes must never be selected.
        self._create_package("alpha", "1.0-1", "x86_64", "lane-a/decoy", payload="decoy")

    def tearDown(self):
        self.temp.cleanup()

    def _create_package(
        self,
        name: str,
        version: str,
        arch: str,
        source: str,
        *,
        pkgname: str | None = None,
        payload: str = "payload",
    ) -> dict:
        directory = self.store / source
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{name}-{version}-{arch}.pkg.tar.zst"
        package = directory / filename
        archive = package.with_suffix("")
        pkginfo = textwrap.dedent(
            f"""\
            pkgname = {pkgname or name}
            pkgbase = {pkgname or name}
            pkgver = {version}
            arch = {arch}
            """
        ).encode()
        with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as output:
            for member_name, content in {
                ".PKGINFO": pkginfo,
                f"usr/share/{name}/identity": f"{name} {payload}\n".encode(),
            }.items():
                member = tarfile.TarInfo(member_name)
                member.size = len(content)
                member.mode = 0o644
                member.mtime = 1_786_914_731
                output.addfile(member, fileobj=io.BytesIO(content))
        subprocess.run(["zstd", "-q", "-f", str(archive), "-o", str(package)], check=True)
        archive.unlink()
        return {
            "package": name,
            "version": version,
            "arch": arch,
            "filename": filename,
            "size": package.stat().st_size,
            "sha256": _sha256(package),
            "source": source,
        }

    def _write_manifest(self, archives=None, **extra) -> Path:
        document = {
            "schema": "arch-pkgs-accepted-publication/v1",
            "repository": {"name": "nisavid", "arch": "x86_64"},
            "archives": self.archives if archives is None else archives,
            **extra,
        }
        self.manifest_path.write_text(json.dumps(document, indent=2) + "\n")
        return self.manifest_path

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(STAGER), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def _stage(self, manifest: Path | None = None) -> subprocess.CompletedProcess[str]:
        return self._run(
            "stage",
            "--manifest",
            str(manifest or self._write_manifest()),
            "--store-root",
            str(self.store),
            "--repo-dir",
            str(self.staging),
            "--repo-name",
            "nisavid",
        )

    def _verify(self, repo_dir: Path) -> subprocess.CompletedProcess[str]:
        return self._run(
            "verify", "--manifest", str(self.manifest_path), "--repo-dir", str(repo_dir)
        )

    def _staged(self) -> Path:
        result = self._stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.staging

    def _manifest_sha(self, directory: Path) -> str:
        output = subprocess.run(
            [sys.executable, str(REPOSITORY_MANIFEST), str(directory)],
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
        return hashlib.sha256(output).hexdigest()

    def _assert_refused(self, result, message: str) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def test_stages_exact_copies_whose_database_records_equal_the_manifest(self):
        staging = self._staged()

        self.assertEqual(
            sorted(path.name for path in staging.iterdir()),
            sorted(
                [record["filename"] for record in self.archives]
                + ["nisavid.db", "nisavid.db.tar.zst", "nisavid.files", "nisavid.files.tar.zst"]
            ),
        )
        self.assertEqual(
            _database_records(staging / "nisavid.db.tar.zst"),
            {
                (r["package"], r["filename"], r["size"], r["sha256"])
                for r in self.archives
            },
        )
        for record in self.archives:
            staged = staging / record["filename"]
            source = self.store / record["source"] / record["filename"]
            self.assertEqual(staged.stat().st_nlink, 1)
            self.assertNotEqual(staged.stat().st_ino, source.stat().st_ino)
        self.assertFalse(staging.with_name("x86_64.writer.lock").exists())
        self.assertEqual(sorted(p.name for p in staging.parent.iterdir()), ["x86_64"])
        self.assertEqual(self._verify(staging).returncode, 0)

    def test_prints_the_staging_repository_manifest_sha(self):
        result = self._stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            f"Repository-manifest SHA-256: {self._manifest_sha(self.staging)}",
            result.stdout,
        )

    def test_refuses_size_mismatch(self):
        archives = [dict(self.archives[0], size=self.archives[0]["size"] + 1), self.archives[1]]
        self._assert_refused(
            self._stage(self._write_manifest(archives)), "size does not match the manifest"
        )
        self.assertFalse(self.staging.exists())

    def test_refuses_sha256_mismatch_from_same_named_decoy(self):
        decoy = self.store / "lane-a" / "decoy" / self.archives[0]["filename"]
        archives = [
            dict(self.archives[0], source="lane-a/decoy", size=decoy.stat().st_size),
            self.archives[1],
        ]
        self._assert_refused(
            self._stage(self._write_manifest(archives)), "sha256 does not match the manifest"
        )
        self.assertFalse(self.staging.exists())

    def test_refuses_missing_archive(self):
        archives = [*self.archives, dict(self.archives[1], source="lane-c")]
        archives[2].update(package="gamma", filename="gamma-2.1-3-any.pkg.tar.zst")
        self._assert_refused(
            self._stage(self._write_manifest(archives)), "missing accepted archive"
        )

    def test_refuses_duplicate_package_and_filename(self):
        result = self._stage(self._write_manifest([*self.archives, self.archives[0]]))
        self._assert_refused(result, "duplicate package: alpha")
        self.assertIn("duplicate filename", result.stderr)

    def test_refuses_retired_chatgpt_name(self):
        retired = self._create_package("codex-app", "26.609.41114-1", "x86_64", "retired")
        self._assert_refused(
            self._stage(self._write_manifest([*self.archives, retired])),
            "retired ChatGPT producer is refused: codex-app",
        )

    def test_refuses_nonempty_staging_directory(self):
        self.staging.mkdir(parents=True)
        (self.staging / "leftover").write_text("x")
        self._assert_refused(self._stage(), "must be absent or empty")
        self.assertEqual([p.name for p in self.staging.iterdir()], ["leftover"])

    def test_accepts_existing_empty_staging_directory(self):
        self.staging.mkdir(parents=True)
        self.assertEqual(self._stage().returncode, 0)

    def test_refuses_held_writer_lock(self):
        self.staging.parent.mkdir(parents=True)
        self.staging.with_name("x86_64.writer.lock").mkdir()
        self._assert_refused(self._stage(), "writer lock is held")
        self.assertTrue(self.staging.with_name("x86_64.writer.lock").is_dir())

    def test_refuses_pkginfo_identity_mismatch(self):
        mislabeled = self._create_package(
            "gamma", "3.0-1", "x86_64", "lane-c", pkgname="not-gamma"
        )
        self._assert_refused(
            self._stage(self._write_manifest([*self.archives, mislabeled])),
            ".PKGINFO identity",
        )
        self.assertFalse(self.staging.exists())

    def test_refuses_source_outside_store(self):
        archives = [dict(self.archives[0], source="../elsewhere"), self.archives[1]]
        self._assert_refused(
            self._stage(self._write_manifest(archives)), "relative store subdirectory"
        )

    def test_verify_is_read_only(self):
        live = self._staged()
        before = self._manifest_sha(live)

        result = self._verify(live)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._manifest_sha(live), before)

    def test_verify_refuses_gitignore(self):
        live = self._staged()
        (live / ".gitignore").write_text("*\n!.gitignore\n")
        self._assert_refused(self._verify(live), "unexpected repository entry: .gitignore")

    def test_refuses_duplicate_keys_inside_a_record(self):
        accepted, decoy_source = self.archives[0], "lane-a/decoy"
        decoy = self.store / decoy_source / accepted["filename"]
        record = json.dumps(accepted)[:-1] + ", " + ", ".join(
            f"{json.dumps(key)}: {json.dumps(value)}"
            for key, value in (
                ("size", decoy.stat().st_size),
                ("sha256", _sha256(decoy)),
                ("source", decoy_source),
            )
        ) + "}"
        self.manifest_path.write_text(
            '{"schema": "arch-pkgs-accepted-publication/v1", '
            '"repository": {"name": "nisavid", "arch": "x86_64"}, '
            f'"archives": [{record}, {json.dumps(self.archives[1])}]}}\n'
        )
        self._assert_refused(self._stage(self.manifest_path), "duplicate JSON keys")
        self.assertFalse(self.staging.exists())

    def test_refuses_duplicate_top_level_keys(self):
        self.manifest_path.write_text(
            '{"schema": "arch-pkgs-accepted-publication/v1", '
            '"repository": {"name": "nisavid", "arch": "x86_64"}, '
            f'"archives": {json.dumps(self.archives[:1])}, '
            f'"archives": {json.dumps(self.archives)}}}\n'
        )
        self._assert_refused(self._stage(self.manifest_path), "duplicate JSON keys ['archives']")

    def test_refuses_foreign_arch_record(self):
        foreign = self._create_package("eps", "1-1", "aarch64", "lane-d")
        self._assert_refused(
            self._stage(self._write_manifest([*self.archives, foreign])),
            "arch aarch64 does not belong in repository arch x86_64",
        )
        self.assertFalse(self.staging.exists())

    def test_verify_refuses_extra_unlisted_archive(self):
        live = self._staged()
        extra = self._create_package("gamma", "3.0-1", "x86_64", "lane-c")
        shutil.copyfile(self.store / "lane-c" / extra["filename"], live / extra["filename"])
        self._assert_refused(self._verify(live), "unexpected repository entry: gamma")

    def test_verify_refuses_extra_database_record(self):
        live = self._staged()
        extra = self._create_package("gamma", "3.0-1", "x86_64", "lane-c")
        copy = live / extra["filename"]
        shutil.copyfile(self.store / "lane-c" / extra["filename"], copy)
        subprocess.run(
            ["repo-add", "-q", str(live / "nisavid.db.tar.zst"), str(copy)],
            capture_output=True,
            check=True,
        )
        for path in [copy, *live.glob("*.old")]:
            path.unlink()
        self._assert_refused(
            self._verify(live), "indexed archive is not in the manifest: gamma"
        )

    def test_verify_refuses_missing_record(self):
        live = self._staged()
        extra = self._create_package("gamma", "3.0-1", "x86_64", "lane-c")
        self._write_manifest([*self.archives, extra])
        self._assert_refused(self._verify(live), "manifest archive is not indexed: gamma")

    def test_verify_refuses_tampered_archive(self):
        live = self._staged()
        target = live / self.archives[0]["filename"]
        data = bytearray(target.read_bytes())
        data[-1] ^= 0xFF
        target.write_bytes(bytes(data))
        self._assert_refused(self._verify(live), "archive bytes do not match the manifest")

    def test_receipt_records_public_identities_without_private_paths(self):
        live = self._staged()
        previous = self.root / "published" / "x86_64.previous.20260922T000000Z.1234"
        previous.mkdir(parents=True)
        old = self._create_package("legacy", "0.9-1", "any", "old")
        shutil.copyfile(self.store / "old" / old["filename"], previous / old["filename"])
        subprocess.run(
            ["repo-add", "-q", str(previous / "nisavid.db.tar.zst"), str(previous / old["filename"])],
            capture_output=True,
            check=True,
        )
        dispositions = [
            {"identity": "legacy 0.9-1", "disposition": "knowingly-foreign", "note": "deferred"},
            {"identity": "alpha 1.0-1", "disposition": "kept-eligible"},
        ]
        manifest = self._write_manifest(dispositions=dispositions)
        output = self.root / "receipt.json"

        result = self._run(
            "receipt",
            "--manifest", str(manifest),
            "--staging-manifest-sha", self._manifest_sha(live),
            "--live-dir", str(live),
            "--previous-dir", str(previous),
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        text = output.read_text()
        self.assertNotIn(str(self.root), text)
        receipt = json.loads(text)
        self.assertEqual(receipt["accepted_manifest_sha256"], _sha256(manifest))
        self.assertEqual(
            receipt["database"],
            {
                "nisavid.db.tar.zst": _sha256(live / "nisavid.db.tar.zst"),
                "nisavid.files.tar.zst": _sha256(live / "nisavid.files.tar.zst"),
            },
        )
        self.assertEqual(receipt["publisher_verified_manifest_sha256"], self._manifest_sha(live))
        self.assertEqual(receipt["previous_copy"]["name"], previous.name)
        self.assertEqual(
            [record["filename"] for record in receipt["previous_copy"]["records"]],
            [old["filename"]],
        )
        self.assertEqual(receipt["identity_dispositions"], dispositions)
        self.assertEqual(
            {record["filename"] for record in receipt["published_records"]},
            {record["filename"] for record in self.archives},
        )

    def test_receipt_refuses_mismatched_publisher_sha(self):
        live = self._staged()
        result = self._run(
            "receipt",
            "--manifest", str(self.manifest_path),
            "--staging-manifest-sha", "0" * 64,
            "--live-dir", str(live),
            "--previous-dir", str(live),
        )
        self._assert_refused(result, "does not match the publisher-verified")

    def test_refuses_foreign_disposition_for_an_archive_record(self):
        manifest = self._write_manifest(
            dispositions=[{"identity": "alpha 1.0-1", "disposition": "knowingly-foreign"}]
        )
        self._assert_refused(self._stage(manifest), "an archive record cannot be knowingly-foreign")


if __name__ == "__main__":
    unittest.main()
