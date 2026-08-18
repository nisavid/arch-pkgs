import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RETIRE = REPO_ROOT / "tools" / "retire_chatgpt.zsh"
REQUIRED_TOOLS = (
    "bsdtar",
    "python3",
    "repo-add",
    "repo-remove",
    "zsh",
    "zstd",
)
MISSING_TOOLS = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


def _resolve_real_binary(name: str) -> str:
    binary = shutil.which(name)
    if binary is None:
        raise AssertionError(f"required test binary is unavailable: {name}")
    return binary


def _python_fake(source: str, *, real_tools: tuple[str, ...] = ()) -> str:
    resolved_tools = "".join(
        f"real_{name.replace('-', '_')} = {_resolve_real_binary(name)!r}\n"
        for name in real_tools
    )
    return f"#!{sys.executable}\n{resolved_tools}{textwrap.dedent(source)}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_manifest(directory: Path) -> dict:
    entries = []
    for path in sorted(directory.iterdir(), key=lambda item: os.fsencode(item.name)):
        metadata = path.lstat()
        common = {
            "gid": metadata.st_gid,
            "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
            "mtimeNs": metadata.st_mtime_ns,
            "name": path.name,
            "uid": metadata.st_uid,
        }
        if path.is_symlink():
            entries.append(
                {**common, "target": os.readlink(path), "type": "symlink"}
            )
        elif path.is_file():
            entries.append(
                {
                    **common,
                    "sha256": _sha256(path),
                    "size": metadata.st_size,
                    "type": "file",
                }
            )
        else:
            raise AssertionError(f"unexpected repository entry: {path}")
    return {"entries": entries, "schemaVersion": 3}


