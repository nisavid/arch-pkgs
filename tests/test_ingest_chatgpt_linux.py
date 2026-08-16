import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INGEST = REPO_ROOT / "tools" / "ingest_chatgpt.zsh"
PUBLISH = REPO_ROOT / "tools" / "publish_pacman_repo.zsh"
REQUIRED_TOOLS = ("git", "zsh", "zstd", "bsdtar", "repo-add", "repo-remove")
MISSING_TOOLS = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


@unittest.skipIf(MISSING_TOOLS, f"missing required tools: {MISSING_TOOLS}")
class ChatGPTLinuxIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.root = Path(self.temp.name)
        self.source = self.root / "chatgpt-linux"
        self.evidence = self.root / "evidence"
        self.repo = self.root / "repo"
        self.source.mkdir()
        self.evidence.mkdir()
        self.repo.mkdir()
        self._create_source_checkout()
        self.artifact = self._create_package(
            "chatgpt",
            "26.810.52044-1",
            {
                "usr/bin/chatgpt": b"launcher\n",
                "usr/bin/chatgpt-updater": b"updater\n",
                "usr/lib/systemd/user/chatgpt-updater.service": b"[Service]\n",
                "usr/share/applications/chatgpt.desktop": b"[Desktop Entry]\n",
                "opt/chatgpt/start.sh": b"start\n",
            },
        )
        self._create_evidence()
        self._create_helper_checkout()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.source), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.strip()

    def _create_source_checkout(self):
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        self._git("config", "user.name", "Fixture")
        self._git("config", "user.email", "fixture@example.invalid")
        self._git(
            "remote", "add", "origin", "https://github.com/nisavid/chatgpt-linux.git"
        )
        verifier = self.source / "scripts" / "lib" / "package-provenance.py"
        verifier.parent.mkdir(parents=True)
        verifier.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import hashlib
                import json
                import sys
                import tarfile

                def canonical(value):
                    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\\n").encode()

                command = sys.argv[1]
                if command == "tar-manifest":
                    entries = []
                    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as archive:
                        for member in archive:
                            path = member.name.removeprefix("./")
                            entry = {
                                "gid": member.gid,
                                "gname": member.gname,
                                "mode": f"{member.mode:04o}",
                                "mtime": str(member.mtime),
                                "path": path,
                                "paxHeaders": dict(sorted(member.pax_headers.items())),
                                "uid": member.uid,
                                "uname": member.uname,
                            }
                            if member.isfile():
                                content = archive.extractfile(member).read()
                                entry.update(type="file", size=len(content), sha256=hashlib.sha256(content).hexdigest())
                            elif member.isdir():
                                entry["type"] = "directory"
                            elif member.issym():
                                entry.update(type="symlink", target=member.linkname)
                            else:
                                raise SystemExit("unsupported fixture member")
                            entries.append(entry)
                    entries.sort(key=lambda entry: entry["path"].encode())
                    content = {"entries": entries, "schemaVersion": 1}
                    value = {**content, "manifestSha256": hashlib.sha256(canonical(content)).hexdigest()}
                    with open(sys.argv[2], "wb") as target:
                        target.write(canonical(value))
                elif command == "compare":
                    with open(sys.argv[2], encoding="utf-8") as expected, open(sys.argv[3], encoding="utf-8") as actual:
                        if json.load(expected) != json.load(actual):
                            raise SystemExit("manifest mismatch")
                else:
                    raise SystemExit(f"unsupported command: {command}")
                """
            ),
            encoding="utf-8",
        )
        verifier.chmod(0o755)
        self._git("add", ".")
        self._git("commit", "-qm", "fixture source")
        self.commit = self._git("rev-parse", "HEAD")
        self.tag = "fallback-fixture"
        self._git("tag", "-a", self.tag, "-m", "fixture fallback")
        self.tag_object = self._git("rev-parse", f"refs/tags/{self.tag}")

    def _create_package(self, name: str, version: str, files: dict[str, bytes]) -> Path:
        package = self.evidence / f"{name}-{version}-x86_64.pkg.tar.zst"
        tar_path = package.with_suffix("")
        pkginfo = textwrap.dedent(
            f"""\
            pkgname = {name}
            pkgbase = {name}
            pkgver = {version}
            arch = x86_64
            """
        ).encode()
        if name == "chatgpt":
            pkginfo += (
                b"provides = codex-app\n"
                b"provides = codex-desktop\n"
                b"conflict = codex-app\n"
                b"conflict = codex-desktop\n"
                b"replaces = codex-app\n"
                b"replaces = codex-desktop\n"
            )
        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
            for path, content in {".PKGINFO": pkginfo, **files}.items():
                info = tarfile.TarInfo(path)
                info.size = len(content)
                info.mode = 0o755 if path.startswith("usr/bin/") else 0o644
                info.mtime = 1_786_914_731
                archive.addfile(info, fileobj=io.BytesIO(content))
        subprocess.run(
            ["zstd", "-q", "-f", str(tar_path), "-o", str(package)], check=True
        )
        tar_path.unlink()
        return package

    def _create_evidence(self):
        manifest = self.evidence / "payload-manifest.json"
        with self.artifact.open("rb") as compressed:
            with subprocess.Popen(
                ["zstd", "-dc"], stdin=compressed, stdout=subprocess.PIPE
            ) as decompressor:
                try:
                    subprocess.run(
                        [
                            str(self.source / "scripts/lib/package-provenance.py"),
                            "tar-manifest",
                            str(manifest),
                        ],
                        stdin=decompressor.stdout,
                        check=True,
                    )
                finally:
                    decompressor.stdout.close()
            self.assertEqual(decompressor.returncode, 0)
        build_info = self.evidence / "build-info.json"
        decision = self.evidence / "upstream-dmg-decision.json"
        build_info.write_text(json.dumps({"source": {"commit": self.commit}}) + "\n")
        decision.write_text(json.dumps({"verdict": "accepted_with_warnings"}) + "\n")
        manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
        record = {
            "schemaVersion": 1,
            "recordedAt": "2026-08-16T22:09:57Z",
            "purpose": "retained-fallback-before-official-linux-app-evaluation",
            "source": {
                "repository": "https://github.com/nisavid/chatgpt-linux",
                "commit": self.commit,
                "tag": self.tag,
                "tagObject": self.tag_object,
                "tagTarget": self.commit,
            },
            "package": {
                "fileName": self.artifact.name,
                "name": "chatgpt",
                "version": "26.810.52044-1",
                "architecture": "x86_64",
                "sizeBytes": self.artifact.stat().st_size,
                "sha256": self._sha256(self.artifact),
                "updaterIncluded": True,
                "provides": ["codex-app", "codex-desktop"],
                "conflicts": ["codex-app", "codex-desktop"],
                "replaces": ["codex-app", "codex-desktop"],
            },
            "payloadManifest": {
                "fileName": manifest.name,
                "sizeBytes": manifest.stat().st_size,
                "fileSha256": self._sha256(manifest),
                "manifestSha256": manifest_value["manifestSha256"],
                "entryCount": len(manifest_value["entries"]),
            },
            "generationEvidence": {
                "acceptanceVerdict": "accepted_with_warnings",
                "blockerCount": 0,
                "inconclusiveReasonCount": 0,
                "optionalWarningCount": 0,
                "decisionFile": decision.name,
                "decisionFileSha256": self._sha256(decision),
                "buildInfoFile": build_info.name,
                "buildInfoFileSha256": self._sha256(build_info),
            },
        }
        self.record = self.evidence / "verification-record.json"
        self.record.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        self.record_sha256 = self._sha256(self.record)

    def _create_helper_checkout(self):
        helper_root = self.root / "helper"
        helper_tools = helper_root / "tools"
        helper_package = helper_root / "packages" / "chatgpt"
        helper_tools.mkdir(parents=True)
        helper_package.mkdir(parents=True)
        self.ingest = helper_tools / INGEST.name
        shutil.copy2(INGEST, self.ingest)
        record = json.loads(self.record.read_text(encoding="utf-8"))
        baseline = {
            "schemaVersion": 1,
            "source": record["source"],
            "package": record["package"],
            "payloadManifest": {
                key: record["payloadManifest"][key]
                for key in ("fileName", "fileSha256", "manifestSha256", "entryCount")
            },
            "verification": {
                "recordSha256": self.record_sha256,
                "generationDecisionSha256": record["generationEvidence"][
                    "decisionFileSha256"
                ],
                "buildInfoSha256": record["generationEvidence"][
                    "buildInfoFileSha256"
                ],
                "acceptanceVerdict": record["generationEvidence"][
                    "acceptanceVerdict"
                ],
                "blockerCount": record["generationEvidence"]["blockerCount"],
                "inconclusiveReasonCount": record["generationEvidence"][
                    "inconclusiveReasonCount"
                ],
                "optionalWarningCount": 0,
            },
        }
        (helper_package / "fallback-baseline-2026-08-16.json").write_text(
            json.dumps(baseline, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _run_ingest(
        self,
        *,
        check: bool = True,
        record_sha256: str | None = None,
        environment: dict[str, str] | None = None,
    ):
        result = subprocess.run(
            [
                "zsh",
                str(self.ingest),
                "--artifact",
                str(self.artifact),
                "--verification-record",
                str(self.record),
                "--record-sha256",
                record_sha256 or self.record_sha256,
                "--source-dir",
                str(self.source),
                "--repo-dir",
                str(self.repo),
                "--repo-name",
                "fixture",
            ],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"ingest failed with {result.returncode}\nstdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def test_ingests_exact_artifact_and_writes_public_provenance(self):
        legacy = self._create_package(
            "codex-app", "26.609.41114-1", {"usr/bin/codex-app": b"legacy\n"}
        )
        older_alias = self._create_package(
            "codex-desktop", "1.0-1", {"usr/bin/codex-desktop": b"legacy\n"}
        )
        unrelated = self._create_package(
            "unrelated", "1.0-1", {"usr/bin/unrelated": b"preserve me\n"}
        )
        staged_legacy = self.repo / legacy.name
        staged_older_alias = self.repo / older_alias.name
        staged_unrelated = self.repo / unrelated.name
        shutil.copy2(legacy, staged_legacy)
        shutil.copy2(older_alias, staged_older_alias)
        shutil.copy2(unrelated, staged_unrelated)
        subprocess.run(
            [
                "repo-add",
                str(self.repo / "fixture.db.tar.zst"),
                str(staged_legacy),
                str(staged_older_alias),
                str(staged_unrelated),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        result = self._run_ingest()

        staged = self.repo / self.artifact.name
        self.assertEqual(self._sha256(staged), self._sha256(self.artifact))
        self.assertFalse(staged_legacy.exists())
        self.assertFalse(staged_older_alias.exists())
        self.assertEqual(self._sha256(staged_unrelated), self._sha256(unrelated))
        database_entries = subprocess.run(
            ["bsdtar", "-tf", str(self.repo / "fixture.db.tar.zst")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
        self.assertNotIn("codex-app-26.609.41114-1/", database_entries)
        self.assertNotIn("codex-desktop-1.0-1/", database_entries)
        self.assertIn("unrelated-1.0-1/", database_entries)
        self.assertIn("chatgpt-26.810.52044-1/", database_entries)
        provenance = json.loads(
            (self.repo / "chatgpt.provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(provenance["package"]["sha256"], self._sha256(self.artifact))
        self.assertEqual(provenance["source"]["commit"], self.commit)
        self.assertEqual(provenance["source"]["tagObject"], self.tag_object)
        self.assertEqual(provenance["verificationRecordSha256"], self.record_sha256)
        self.assertNotIn(str(self.root), json.dumps(provenance))
        self.assertIn("Staged exact ChatGPT fallback", result.stdout)

    def test_record_digest_mismatch_leaves_repository_unchanged(self):
        sentinel = self.repo / "keep.txt"
        sentinel.write_bytes(b"last known good")

        result = self._run_ingest(check=False, record_sha256="0" * 64)

        self.assertEqual(result.returncode, 2)
        self.assertIn("does not match the tracked accepted baseline", result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"last known good")
        self.assertEqual(sorted(path.name for path in self.repo.iterdir()), ["keep.txt"])

    def test_repo_dir_must_not_be_a_regular_file(self):
        self.repo.rmdir()
        self.repo.write_bytes(b"preserve me")

        result = self._run_ingest(check=False)

        self.assertEqual(result.returncode, 2)
        self.assertIn("is not a directory", result.stderr)
        self.assertEqual(self.repo.read_bytes(), b"preserve me")

    def test_repo_remove_failure_cannot_promote_a_stale_database_entry(self):
        legacy = self._create_package(
            "codex-app", "26.609.41114-1", {"usr/bin/codex-app": b"legacy\n"}
        )
        staged_legacy = self.repo / legacy.name
        shutil.copy2(legacy, staged_legacy)
        subprocess.run(
            [
                "repo-add",
                str(self.repo / "fixture.db.tar.zst"),
                str(staged_legacy),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        fake_repo_remove = fake_bin / "repo-remove"
        fake_repo_remove.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
        fake_repo_remove.chmod(0o755)
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("BASH_FUNC_"):
                del environment[key]
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_ingest(check=False, environment=environment)

        self.assertEqual(result.returncode, 2)
        self.assertIn("still contains replaced package: codex-app", result.stderr)
        self.assertTrue(staged_legacy.is_file())
        database_entries = subprocess.run(
            ["bsdtar", "-tf", str(self.repo / "fixture.db.tar.zst")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
        self.assertIn("codex-app-26.609.41114-1/", database_entries)

    def test_interruption_after_backup_restores_original_staging(self):
        sentinel = self.repo / "keep.txt"
        sentinel.write_bytes(b"last known good")
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("BASH_FUNC_"):
                del environment[key]
        environment["ARCH_PKGS_INGEST_TEST_SIGNAL_AFTER_BACKUP"] = "1"

        result = self._run_ingest(check=False, environment=environment)

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"last known good")
        self.assertEqual(sorted(path.name for path in self.repo.iterdir()), ["keep.txt"])
        self.assertFalse(Path(f"{self.repo}.ingest.lock").exists())


class PacmanRepoPublicationTests(unittest.TestCase):
    def test_dry_run_plans_verified_candidate_and_previous_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"database")

            result = subprocess.run(
                [
                    "zsh",
                    str(PUBLISH),
                    "--dry-run",
                    "--repo-dir",
                    str(repo),
                    "--repo-name",
                    "fixture",
                    "--publish-dir",
                    "/srv/pacman/fixture/x86_64",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        self.assertIn("retain a SHA-256 manifest for staging", result.stdout)
        self.assertIn("copy staging into a candidate directory", result.stdout)
        self.assertIn("verify the candidate manifest before promotion", result.stdout)
        self.assertIn("atomically exchange the candidate", result.stdout)
        self.assertIn("compare its manifest again", result.stdout)

    def test_failed_post_promotion_verification_restores_previous_repository(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            fake_bin = root / "bin"
            repo.mkdir()
            publish.mkdir()
            fake_bin.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (repo / "new.pkg.tar.zst").write_bytes(b"new package")
            (publish / "fixture.db.tar.zst").write_bytes(b"old database")
            (publish / "old.pkg.tar.zst").write_bytes(b"old package")
            cmp_counter = root / "cmp-counter"
            fake_cmp = fake_bin / "cmp"
            fake_cmp.write_text(
                "#!/bin/sh\n"
                f"counter={cmp_counter}\n"
                "count=0\n"
                "[ ! -f \"$counter\" ] || count=$(cat \"$counter\")\n"
                "count=$((count + 1))\n"
                "printf '%s\\n' \"$count\" >\"$counter\"\n"
                "[ \"$count\" -lt 2 ] || exit 1\n"
                "exec /usr/bin/cmp \"$@\"\n",
                encoding="utf-8",
            )
            fake_cmp.chmod(0o755)
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

            result = subprocess.run(
                [
                    "zsh",
                    str(PUBLISH),
                    "--repo-dir",
                    str(repo),
                    "--repo-name",
                    "fixture",
                    "--publish-dir",
                    str(publish),
                ],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("previous repository restored", result.stderr)
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())

    def test_successful_exchange_retains_previous_and_cleans_transaction_state(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            publish.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (repo / "new.pkg.tar.zst").write_bytes(b"new package")
            (publish / "fixture.db.tar.zst").write_bytes(b"old database")
            (publish / "old.pkg.tar.zst").write_bytes(b"old package")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"

            result = subprocess.run(
                [
                    "zsh",
                    str(PUBLISH),
                    "--repo-dir",
                    str(repo),
                    "--repo-name",
                    "fixture",
                    "--publish-dir",
                    str(publish),
                ],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"new database"
            )
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            self.assertFalse((publish / "old.pkg.tar.zst").exists())
            previous = list(root.glob("published.previous.*"))
            self.assertEqual(len(previous), 1)
            self.assertEqual(
                (previous[0] / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((previous[0] / "old.pkg.tar.zst").is_file())
            self.assertFalse(list(root.glob(".published.candidate.*")))
            self.assertFalse((root / ".published.publish.lock").exists())
            retained_index = result.stdout.index("Retained previous pacman repo")
            published_index = result.stdout.index("Published verified pacman repo")
            self.assertLess(retained_index, published_index)

    def test_interruption_after_exchange_restores_previous_repository(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            publish.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (repo / "new.pkg.tar.zst").write_bytes(b"new package")
            (publish / "fixture.db.tar.zst").write_bytes(b"old database")
            (publish / "old.pkg.tar.zst").write_bytes(b"old package")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["ARCH_PKGS_PUBLISH_TEST_SIGNAL_AFTER_PROMOTION"] = "1"

            result = subprocess.run(
                [
                    "zsh",
                    str(PUBLISH),
                    "--repo-dir",
                    str(repo),
                    "--repo-name",
                    "fixture",
                    "--publish-dir",
                    str(publish),
                ],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 143)
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            self.assertFalse((root / ".published.publish.lock").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())


class ChatGPTPackageContractTests(unittest.TestCase):
    def test_required_helpers_are_present_and_executable(self):
        self.assertTrue(INGEST.is_file())
        self.assertTrue(PUBLISH.is_file())
        self.assertTrue(os.access(INGEST, os.X_OK))
        self.assertTrue(os.access(PUBLISH, os.X_OK))

    def test_tracked_baseline_records_the_exact_public_tuple(self):
        baseline_path = (
            REPO_ROOT / "packages/chatgpt/fallback-baseline-2026-08-16.json"
        )
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

        self.assertEqual(
            baseline["source"]["commit"],
            "dd3d1397f544752ea1170af8393cd59379373f52",
        )
        self.assertEqual(
            baseline["source"]["tagObject"],
            "4ca5cb05ee73dd78da7e719a0b376221d5f9fa0f",
        )
        self.assertEqual(
            baseline["package"]["sha256"],
            "678cb85152895eeed112428df110bd85b5b713fc26db03c12d9e2e120985340b",
        )
        self.assertEqual(
            baseline["payloadManifest"]["manifestSha256"],
            "a433754f9a5f79350bdef63d87a50e5f5c3ccccd7ae3ea6b1edae7dc83085a0d",
        )
        self.assertEqual(baseline["payloadManifest"]["entryCount"], 21400)
        serialized = json.dumps(baseline)
        self.assertNotIn("/home/", serialized)
        self.assertNotIn("chatgpt-transition", serialized)

    def test_user_docs_use_the_canonical_package_and_source_identity(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                REPO_ROOT / "README.md",
                REPO_ROOT / "packages/README.md",
                REPO_ROOT / "packages/chatgpt/README.md",
                REPO_ROOT / "docs/usage/local-repo.md",
            )
        )

        self.assertIn("nisavid/chatgpt-linux", text)
        self.assertIn("tools/ingest_chatgpt.zsh", text)
        self.assertNotIn("nisavid/codex-app-linux", text)
        self.assertNotIn("tools/ingest_codex_app.zsh", text)


if __name__ == "__main__":
    unittest.main()