def _database_records(database: Path) -> dict[str, dict[str, bytes]]:
    package_records: dict[str, dict[str, bytes]] = {}
    members = subprocess.run(
        ["bsdtar", "-tf", str(database)],
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.splitlines()
    for member in members:
        normalized = member.removeprefix("./")
        if not normalized.endswith(("/desc", "/files")):
            continue
        package_record, kind = normalized.rsplit("/", 1)
        content = subprocess.run(
            ["bsdtar", "-xOf", str(database), member],
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
        package_records.setdefault(package_record, {})[kind] = content
    records: dict[str, dict[str, bytes]] = {}
    for values in package_records.values():
        lines = values["desc"].decode().splitlines()
        name = lines[lines.index("%NAME%") + 1]
        records[name] = values
    return records


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


@unittest.skipIf(MISSING_TOOLS, f"missing required tools: {MISSING_TOOLS}")
class ChatGPTRetirementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.root = Path(self.temp.name)
        self.packages = self.root / "packages"
        self.source = self.root / "source"
        self.candidate = self.root / "candidate"
        self.packages.mkdir()
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _create_package(self, name: str, version: str) -> Path:
        package = self.packages / f"{name}-{version}-x86_64.pkg.tar.zst"
        archive = package.with_suffix("")
        pkginfo = textwrap.dedent(
            f"""\
            pkgname = {name}
            pkgbase = {name}
            pkgver = {version}
            arch = x86_64
            """
        ).encode()
        with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as output:
            for member_name, content in {
                ".PKGINFO": pkginfo,
                f"usr/share/{name}/identity": f"{name}\n".encode(),
            }.items():
                member = tarfile.TarInfo(member_name)
                member.size = len(content)
                member.mode = 0o644
                member.mtime = 1_786_914_731
                output.addfile(member, fileobj=io.BytesIO(content))
        subprocess.run(
            ["zstd", "-q", "-f", str(archive), "-o", str(package)], check=True
        )
        archive.unlink()
        return package

    def _seed_complete_repository(self) -> dict[str, Path]:
        packages = {
            "chatgpt": self._create_package("chatgpt", "26.810.52044-1"),
            "codex-app": self._create_package("codex-app", "26.609.41114-1"),
            "codex-desktop": self._create_package("codex-desktop", "1.0-1"),
            "chatgpt-tools": self._create_package("chatgpt-tools", "3.1-1"),
            "example": self._create_package("example", "2.0-3"),
        }
        staged = {}
        for name, package in packages.items():
            destination = self.source / package.name
            shutil.copy2(package, destination)
            staged[name] = destination
        subprocess.run(
            ["repo-add", str(self.source / "nisavid.db.tar.zst"), *map(str, staged.values())],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        for index, path in enumerate(staged.values(), start=1):
            signature = path.with_name(f"{path.name}.sig")
            signature.write_bytes(f"signature-{index}\n".encode())
            os.chmod(signature, 0o640)
            os.utime(signature, ns=(1_786_900_000_000_000_000 + index,) * 2)
        (self.source / "chatgpt.provenance.json").write_text(
            '{"package":"chatgpt"}\n', encoding="utf-8"
        )
        unrelated_provenance = self.source / "example.provenance.json"
        unrelated_provenance.write_text(
            '{"package":"example"}\n', encoding="utf-8"
        )
        os.chmod(unrelated_provenance, 0o640)
        os.utime(unrelated_provenance, ns=(1_786_900_999_000_000_000,) * 2)
        return staged

    def _remove_index_record(self, database: Path, package_name: str) -> None:
        extracted = self.root / f"{database.name}-extracted"
        extracted.mkdir()
        subprocess.run(
            ["bsdtar", "-xf", str(database), "-C", str(extracted)], check=True
        )
        for description in extracted.glob("*/desc"):
            lines = description.read_text(encoding="utf-8").splitlines()
            if lines[lines.index("%NAME%") + 1] == package_name:
                shutil.rmtree(description.parent)
                break
        else:
            raise AssertionError(f"package record not found: {package_name}")
        replacement = database.with_name(f"{database.name}.replacement")
        subprocess.run(
            [
                "bsdtar",
                "--zstd",
                "-cf",
                str(replacement),
                "-C",
                str(extracted),
                *sorted(path.name for path in extracted.iterdir()),
            ],
            check=True,
        )
        os.replace(replacement, database)

    def _remove_index_member(
        self, database: Path, package_name: str, member_name: str
    ) -> None:
        extracted = self.root / f"{database.name}-{member_name}-extracted"
        extracted.mkdir()
        subprocess.run(
            ["bsdtar", "-xf", str(database), "-C", str(extracted)], check=True
        )
        for description in extracted.glob("*/desc"):
            lines = description.read_text(encoding="utf-8").splitlines()
            if lines[lines.index("%NAME%") + 1] == package_name:
                (description.parent / member_name).unlink()
                break
        else:
            raise AssertionError(f"package record not found: {package_name}")
        replacement = database.with_name(f"{database.name}.replacement")
        subprocess.run(
            [
                "bsdtar",
                "--zstd",
                "-cf",
                str(replacement),
                "-C",
                str(extracted),
                *sorted(path.name for path in extracted.iterdir()),
            ],
            check=True,
        )
        os.replace(replacement, database)

    def _add_index_member(
        self, database: Path, package_name: str, member_name: str, content: bytes
    ) -> None:
        extracted = self.root / f"{database.name}-{member_name}-added"
        extracted.mkdir()
        subprocess.run(
            ["bsdtar", "-xf", str(database), "-C", str(extracted)], check=True
        )
        for description in extracted.glob("*/desc"):
            lines = description.read_text(encoding="utf-8").splitlines()
            if lines[lines.index("%NAME%") + 1] == package_name:
                (description.parent / member_name).write_bytes(content)
                break
        else:
            raise AssertionError(f"package record not found: {package_name}")
        replacement = database.with_name(f"{database.name}.replacement")
        subprocess.run(
            [
                "bsdtar",
                "--zstd",
                "-cf",
                str(replacement),
                "-C",
                str(extracted),
                *sorted(path.name for path in extracted.iterdir()),
            ],
            check=True,
        )
        os.replace(replacement, database)

    def _run_retirement(
        self, *, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        source_manifest_bytes = (
            json.dumps(_repository_manifest(self.source), indent=2, sort_keys=True)
            + "\n"
        ).encode()
        manifest_path = self.root / "accepted-source-manifest.json"
        manifest_path.write_bytes(source_manifest_bytes)
        return subprocess.run(
            [
                str(RETIRE),
                "--source-repo-dir",
                str(self.source),
                "--input-manifest",
                str(manifest_path),
                "--input-manifest-sha256",
                _sha256(manifest_path),
                "--repo-dir",
                str(self.candidate),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )

    def _run_promotion_transition(
        self,
        *,
        no_effect: bool = False,
        fail_after_move: bool = False,
        replace_identity: bool = False,
        corrupt_after_move: bool = False,
        signal_after_move: bool = False,
        race_destination: bool = False,
        replace_failed_identity: bool = False,
        fail_failed_move_after_effect: bool = False,
        symlink_promoted_destination: bool = False,
        symlink_retained_stage: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "mv",
            _python_fake(
                f"""\
                import os
                import pathlib
                import shutil
                import signal
                import subprocess
                import sys

                no_effect = {no_effect!r}
                fail_after_move = {fail_after_move!r}
                replace_identity = {replace_identity!r}
                corrupt_after_move = {corrupt_after_move!r}
                signal_after_move = {signal_after_move!r}
                race_destination = {race_destination!r}
                replace_failed_identity = {replace_failed_identity!r}
                fail_failed_move_after_effect = {fail_failed_move_after_effect!r}
                symlink_promoted_destination = {symlink_promoted_destination!r}
                symlink_retained_stage = {symlink_retained_stage!r}
                source = pathlib.Path(sys.argv[-2])
                destination = pathlib.Path(sys.argv[-1])
                is_promotion = (
                    source.name.startswith(".candidate.retire-stage.")
                    and destination.name == "candidate"
                )
                is_failed_move = (
                    source.name == "candidate"
                    and destination.name.startswith(".candidate.retire-failed.")
                )
                if is_promotion and no_effect:
                    raise SystemExit(0)
                if is_promotion and race_destination:
                    destination.mkdir()
                    (destination / "other-writer").write_bytes(b"unrelated\\n")
                    raise SystemExit(1)
                if is_promotion and symlink_retained_stage:
                    owned = source.with_name(f"{{source.name}}.owned")
                    source.rename(owned)
                    source.symlink_to(owned, target_is_directory=True)
                    raise SystemExit(0)
                result = subprocess.run([real_mv, *sys.argv[1:]])
                if (
                    is_promotion
                    and result.returncode == 0
                    and symlink_promoted_destination
                ):
                    owned = destination.with_name(f"{{destination.name}}.owned")
                    destination.rename(owned)
                    destination.symlink_to(owned, target_is_directory=True)
                if is_promotion and result.returncode == 0 and replace_identity:
                    moved = destination.with_name(f"{{destination.name}}.moved")
                    destination.rename(moved)
                    shutil.copytree(moved, destination, symlinks=True)
                    shutil.rmtree(moved)
                if is_promotion and result.returncode == 0 and corrupt_after_move:
                    (destination / "unexpected-after-promotion").write_bytes(b"changed\\n")
                if is_promotion and result.returncode == 0 and signal_after_move:
                    os.kill(os.getppid(), signal.SIGTERM)
                if is_promotion and result.returncode == 0 and fail_after_move:
                    raise SystemExit(77)
                if is_failed_move and result.returncode == 0 and replace_failed_identity:
                    owned = destination.with_name(f"{{destination.name}}.owned")
                    destination.rename(owned)
                    shutil.copytree(owned, destination, symlinks=True)
                if (
                    is_failed_move
                    and result.returncode == 0
                    and fail_failed_move_after_effect
                ):
                    raise SystemExit(77)
                raise SystemExit(result.returncode)
                """,
                real_tools=("mv",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        return self._run_retirement(environment=environment)

    def test_builds_exact_retirement_candidate_without_mutating_source(self):
        staged = self._seed_complete_repository()
        source_manifest = _repository_manifest(self.source)
        source_manifest_bytes = (
            json.dumps(source_manifest, indent=2, sort_keys=True) + "\n"
        ).encode()
        manifest_path = self.root / "accepted-source-manifest.json"
        manifest_path.write_bytes(source_manifest_bytes)
        manifest_sha256 = _sha256(manifest_path)
        source_db_records = _database_records(self.source / "nisavid.db.tar.zst")
        source_files_records = _database_records(
            self.source / "nisavid.files.tar.zst"
        )

        result = self._run_retirement()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_repository_manifest(self.source), source_manifest)
        self.assertTrue(self.candidate.is_dir())

        for name in ("chatgpt", "codex-app", "codex-desktop"):
            self.assertFalse((self.candidate / staged[name].name).exists())
            self.assertFalse(
                (self.candidate / f"{staged[name].name}.sig").exists()
            )
        self.assertFalse((self.candidate / "chatgpt.provenance.json").exists())

        for suffix in ("", ".sig"):
            source_path = self.source / f"{staged['example'].name}{suffix}"
            candidate_path = self.candidate / source_path.name
            self.assertEqual(candidate_path.read_bytes(), source_path.read_bytes())
            self.assertEqual(
                stat.S_IMODE(candidate_path.stat().st_mode),
                stat.S_IMODE(source_path.stat().st_mode),
            )
            self.assertEqual(candidate_path.stat().st_uid, source_path.stat().st_uid)
            self.assertEqual(candidate_path.stat().st_gid, source_path.stat().st_gid)
            self.assertEqual(
                candidate_path.stat().st_mtime_ns, source_path.stat().st_mtime_ns
            )
        self.assertEqual(
            (self.candidate / "example.provenance.json").read_bytes(),
            (self.source / "example.provenance.json").read_bytes(),
        )
        self.assertTrue((self.candidate / staged["chatgpt-tools"].name).is_file())
        self.assertTrue(
            (self.candidate / f"{staged['chatgpt-tools'].name}.sig").is_file()
        )

        candidate_db_records = _database_records(
            self.candidate / "nisavid.db.tar.zst"
        )
        candidate_files_records = _database_records(
            self.candidate / "nisavid.files.tar.zst"
        )
        self.assertEqual(set(candidate_db_records), {"chatgpt-tools", "example"})
        self.assertEqual(set(candidate_files_records), {"chatgpt-tools", "example"})
        self.assertEqual(candidate_db_records["example"], source_db_records["example"])
        self.assertEqual(
            candidate_files_records["example"], source_files_records["example"]
        )

    def test_all_target_source_produces_valid_empty_indexes(self):
        package = self._create_package("chatgpt", "26.810.52044-1")
        staged = self.source / package.name
        shutil.copy2(package, staged)
        subprocess.run(
            ["repo-add", str(self.source / "nisavid.db.tar.zst"), str(staged)],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        (self.source / "chatgpt.provenance.json").write_text(
            '{"package":"chatgpt"}\n', encoding="utf-8"
        )

        result = self._run_retirement()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            _database_records(self.candidate / "nisavid.db.tar.zst"), {}
        )
        self.assertEqual(
            _database_records(self.candidate / "nisavid.files.tar.zst"), {}
        )
        self.assertFalse(list(self.candidate.glob("*.pkg.tar.*")))
        self.assertFalse((self.candidate / "chatgpt.provenance.json").exists())

    def test_removes_authorized_stale_index_backups_from_live_shape(self):
        self._seed_complete_repository()
        stale_database = self.source / "nisavid.db.tar.zst.old"
        stale_files = self.source / "nisavid.files.tar.zst.old"
        shutil.copy2(self.source / "nisavid.db.tar.zst", stale_database)
        shutil.copy2(self.source / "nisavid.files.tar.zst", stale_files)
        stale_database_bytes = stale_database.read_bytes()
        stale_files_bytes = stale_files.read_bytes()

        result = self._run_retirement()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stale_database.read_bytes(), stale_database_bytes)
        self.assertEqual(stale_files.read_bytes(), stale_files_bytes)
        self.assertFalse((self.candidate / stale_database.name).exists())
        self.assertFalse((self.candidate / stale_files.name).exists())

    def test_rejects_symlinked_stale_index_backup(self):
        self._seed_complete_repository()
        (self.source / "nisavid.db.tar.zst.old").symlink_to(
            "nisavid.db.tar.zst"
        )

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("stale repository index backup is unsafe", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_accepted_manifest_when_indexed_archive_is_missing(self):
        staged = self._seed_complete_repository()
        staged["example"].unlink()

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("indexed package archive is missing", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_partial_repository_when_database_and_files_disagree(self):
        self._seed_complete_repository()
        self._remove_index_record(self.source / "nisavid.files.tar.zst", "example")

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("repository database and files indexes disagree", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_files_index_missing_package_file_list(self):
        self._seed_complete_repository()
        self._remove_index_member(
            self.source / "nisavid.files.tar.zst", "example", "files"
        )

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("files index member set does not match package records", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_noncanonical_repository_index_members(self):
        self._seed_complete_repository()
        for name in ("nisavid.db.tar.zst", "nisavid.files.tar.zst"):
            self._add_index_member(
                self.source / name, "example", "unexpected", b"opaque\n"
            )

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("repository index contains an unsupported member", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_unindexed_package_archive(self):
        self._seed_complete_repository()
        orphan = self._create_package("orphan", "1.0-1")
        shutil.copy2(orphan, self.source / orphan.name)

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("repository contains an unindexed package archive", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_repo_remove_that_changes_an_unrelated_index_record(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "repo-remove",
            _python_fake(
                """\
                import os
                import pathlib
                import shutil
                import subprocess
                import sys
                import tempfile

                result = subprocess.run([real_repo_remove, *sys.argv[1:]])
                if result.returncode != 0 or sys.argv[-1] != "chatgpt":
                    raise SystemExit(result.returncode)
                database = pathlib.Path(sys.argv[-2])
                with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
                    extracted = pathlib.Path(temporary) / "index"
                    extracted.mkdir()
                    subprocess.run(
                        [real_bsdtar, "-xf", str(database), "-C", str(extracted)],
                        check=True,
                    )
                    description = next(extracted.glob("example-*/desc"))
                    description.write_bytes(
                        description.read_bytes() + b"%CORRUPTED%\\nchanged\\n"
                    )
                    replacement = database.with_name(f"{database.name}.replacement")
                    subprocess.run(
                        [
                            real_bsdtar,
                            "--zstd",
                            "-cf",
                            str(replacement),
                            "-C",
                            str(extracted),
                            *sorted(path.name for path in extracted.iterdir()),
                        ],
                        check=True,
                    )
                    os.replace(replacement, database)
                """,
                real_tools=("repo-remove", "bsdtar"),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unrelated repository index record changed", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_repo_remove_that_changes_unrelated_index_metadata(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "repo-remove",
            _python_fake(
                """\
                import os
                import pathlib
                import subprocess
                import sys
                import tempfile

                result = subprocess.run([real_repo_remove, *sys.argv[1:]])
                if result.returncode != 0 or sys.argv[-1] != "chatgpt":
                    raise SystemExit(result.returncode)
                database = pathlib.Path(sys.argv[-2])
                with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
                    extracted = pathlib.Path(temporary) / "index"
                    extracted.mkdir()
                    subprocess.run(
                        [real_bsdtar, "-xf", str(database), "-C", str(extracted)],
                        check=True,
                    )
                    description = next(extracted.glob("example-*/desc"))
                    metadata = description.stat()
                    os.utime(
                        description,
                        ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
                    )
                    replacement = database.with_name(f"{database.name}.replacement")
                    subprocess.run(
                        [
                            real_bsdtar,
                            "--zstd",
                            "-cf",
                            str(replacement),
                            "-C",
                            str(extracted),
                            *sorted(path.name for path in extracted.iterdir()),
                        ],
                        check=True,
                    )
                    os.replace(replacement, database)
                """,
                real_tools=("repo-remove", "bsdtar"),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unrelated repository index record changed", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_repo_remove_that_changes_unrelated_index_directory_metadata(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "repo-remove",
            _python_fake(
                """\
                import os
                import pathlib
                import subprocess
                import sys
                import tempfile

                result = subprocess.run([real_repo_remove, *sys.argv[1:]])
                if result.returncode != 0 or sys.argv[-1] != "chatgpt":
                    raise SystemExit(result.returncode)
                database = pathlib.Path(sys.argv[-2])
                with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
                    extracted = pathlib.Path(temporary) / "index"
                    extracted.mkdir()
                    subprocess.run(
                        [real_bsdtar, "-xf", str(database), "-C", str(extracted)],
                        check=True,
                    )
                    package_directory = next(extracted.glob("example-*"))
                    metadata = package_directory.stat()
                    os.utime(
                        package_directory,
                        ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
                    )
                    replacement = database.with_name(f"{database.name}.replacement")
                    subprocess.run(
                        [
                            real_bsdtar,
                            "--zstd",
                            "-cf",
                            str(replacement),
                            "-C",
                            str(extracted),
                            *sorted(path.name for path in extracted.iterdir()),
                        ],
                        check=True,
                    )
                    os.replace(replacement, database)
                """,
                real_tools=("repo-remove", "bsdtar"),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unrelated repository index record changed", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_repo_remove_nonzero_status_cannot_promote_even_after_effect(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "repo-remove",
            _python_fake(
                """\
                import subprocess
                import sys

                result = subprocess.run([real_repo_remove, *sys.argv[1:]])
                if result.returncode == 0 and sys.argv[-1] == "chatgpt":
                    raise SystemExit(77)
                raise SystemExit(result.returncode)
                """,
                real_tools=("repo-remove",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("repo-remove failed for retired package: chatgpt", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_repo_remove_that_retargets_canonical_database_alias(self):
        staged = self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "repo-remove",
            _python_fake(
                f"""\
                import pathlib
                import subprocess
                import sys

                result = subprocess.run([real_repo_remove, *sys.argv[1:]])
                if result.returncode == 0:
                    database = pathlib.Path(sys.argv[-2])
                    alias = database.with_name("nisavid.db")
                    alias.unlink(missing_ok=True)
                    alias.symlink_to({staged['example'].name!r})
                raise SystemExit(result.returncode)
                """,
                real_tools=("repo-remove",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("canonical database alias target does not match", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_late_canonical_database_alias_retarget(self):
        staged = self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "cmp",
            _python_fake(
                f"""\
                import pathlib
                import subprocess
                import sys

                result = subprocess.run([real_cmp, *sys.argv[1:]])
                if result.returncode == 0 and any(
                    value.endswith("candidate.db-records.sorted") for value in sys.argv
                ):
                    stage = next(pathlib.Path({str(self.root)!r}).glob(".candidate.retire-stage.*"))
                    alias = stage / "nisavid.db"
                    alias.unlink()
                    alias.symlink_to({staged['example'].name!r})
                raise SystemExit(result.returncode)
                """,
                real_tools=("cmp",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("canonical database alias target does not match", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_rejects_source_change_during_candidate_copy(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "cp",
            _python_fake(
                """\
                import pathlib
                import subprocess
                import sys

                result = subprocess.run([real_cp, *sys.argv[1:]])
                if result.returncode == 0 and "-a" in sys.argv:
                    source = pathlib.Path(sys.argv[-2]).resolve()
                    (source / "race-marker").write_bytes(b"changed during copy\\n")
                raise SystemExit(result.returncode)
                """,
                real_tools=("cp",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("source repository changed while constructing", result.stderr)
        self.assertFalse(self.candidate.exists())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())

    def test_completed_promotion_reconciles_nonzero_move_status(self):
        result = self._run_promotion_transition(fail_after_move=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.candidate.is_dir())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())

    def test_no_effect_promotion_is_not_reported_as_success(self):
        result = self._run_promotion_transition(no_effect=True)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("could not promote the verified retirement candidate", result.stderr)
        self.assertFalse(self.candidate.exists())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())

    def test_ambiguous_promotion_preserves_identity_and_recovery_state(self):
        result = self._run_promotion_transition(
            fail_after_move=True, replace_identity=True
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(
            "could not identify the retirement candidate after promotion",
            result.stderr,
        )
        self.assertIn("recovery manifests preserved at:", result.stderr)
        self.assertTrue(self.candidate.is_dir())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())

    def test_symlinked_promoted_destination_is_indeterminate(self):
        result = self._run_promotion_transition(
            symlink_promoted_destination=True
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(
            "could not identify the retirement candidate after promotion",
            result.stderr,
        )
        self.assertTrue(self.candidate.is_symlink(), result.stderr)
        self.assertTrue(
            (self.root / "candidate.owned/nisavid.db.tar.zst").is_file(),
            result.stderr,
        )
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())

    def test_symlinked_retained_stage_is_indeterminate(self):
        result = self._run_promotion_transition(symlink_retained_stage=True)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(
            "could not identify the retirement candidate after promotion",
            result.stderr,
        )
        staged_links = [
            path
            for path in self.root.glob(".candidate.retire-stage.*")
            if path.is_symlink()
        ]
        self.assertEqual(len(staged_links), 1, result.stderr)
        self.assertTrue(
            staged_links[0].with_name(f"{staged_links[0].name}.owned").is_dir()
        )
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())

    def test_post_promotion_corruption_is_retained_as_failed_not_accepted(self):
        result = self._run_promotion_transition(corrupt_after_move=True)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("failed post-promotion verification", result.stderr)
        self.assertFalse(self.candidate.exists())
        failed = list(self.root.glob(".candidate.retire-failed.*"))
        self.assertEqual(len(failed), 1, result.stderr)
        self.assertTrue((failed[0] / "unexpected-after-promotion").is_file())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())

    def test_failed_candidate_claim_reports_the_original_move_failure(self):
        result = self._run_promotion_transition(
            corrupt_after_move=True,
            replace_failed_identity=True,
            fail_failed_move_after_effect=True,
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("(identity-mismatch, status 77)", result.stderr)
        self.assertNotIn("(identity-mismatch, status 0)", result.stderr)
        self.assertTrue(self.candidate.is_dir(), result.stderr)
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())

    def test_signal_during_promotion_retains_candidate_as_failed(self):
        result = self._run_promotion_transition(signal_after_move=True)

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(self.candidate.exists())
        failed = list(self.root.glob(".candidate.retire-failed.*"))
        self.assertEqual(len(failed), 1, result.stderr)
        self.assertTrue((failed[0] / "example-2.0-3-x86_64.pkg.tar.zst").is_file())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())

    def test_destination_race_preserves_both_identities_and_lock(self):
        result = self._run_promotion_transition(race_destination=True)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("could not identify the retirement candidate", result.stderr)
        self.assertEqual(
            (self.candidate / "other-writer").read_bytes(), b"unrelated\n"
        )
        staged = list(self.root.glob(".candidate.retire-stage.*"))
        self.assertEqual(len(staged), 1, result.stderr)
        self.assertTrue((staged[0] / "example-2.0-3-x86_64.pkg.tar.zst").is_file())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())

    def test_signal_before_promotion_cleans_owned_transaction_state(self):
        source_manifest = None
        self._seed_complete_repository()
        source_manifest = _repository_manifest(self.source)
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "repo-remove",
            _python_fake(
                """\
                import os
                import signal
                import subprocess
                import sys

                result = subprocess.run([real_repo_remove, *sys.argv[1:]])
                os.kill(os.getppid(), signal.SIGTERM)
                raise SystemExit(result.returncode)
                """,
                real_tools=("repo-remove",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertEqual(_repository_manifest(self.source), source_manifest)
        self.assertFalse(self.candidate.exists())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())
        self.assertFalse(list(self.root.glob(".candidate.retire-stage.*")))

    def test_cleanup_preserves_replacement_at_owned_temporary_path(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "cp",
            _python_fake(
                """\
                import pathlib
                import subprocess
                import sys

                result = subprocess.run([real_cp, *sys.argv[1:]])
                if result.returncode == 0 and "-a" in sys.argv:
                    stage = pathlib.Path(sys.argv[-1]).resolve()
                    owned = stage.with_name(f"{stage.name}.owned")
                    stage.rename(owned)
                    stage.mkdir()
                    (stage / "unrelated-marker").write_bytes(b"preserve\\n")
                    raise SystemExit(77)
                raise SystemExit(result.returncode)
                """,
                real_tools=("cp",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        replacements = [
            path
            for path in self.root.glob(".candidate.retire-stage.*")
            if (path / "unrelated-marker").is_file()
        ]
        self.assertEqual(len(replacements), 1, result.stderr)
        self.assertEqual(
            (replacements[0] / "unrelated-marker").read_bytes(), b"preserve\n"
        )
        owned = list(self.root.glob(".candidate.retire-stage.*.owned"))
        self.assertEqual(len(owned), 1, result.stderr)
        self.assertTrue((owned[0] / "nisavid.db.tar.zst").is_file())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())
        self.assertIn("temporary path identity changed", result.stderr)

    def test_cleanup_treats_missing_tracked_stage_as_indeterminate(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "cp",
            _python_fake(
                """\
                import pathlib
                import subprocess
                import sys

                result = subprocess.run([real_cp, *sys.argv[1:]])
                if result.returncode == 0 and "-a" in sys.argv:
                    stage = pathlib.Path(sys.argv[-1]).resolve()
                    stage.rename(stage.with_name(f"{stage.name}.owned"))
                    raise SystemExit(77)
                raise SystemExit(result.returncode)
                """,
                real_tools=("cp",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        owned = list(self.root.glob(".candidate.retire-stage.*.owned"))
        self.assertEqual(len(owned), 1, result.stderr)
        self.assertTrue((owned[0] / "nisavid.db.tar.zst").is_file())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())
        self.assertIn("tracked temporary path is missing", result.stderr)
        self.assertIn("retirement state is indeterminate", result.stderr)

    def test_cleanup_cannot_delete_replacement_after_identity_check(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        counter = self.root / "stage-stat-count"
        _write_executable(
            fake_bin / "repo-remove",
            "#!/bin/sh\nexit 77\n",
        )
        _write_executable(
            fake_bin / "stat",
            _python_fake(
                f"""\
                import pathlib
                import subprocess
                import sys

                result = subprocess.run([real_stat, *sys.argv[1:]], capture_output=True)
                target = pathlib.Path(sys.argv[-1])
                counter = pathlib.Path({str(counter)!r})
                if result.returncode == 0 and "-Lc" in sys.argv and target.name.startswith(
                    ".candidate.retire-stage."
                ):
                    count = int(counter.read_text() or "0") if counter.exists() else 0
                    count += 1
                    counter.write_text(str(count))
                    if count == 2:
                        owned = target.with_name(f"{{target.name}}.owned")
                        target.rename(owned)
                        target.mkdir()
                        (target / "unrelated-marker").write_bytes(b"preserve\\n")
                sys.stdout.buffer.write(result.stdout)
                sys.stderr.buffer.write(result.stderr)
                raise SystemExit(result.returncode)
                """,
                real_tools=("stat",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        preserved = [
            path
            for path in self.root.iterdir()
            if path.is_dir() and (path / "unrelated-marker").is_file()
        ]
        self.assertEqual(len(preserved), 1, result.stderr)
        self.assertEqual(
            (preserved[0] / "unrelated-marker").read_bytes(), b"preserve\n"
        )
        owned = list(self.root.glob(".candidate.retire-stage.*.owned"))
        self.assertEqual(len(owned), 1, result.stderr)
        self.assertTrue((owned[0] / "nisavid.db.tar.zst").is_file())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())
        self.assertIn("temporary path identity changed", result.stderr)

    def test_cleanup_claim_preserves_post_move_substitution(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        injected = self.root / "cleanup-move-injected"
        _write_executable(fake_bin / "repo-remove", "#!/bin/sh\nexit 77\n")
        _write_executable(
            fake_bin / "mv",
            _python_fake(
                f"""\
                import pathlib
                import subprocess
                import sys

                source = pathlib.Path(sys.argv[-2])
                destination = pathlib.Path(sys.argv[-1])
                result = subprocess.run([real_mv, *sys.argv[1:]])
                injected = pathlib.Path({str(injected)!r})
                if (
                    result.returncode == 0
                    and ".retire-stage." in source.name
                    and ".cleanup." in destination.name
                    and not injected.exists()
                ):
                    destination.rename(destination.with_name(f"{{destination.name}}.owned"))
                    destination.mkdir()
                    (destination / "unrelated-marker").write_bytes(b"preserve\\n")
                    injected.write_text("yes")
                raise SystemExit(result.returncode)
                """,
                real_tools=("mv",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        replacements = [
            path
            for path in self.root.iterdir()
            if path.is_dir() and (path / "unrelated-marker").is_file()
        ]
        self.assertEqual(len(replacements), 1, result.stderr)
        self.assertEqual(
            (replacements[0] / "unrelated-marker").read_bytes(), b"preserve\n"
        )
        owned = list(self.root.glob(".candidate.retire-stage.*.cleanup.*.owned"))
        self.assertEqual(len(owned), 1, result.stderr)
        self.assertTrue((owned[0] / "nisavid.db.tar.zst").is_file())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())
        self.assertIn("temporary path identity changed", result.stderr)

    def test_cleanup_helper_preserves_post_verification_replacement(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        injected = self.root / "cleanup-helper-injected"
        _write_executable(fake_bin / "repo-remove", "#!/bin/sh\nexit 77\n")
        _write_executable(
            fake_bin / "python3",
            _python_fake(
                f"""\
                import os
                import pathlib
                import sys

                real_python = {sys.executable!r}

                injected = pathlib.Path({str(injected)!r})
                if (
                    len(sys.argv) >= 5
                    and pathlib.Path(sys.argv[1]).name
                    == "repository_owned_directory.py"
                    and sys.argv[2] == "delete-tree"
                    and ".retire-stage." in pathlib.Path(sys.argv[3]).name
                    and ".cleanup." in pathlib.Path(sys.argv[3]).name
                    and not injected.exists()
                ):
                    target = pathlib.Path(sys.argv[3])
                    target.rename(target.with_name(f"{{target.name}}.owned"))
                    target.mkdir()
                    (target / "unrelated-marker").write_bytes(b"preserve\\n")
                    injected.write_text("yes")
                os.execv(real_python, [real_python, *sys.argv[1:]])
                """
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertTrue(injected.is_file(), result.stderr)
        replacements = [
            path
            for path in self.root.iterdir()
            if path.is_dir() and (path / "unrelated-marker").is_file()
        ]
        self.assertEqual(len(replacements), 1, result.stderr)
        self.assertEqual(
            (replacements[0] / "unrelated-marker").read_bytes(), b"preserve\n"
        )
        owned = list(self.root.glob(".candidate.retire-stage.*.cleanup.*.owned"))
        self.assertEqual(len(owned), 1, result.stderr)
        self.assertTrue((owned[0] / "nisavid.db.tar.zst").is_file())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())
        self.assertIn("could not remove claimed temporary path", result.stderr)

    def test_rejects_candidate_nested_inside_source_before_writing(self):
        self._seed_complete_repository()
        source_metadata = self.source.stat()
        self.candidate = self.source / "candidate"

        result = self._run_retirement()

        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn("must not overlap", result.stderr)
        after = self.source.stat()
        self.assertEqual(after.st_mtime_ns, source_metadata.st_mtime_ns)
        self.assertEqual(after.st_ctime_ns, source_metadata.st_ctime_ns)
        self.assertFalse(self.candidate.exists())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())
        self.assertFalse(list(self.source.glob(".candidate.retire-*")))

    def test_post_promotion_rollback_preserves_replacement_candidate(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "python3",
            _python_fake(
                f"""\
                import os
                import pathlib
                import subprocess
                import sys

                real_python = {sys.executable!r}
                result = subprocess.run([real_python, *sys.argv[1:]])
                if (
                    result.returncode == 0
                    and len(sys.argv) >= 3
                    and pathlib.Path(sys.argv[1]).name == "repository_manifest.py"
                    and pathlib.Path(sys.argv[2]).name == "candidate"
                ):
                    candidate = pathlib.Path(sys.argv[2])
                    owned = candidate.with_name("candidate.owned")
                    candidate.rename(owned)
                    candidate.mkdir()
                    (candidate / "unrelated-marker").write_bytes(b"preserve\\n")
                    raise SystemExit(77)
                raise SystemExit(result.returncode)
                """
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(self.candidate.is_dir(), result.stderr)
        self.assertEqual(
            (self.candidate / "unrelated-marker").read_bytes(), b"preserve\n"
        )
        self.assertTrue((self.root / "candidate.owned/nisavid.db.tar.zst").is_file())
        self.assertTrue(Path(f"{self.candidate}.writer.lock").is_dir())
        self.assertIn("could not be identified", result.stderr)

    def test_preheld_writer_lock_is_preserved(self):
        self._seed_complete_repository()
        writer_lock = Path(f"{self.candidate}.writer.lock")
        writer_lock.mkdir()
        owner_marker = writer_lock / "owner"
        owner_marker.write_text("someone else\n", encoding="utf-8")

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("another repository writer appears to be active", result.stderr)
        self.assertEqual(owner_marker.read_text(encoding="utf-8"), "someone else\n")
        self.assertFalse(self.candidate.exists())

    def test_signal_during_owned_writer_lock_acquisition_cleans_lock(self):
        self._seed_complete_repository()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        _write_executable(
            fake_bin / "mkdir",
            _python_fake(
                """\
                import os
                import pathlib
                import signal
                import subprocess
                import sys

                result = subprocess.run([real_mkdir, *sys.argv[1:]])
                destination = pathlib.Path(sys.argv[-1])
                if result.returncode == 0 and destination.name.endswith(".writer.lock"):
                    os.kill(os.getppid(), signal.SIGTERM)
                raise SystemExit(result.returncode)
                """,
                real_tools=("mkdir",),
            ),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

        result = self._run_retirement(environment=environment)

        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())
        self.assertFalse(self.candidate.exists())

    def test_retirement_rejects_a_symlinked_adjacent_manifest_tool(self):
        self._seed_complete_repository()
        isolated_tools = self.root / "isolated-tools"
        isolated_tools.mkdir()
        isolated_retire = isolated_tools / RETIRE.name
        shutil.copy2(RETIRE, isolated_retire)
        shutil.copy2(
            REPO_ROOT / "tools" / "repository_owned_directory.py",
            isolated_tools / "repository_owned_directory.py",
        )
        manifest_link = isolated_tools / "repository_manifest.py"
        manifest_link.symlink_to(REPO_ROOT / "tools" / "repository_manifest.py")
        source_manifest_bytes = (
            json.dumps(_repository_manifest(self.source), indent=2, sort_keys=True)
            + "\n"
        ).encode()
        manifest_path = self.root / "accepted-source-manifest.json"
        manifest_path.write_bytes(source_manifest_bytes)

        result = subprocess.run(
            [
                str(isolated_retire),
                "--source-repo-dir",
                str(self.source),
                "--input-manifest",
                str(manifest_path),
                "--input-manifest-sha256",
                _sha256(manifest_path),
                "--repo-dir",
                str(self.candidate),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            result.stderr,
            f"repository manifest tool is not executable: {manifest_link}\n",
        )
        self.assertFalse(self.candidate.exists())
        self.assertFalse(Path(f"{self.candidate}.writer.lock").exists())

    def test_signed_repository_indexes_are_rejected_without_mutation(self):
        self._seed_complete_repository()
        (self.source / "nisavid.db.tar.zst.sig").write_bytes(b"index signature\n")

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("signed repository indexes cannot be rewritten", result.stderr)
        self.assertFalse(self.candidate.exists())

    def test_existing_candidate_path_is_rejected(self):
        self._seed_complete_repository()
        self.candidate.mkdir()
        marker = self.candidate / "preserve"
        marker.write_text("existing\n", encoding="utf-8")

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("candidate repository path must not already exist", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "existing\n")

    def test_candidate_parent_with_symlink_component_is_rejected(self):
        self._seed_complete_repository()
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        self.candidate = linked_parent / "candidate"

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("candidate repository parent must not contain symlinks", result.stderr)
        self.assertFalse((real_parent / "candidate").exists())

    def test_source_repository_symlink_is_rejected(self):
        self._seed_complete_repository()
        source_link = self.root / "source-link"
        source_link.symlink_to(self.source, target_is_directory=True)
        self.source = source_link

        result = self._run_retirement()

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("source repository must be a real directory", result.stderr)
        self.assertFalse(self.candidate.exists())


if __name__ == "__main__":
    unittest.main()
