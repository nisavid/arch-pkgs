import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISH = REPO_ROOT / "tools" / "publish_pacman_repo.zsh"
REQUIRED_TOOLS = (
    "cmp",
    "date",
    "install",
    "mkdir",
    "mv",
    "readlink",
    "rsync",
    "sha256sum",
    "stat",
    "zsh",
)
MISSING_TOOLS = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


def _resolve_real_binary(name: str) -> str:
    binary = shutil.which(name)
    if binary is None:
        raise AssertionError(f"required test binary is unavailable: {name}")
    return binary


def _write_fake_cmp(
    fake_bin: Path, counter: Path, *, fail_from_call: int
) -> Path:
    real_cmp = _resolve_real_binary("cmp")
    fake_cmp = fake_bin / "cmp"
    fake_cmp.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "import pathlib\n"
        "import sys\n"
        f"counter = pathlib.Path({str(counter)!r})\n"
        f"fail_from_call = {fail_from_call!r}\n"
        "count = int(counter.read_text(encoding='utf-8')) if counter.is_file() else 0\n"
        "count += 1\n"
        "counter.write_text(f'{count}\\n', encoding='utf-8')\n"
        "if count >= fail_from_call:\n"
        "    raise SystemExit(1)\n"
        f"os.execv({real_cmp!r}, [{real_cmp!r}, *sys.argv[1:]])\n",
        encoding="utf-8",
    )
    fake_cmp.chmod(0o755)
    return fake_cmp


def _write_fake_mv(
    fake_bin: Path, body: str, *, extra_imports: tuple[str, ...] = ()
) -> Path:
    real_mv = _resolve_real_binary("mv")
    imports = ("pathlib", "subprocess", "sys", *extra_imports)
    fake_mv = fake_bin / "mv"
    fake_mv.write_text(
        f"#!{sys.executable}\n"
        + "".join(f"import {name}\n" for name in imports)
        + f"real_mv = {real_mv!r}\n"
        + body,
        encoding="utf-8",
    )
    fake_mv.chmod(0o755)
    return fake_mv


def _write_fake_date_collision(
    fake_bin: Path, collision: Path, *, dangling_symlink: bool = False
) -> Path:
    fake_date = fake_bin / "date"
    fake_date.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "from pathlib import Path\n"
        f"collision = Path({str(collision)!r}.format(pid=os.getppid()))\n"
        f"dangling_symlink = {dangling_symlink!r}\n"
        "if not os.path.lexists(collision):\n"
        "    if dangling_symlink:\n"
        "        collision.symlink_to('missing-collision-target', target_is_directory=True)\n"
        "    else:\n"
        "        collision.mkdir()\n"
        "metadata = collision.lstat()\n"
        "(collision.parent / 'collision-identity').write_text(\n"
        "    f'{metadata.st_dev}:{metadata.st_ino}\\n', encoding='utf-8'\n"
        ")\n"
        "print('fixed')\n",
        encoding="utf-8",
    )
    fake_date.chmod(0o755)
    return fake_date


@unittest.skipIf(MISSING_TOOLS, f"missing required tools: {MISSING_TOOLS}")
class PacmanRepoPublicationTests(unittest.TestCase):
    def _run_first_publication_move_transition(
        self,
        root: Path,
        *,
        replace_published_identity: bool = False,
        fail_promotion_after_move: bool = True,
        promotion_no_effect_success: bool = False,
        signal_after_promotion: bool = False,
        fail_rollback_after_move: bool = False,
        replace_rollback_identity: bool = False,
        precreate_failed_destination: bool = False,
        race_publish_destination: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        repo = root / "repo"
        publish = root / "published"
        fake_bin = root / "bin"
        manifest_tmp = root / "manifest-tmp"
        repo.mkdir()
        fake_bin.mkdir()
        manifest_tmp.mkdir()
        (repo / "fixture.db.tar.zst").write_bytes(b"new database")
        (repo / "new.pkg.tar.zst").write_bytes(b"new package")

        _write_fake_mv(
            fake_bin,
            f"replace_published_identity = {replace_published_identity!r}\n"
            f"fail_promotion_after_move = {fail_promotion_after_move!r}\n"
            f"promotion_no_effect_success = {promotion_no_effect_success!r}\n"
            f"fail_rollback_after_move = {fail_rollback_after_move!r}\n"
            f"replace_rollback_identity = {replace_rollback_identity!r}\n"
            f"race_publish_destination = {race_publish_destination!r}\n"
            "source = pathlib.Path(sys.argv[-2]) if len(sys.argv) >= 3 else None\n"
            "destination = pathlib.Path(sys.argv[-1]) if len(sys.argv) >= 2 else None\n"
            "is_first_promotion = (\n"
            "    '--exchange' not in sys.argv\n"
            "    and source is not None\n"
            "    and destination is not None\n"
            "    and source.name.startswith('.published.candidate.')\n"
            "    and destination.name == 'published'\n"
            ")\n"
            "is_first_rollback = (\n"
            "    source is not None\n"
            "    and destination is not None\n"
            "    and source.name == 'published'\n"
            "    and destination.name.startswith('.published.failed.')\n"
            ")\n"
            "if is_first_promotion and promotion_no_effect_success:\n"
            "    raise SystemExit(0)\n"
            "if is_first_promotion and race_publish_destination:\n"
            "    destination.mkdir()\n"
            "    metadata = destination.stat()\n"
            "    (destination.parent / 'collision-identity').write_text(\n"
            "        f'{metadata.st_dev}:{metadata.st_ino}\\n', encoding='utf-8'\n"
            "    )\n"
            "result = subprocess.run([real_mv, *sys.argv[1:]])\n"
            "if is_first_promotion and result.returncode == 0 and replace_published_identity:\n"
            "    moved = destination.with_name(f'{destination.name}.moved')\n"
            "    destination.rename(moved)\n"
            "    shutil.copytree(moved, destination, symlinks=True)\n"
            "    shutil.rmtree(moved)\n"
            "if is_first_promotion and result.returncode == 0 and fail_promotion_after_move:\n"
            "    raise SystemExit(77)\n"
            "if is_first_rollback and result.returncode == 0 and replace_rollback_identity:\n"
            "    moved = destination.with_name(f'{destination.name}.moved')\n"
            "    destination.rename(moved)\n"
            "    shutil.copytree(moved, destination, symlinks=True)\n"
            "    shutil.rmtree(moved)\n"
            "if is_first_rollback and result.returncode == 0 and fail_rollback_after_move:\n"
            "    raise SystemExit(78)\n"
            "raise SystemExit(result.returncode)\n",
            extra_imports=("shutil",),
        )
        if precreate_failed_destination:
            _write_fake_date_collision(
                fake_bin, root / ".published.failed.fixed.{pid}"
            )

        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("BASH_FUNC_"):
                del environment[key]
        environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        environment["TMPDIR"] = str(manifest_tmp)
        if signal_after_promotion:
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
        return result, repo, publish

    def test_completed_first_promotion_reconciles_nonzero_command_status(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_move_transition(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Published verified pacman repo", result.stdout)
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            self.assertFalse(list(root.glob(".published.candidate.*")))
            self.assertFalse(list(root.glob(".published.failed.*")))
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_no_effect_first_promotion_normalizes_success_status_to_failure(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_move_transition(
                root, promotion_no_effect_success=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "could not promote candidate repository (status 1)", result.stderr
            )
            self.assertFalse(publish.exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_first_promotion_does_not_clobber_destination_created_during_move(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_move_transition(
                root,
                fail_promotion_after_move=False,
                race_publish_destination=True,
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "could not identify the repository after first publication promotion "
                "(status 1)",
                result.stderr,
            )
            self.assertIn("recovery state is indeterminate", result.stderr)
            expected_identity = (root / "collision-identity").read_text(
                encoding="utf-8"
            ).strip()
            publish_metadata = publish.stat()
            self.assertEqual(
                f"{publish_metadata.st_dev}:{publish_metadata.st_ino}",
                expected_identity,
            )
            self.assertEqual(list(publish.iterdir()), [])
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertIn("recovery manifests preserved at:", result.stderr)

    def test_ambiguous_first_promotion_preserves_recovery_state(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_move_transition(
                root, replace_published_identity=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "could not identify the repository after first publication promotion "
                "(status 77)",
                result.stderr,
            )
            self.assertIn("recovery state is indeterminate", result.stderr)
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertIn("recovery manifests preserved at:", result.stderr)

    def test_completed_first_rollback_reconciles_nonzero_command_status(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_move_transition(
                root,
                fail_promotion_after_move=False,
                signal_after_promotion=True,
                fail_rollback_after_move=True,
            )

            self.assertEqual(result.returncode, 143, result.stderr)
            self.assertFalse(publish.exists())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_ambiguous_first_rollback_preserves_recovery_state(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_move_transition(
                root,
                fail_promotion_after_move=False,
                signal_after_promotion=True,
                replace_rollback_identity=True,
            )

            self.assertEqual(result.returncode, 143, result.stderr)
            self.assertIn("first publication could not be rolled back", result.stderr)
            self.assertFalse(publish.exists())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertIn("recovery manifests preserved at:", result.stderr)

    def test_first_rollback_rejects_preexisting_failed_destination(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_move_transition(
                root,
                fail_promotion_after_move=False,
                signal_after_promotion=True,
                precreate_failed_destination=True,
            )

            self.assertEqual(result.returncode, 143, result.stderr)
            self.assertIn("first publication could not be rolled back", result.stderr)
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            expected_identity = (root / "collision-identity").read_text(
                encoding="utf-8"
            ).strip()
            failed_metadata = failed[0].stat()
            self.assertEqual(
                f"{failed_metadata.st_dev}:{failed_metadata.st_ino}", expected_identity
            )
            self.assertEqual(list(failed[0].iterdir()), [])
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertIn("recovery manifests preserved at:", result.stderr)

    def _run_first_publication_failed_copy_transition(
        self,
        root: Path,
        *,
        replace_failed_identity: bool = False,
        precreate_failed_destination: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        repo = root / "repo"
        publish = root / "published"
        fake_bin = root / "bin"
        manifest_tmp = root / "manifest-tmp"
        repo.mkdir()
        fake_bin.mkdir()
        manifest_tmp.mkdir()
        (repo / "fixture.db.tar.zst").write_bytes(b"new database")
        (repo / "new.pkg.tar.zst").write_bytes(b"new package")

        cmp_counter = root / "cmp-counter"
        _write_fake_cmp(fake_bin, cmp_counter, fail_from_call=2)

        _write_fake_mv(
            fake_bin,
            f"replace_failed_identity = {replace_failed_identity!r}\n"
            "source = pathlib.Path(sys.argv[-2]) if len(sys.argv) >= 3 else None\n"
            "destination = pathlib.Path(sys.argv[-1]) if len(sys.argv) >= 2 else None\n"
            "is_failed_copy_move = (\n"
            "    source is not None\n"
            "    and destination is not None\n"
            "    and source.name == 'published'\n"
            "    and destination.name.startswith('.published.failed.')\n"
            ")\n"
            "result = subprocess.run([real_mv, *sys.argv[1:]])\n"
            "if is_failed_copy_move and result.returncode == 0 and replace_failed_identity:\n"
            "    moved = destination.with_name(f'{destination.name}.moved')\n"
            "    destination.rename(moved)\n"
            "    shutil.copytree(moved, destination, symlinks=True)\n"
            "    shutil.rmtree(moved)\n"
            "if is_failed_copy_move and result.returncode == 0:\n"
            "    raise SystemExit(77)\n"
            "raise SystemExit(result.returncode)\n",
            extra_imports=("shutil",),
        )
        if precreate_failed_destination:
            _write_fake_date_collision(
                fake_bin, root / ".published.failed.fixed.{pid}"
            )

        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("BASH_FUNC_"):
                del environment[key]
        environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        environment["TMPDIR"] = str(manifest_tmp)

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
        return result, repo, publish

    def test_completed_first_failed_copy_move_reconciles_nonzero_command_status(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_failed_copy_transition(
                root
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "published repository failed post-promotion verification; no previous "
                "repository existed; failed copy retained",
                result.stderr,
            )
            self.assertNotIn("indeterminate", result.stderr)
            self.assertFalse(publish.exists())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_ambiguous_first_failed_copy_move_preserves_recovery_state(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_failed_copy_transition(
                root, replace_failed_identity=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "published verification failed and the failed repository could not "
                "be identified (status 77)",
                result.stderr,
            )
            self.assertIn(
                "first-publication recovery state is indeterminate; preserving "
                "repository locks and transaction paths for recovery",
                result.stderr,
            )
            self.assertFalse(publish.exists())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())
            self.assertIn(str(publish), result.stderr)
            self.assertIn(str(failed[0]), result.stderr)
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            manifest_prefix = "recovery manifests preserved at: "
            recovery_manifest_paths = [
                Path(line.removeprefix(manifest_prefix))
                for line in result.stderr.splitlines()
                if line.startswith(manifest_prefix)
            ]
            self.assertEqual(len(recovery_manifest_paths), 1, result.stderr)
            self.assertEqual(
                sorted(path.name for path in recovery_manifest_paths[0].iterdir()),
                ["candidate.json", "published.json", "staging.json"],
            )

    def test_first_failed_copy_rejects_preexisting_destination(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_first_publication_failed_copy_transition(
                root, precreate_failed_destination=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "published verification failed and the failed repository could not "
                "be identified (status 1)",
                result.stderr,
            )
            self.assertIn("recovery state is indeterminate", result.stderr)
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            expected_identity = (root / "collision-identity").read_text(
                encoding="utf-8"
            ).strip()
            failed_metadata = failed[0].stat()
            self.assertEqual(
                f"{failed_metadata.st_dev}:{failed_metadata.st_ino}", expected_identity
            )
            self.assertEqual(list(failed[0].iterdir()), [])
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertIn("recovery manifests preserved at:", result.stderr)

    def _run_retention_transition(
        self,
        root: Path,
        *,
        fail_retention_move: bool = False,
        fail_after_retention_move: bool = False,
        replace_retained_identity: bool = False,
        signal_after_retention_move: str | None = None,
        precreate_previous_destination: bool = False,
        race_previous_destination: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        repo = root / "repo"
        publish = root / "published"
        fake_bin = root / "bin"
        manifest_tmp = root / "manifest-tmp"
        repo.mkdir()
        publish.mkdir()
        fake_bin.mkdir()
        manifest_tmp.mkdir()
        (repo / "fixture.db.tar.zst").write_bytes(b"new database")
        (repo / "new.pkg.tar.zst").write_bytes(b"new package")
        (publish / "fixture.db.tar.zst").write_bytes(b"old database")
        (publish / "old.pkg.tar.zst").write_bytes(b"old package")
        _write_fake_mv(
            fake_bin,
            f"fail_retention_move = {fail_retention_move!r}\n"
            f"fail_after_retention_move = {fail_after_retention_move!r}\n"
            f"replace_retained_identity = {replace_retained_identity!r}\n"
            f"signal_after_retention_move = {signal_after_retention_move!r}\n"
            f"race_previous_destination = {race_previous_destination!r}\n"
            "source = pathlib.Path(sys.argv[-2]) if len(sys.argv) >= 3 else None\n"
            "destination = pathlib.Path(sys.argv[-1]) if len(sys.argv) >= 2 else None\n"
            "is_retention_move = (\n"
            "    source is not None\n"
            "    and destination is not None\n"
            "    and source.name.startswith('.published.candidate.')\n"
            "    and destination.name.startswith('published.previous.')\n"
            ")\n"
            "if is_retention_move and fail_retention_move:\n"
            "    raise SystemExit(77)\n"
            "if is_retention_move and race_previous_destination:\n"
            "    destination.mkdir()\n"
            "    metadata = destination.stat()\n"
            "    (destination.parent / 'collision-identity').write_text(\n"
            "        f'{metadata.st_dev}:{metadata.st_ino}\\n', encoding='utf-8'\n"
            "    )\n"
            "result = subprocess.run([real_mv, *sys.argv[1:]])\n"
            "if is_retention_move and result.returncode == 0 and fail_after_retention_move:\n"
            "    raise SystemExit(77)\n"
            "if is_retention_move and result.returncode == 0 and replace_retained_identity:\n"
            "    moved = destination.with_name(f'{destination.name}.moved')\n"
            "    destination.rename(moved)\n"
            "    shutil.copytree(moved, destination, symlinks=True)\n"
            "    shutil.rmtree(moved)\n"
            "if is_retention_move and result.returncode == 0 and signal_after_retention_move:\n"
            "    os.kill(os.getppid(), getattr(signal, f'SIG{signal_after_retention_move}'))\n"
            "    time.sleep(0.2)\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(result.returncode)\n",
            extra_imports=("os", "signal", "shutil", "time"),
        )
        if precreate_previous_destination:
            _write_fake_date_collision(
                fake_bin, root / "published.previous.fixed.{pid}"
            )
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("BASH_FUNC_"):
                del environment[key]
        environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        environment["TMPDIR"] = str(manifest_tmp)

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
        return result, repo, publish

    def _assert_signal_after_retention_move_keeps_new_publication(
        self, signal_name: str, expected_returncode: int
    ) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_retention_transition(
                root, signal_after_retention_move=signal_name
            )

            self.assertEqual(result.returncode, expected_returncode, result.stderr)
            self.assertNotIn("could not be retained", result.stderr)
            self.assertNotIn("preserving repository locks", result.stderr)
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
            self.assertFalse(list(root.glob(".published.failed.*")))
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_completed_retention_move_reconciles_nonzero_command_status(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_retention_transition(
                root, fail_after_retention_move=True
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("could not be retained", result.stderr)
            self.assertNotIn("preserving repository locks", result.stderr)
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
            self.assertFalse(list(root.glob(".published.failed.*")))
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])
            self.assertIn("Retained previous pacman repo", result.stdout)
            self.assertIn("Published verified pacman repo", result.stdout)

    def test_retention_move_failure_keeps_verified_publication_and_recovery_locks(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_retention_transition(
                root, fail_retention_move=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "verified repository was published but the previous repository "
                "could not be retained (status 77)",
                result.stderr,
            )
            self.assertIn(
                "verified publication is live but previous-repository retention "
                "is incomplete; preserving repository locks and transaction paths "
                "for recovery",
                result.stderr,
            )
            manifest_prefix = "recovery manifests preserved at: "
            recovery_manifest_paths = [
                Path(line.removeprefix(manifest_prefix))
                for line in result.stderr.splitlines()
                if line.startswith(manifest_prefix)
            ]
            self.assertEqual(len(recovery_manifest_paths), 1, result.stderr)
            recovery_manifest_dir = recovery_manifest_paths[0]
            self.assertEqual(recovery_manifest_dir.parent, root / "manifest-tmp")
            self.assertEqual(
                sorted(path.name for path in recovery_manifest_dir.iterdir()),
                ["candidate.json", "published.json", "staging.json"],
            )
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"new database"
            )
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            self.assertFalse((publish / "old.pkg.tar.zst").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertEqual(
                (candidates[0] / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((candidates[0] / "old.pkg.tar.zst").is_file())
            self.assertFalse(list(root.glob("published.previous.*")))
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())

    def test_retention_identity_mismatch_reports_nonzero_recovery_status(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_retention_transition(
                root, replace_retained_identity=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertRegex(
                result.stderr,
                r"verified repository was published but the previous repository "
                r"could not be retained \(status [1-9][0-9]*\)",
            )
            self.assertNotIn("(status 0)", result.stderr)
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
            self.assertFalse(list(root.glob(".published.failed.*")))
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())

    def test_retention_rejects_preexisting_previous_destination(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_retention_transition(
                root, precreate_previous_destination=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "verified repository was published but the previous repository "
                "could not be retained (status 1)",
                result.stderr,
            )
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"new database"
            )
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "old.pkg.tar.zst").is_file())
            previous = list(root.glob("published.previous.*"))
            self.assertEqual(len(previous), 1)
            expected_identity = (root / "collision-identity").read_text(
                encoding="utf-8"
            ).strip()
            previous_metadata = previous[0].stat()
            self.assertEqual(
                f"{previous_metadata.st_dev}:{previous_metadata.st_ino}",
                expected_identity,
            )
            self.assertEqual(list(previous[0].iterdir()), [])
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertIn("recovery manifests preserved at:", result.stderr)

    def test_retention_does_not_clobber_destination_created_during_move(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = self._run_retention_transition(
                root, race_previous_destination=True
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "verified repository was published but the previous repository "
                "could not be retained (status 1)",
                result.stderr,
            )
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "old.pkg.tar.zst").is_file())
            previous = list(root.glob("published.previous.*"))
            self.assertEqual(len(previous), 1)
            expected_identity = (root / "collision-identity").read_text(
                encoding="utf-8"
            ).strip()
            previous_metadata = previous[0].stat()
            self.assertEqual(
                f"{previous_metadata.st_dev}:{previous_metadata.st_ino}",
                expected_identity,
            )
            self.assertEqual(list(previous[0].iterdir()), [])
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertIn("recovery manifests preserved at:", result.stderr)

    def test_term_after_retention_move_keeps_new_publication_coherent(self):
        self._assert_signal_after_retention_move_keeps_new_publication("TERM", 143)

    def test_hup_after_retention_move_keeps_new_publication_coherent(self):
        self._assert_signal_after_retention_move_keeps_new_publication("HUP", 129)

    def test_existing_non_directory_destination_is_left_untouched(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            publish.write_bytes(b"preserve me")
            (repo / "fixture.db.tar.zst").write_bytes(b"database")
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

            self.assertEqual(result.returncode, 2)
            self.assertIn("publish dir exists and is not a directory", result.stderr)
            self.assertEqual(publish.read_bytes(), b"preserve me")
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_dry_run_plans_verified_candidate_and_previous_repository(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"database")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"

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
                    str(publish),
                ],
                cwd=REPO_ROOT,
                env=environment,
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

    def test_publication_requires_the_adjacent_shared_manifest_tool(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            isolated_tools = root / "tools"
            repo.mkdir()
            publish.mkdir()
            isolated_tools.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (repo / "new.pkg.tar.zst").write_bytes(b"new package")
            (publish / "fixture.db.tar.zst").write_bytes(b"old database")
            (publish / "old.pkg.tar.zst").write_bytes(b"old package")
            isolated_publish = isolated_tools / PUBLISH.name
            shutil.copy2(PUBLISH, isolated_publish)
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"

            result = subprocess.run(
                [
                    "zsh",
                    str(isolated_publish),
                    "--repo-dir",
                    str(repo),
                    "--repo-name",
                    "fixture",
                    "--publish-dir",
                    str(publish),
                ],
                cwd=root,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(
                result.stderr,
                f"missing repository manifest tool: "
                f"{isolated_tools / 'repository_manifest.py'}\n",
            )
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_test_mode_rejects_symlinked_publish_path_without_mutation(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            trusted_destination_parent = root / "trusted-destination-parent"
            publish_parent = root / "publish-parent"
            publish = publish_parent / "published"
            repo.mkdir()
            trusted_destination_parent.mkdir()
            publish_parent.symlink_to(trusted_destination_parent, target_is_directory=True)
            (repo / "fixture.db.tar.zst").write_bytes(b"database")
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

            self.assertEqual(result.returncode, 2)
            self.assertEqual(
                result.stderr,
                "publish dir must not contain symlink components under "
                f"/tmp: {publish_parent}\n",
            )
            self.assertFalse(publish.exists())
            self.assertEqual(list(trusted_destination_parent.iterdir()), [])
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertFalse((trusted_destination_parent / ".published.publish.lock").exists())

    def test_candidate_mode_drift_fails_before_promotion(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            fake_bin = root / "bin"
            repo.mkdir()
            publish.mkdir()
            fake_bin.mkdir()
            staged_database = repo / "fixture.db.tar.zst"
            staged_package = repo / "new.pkg.tar.zst"
            staged_database.write_bytes(b"new database")
            staged_package.write_bytes(b"new package")
            staged_package.chmod(0o644)
            published_database = publish / "fixture.db.tar.zst"
            published_package = publish / "old.pkg.tar.zst"
            published_database.write_bytes(b"old database")
            published_package.write_bytes(b"old package")
            real_rsync = shutil.which("rsync")
            self.assertIsNotNone(real_rsync)
            fake_rsync = fake_bin / "rsync"
            fake_rsync.write_text(
                "#!/bin/sh\n"
                f"{real_rsync!r} \"$@\" || exit $?\n"
                "for destination do :; done\n"
                "chmod 0600 -- \"${destination%/}/new.pkg.tar.zst\"\n",
                encoding="utf-8",
            )
            fake_rsync.chmod(0o755)
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
            self.assertIn(
                "candidate repository does not match verified staging", result.stderr
            )
            self.assertEqual(published_database.read_bytes(), b"old database")
            self.assertEqual(published_package.read_bytes(), b"old package")
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertEqual(
                (candidates[0] / "new.pkg.tar.zst").stat().st_mode & 0o777, 0o600
            )
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_candidate_mtime_drift_fails_before_promotion(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            fake_bin = root / "bin"
            repo.mkdir()
            publish.mkdir()
            fake_bin.mkdir()
            staged_database = repo / "fixture.db.tar.zst"
            staged_package = repo / "new.pkg.tar.zst"
            staged_database.write_bytes(b"new database")
            staged_package.write_bytes(b"new package")
            published_database = publish / "fixture.db.tar.zst"
            published_package = publish / "old.pkg.tar.zst"
            published_database.write_bytes(b"old database")
            published_package.write_bytes(b"old package")
            real_rsync = _resolve_real_binary("rsync")
            fake_rsync = fake_bin / "rsync"
            fake_rsync.write_text(
                f"#!{sys.executable}\n"
                "import os\n"
                "import pathlib\n"
                "import subprocess\n"
                "import sys\n"
                f"real_rsync = {real_rsync!r}\n"
                "result = subprocess.run([real_rsync, *sys.argv[1:]])\n"
                "if result.returncode != 0:\n"
                "    raise SystemExit(result.returncode)\n"
                "destination = pathlib.Path(sys.argv[-1].removesuffix('/'))\n"
                "package = destination / 'new.pkg.tar.zst'\n"
                "metadata = package.stat()\n"
                "os.utime(package, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1))\n",
                encoding="utf-8",
            )
            fake_rsync.chmod(0o755)
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
            self.assertIn(
                "candidate repository does not match verified staging", result.stderr
            )
            self.assertEqual(published_database.read_bytes(), b"old database")
            self.assertEqual(published_package.read_bytes(), b"old package")
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertEqual(
                (candidates[0] / "new.pkg.tar.zst").stat().st_mtime_ns,
                staged_package.stat().st_mtime_ns + 1,
            )
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def _run_restored_previous_failed_copy_transition(
        self,
        root: Path,
        *,
        failed_copy_outcome: str,
        precreate_failed_destination: bool = False,
        precreate_dangling_failed_destination: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        self.assertIn(
            failed_copy_outcome,
            {"completed_nonzero", "no_effect", "replaced_identity"},
        )
        repo = root / "repo"
        publish = root / "published"
        fake_bin = root / "bin"
        manifest_tmp = root / "manifest-tmp"
        repo.mkdir()
        publish.mkdir()
        fake_bin.mkdir()
        manifest_tmp.mkdir()
        (repo / "fixture.db.tar.zst").write_bytes(b"new database")
        (repo / "new.pkg.tar.zst").write_bytes(b"new package")
        (publish / "fixture.db.tar.zst").write_bytes(b"old database")
        (publish / "old.pkg.tar.zst").write_bytes(b"old package")
        _write_fake_cmp(fake_bin, root / "cmp-counter", fail_from_call=2)
        _write_fake_mv(
            fake_bin,
            f"failed_copy_outcome = {failed_copy_outcome!r}\n"
            "source = pathlib.Path(sys.argv[-2]) if len(sys.argv) >= 3 else None\n"
            "destination = pathlib.Path(sys.argv[-1]) if len(sys.argv) >= 2 else None\n"
            "is_failed_copy_move = (\n"
            "    source is not None\n"
            "    and destination is not None\n"
            "    and source.name.startswith('.published.candidate.')\n"
            "    and destination.name.startswith('.published.failed.')\n"
            ")\n"
            "if is_failed_copy_move and failed_copy_outcome == 'no_effect':\n"
            "    raise SystemExit(77)\n"
            "result = subprocess.run([real_mv, *sys.argv[1:]])\n"
            "if is_failed_copy_move and result.returncode == 0 and failed_copy_outcome == 'replaced_identity':\n"
            "    moved = destination.with_name(f'{destination.name}.moved')\n"
            "    destination.rename(moved)\n"
            "    shutil.copytree(moved, destination, symlinks=True)\n"
            "    shutil.rmtree(moved)\n"
            "if is_failed_copy_move and result.returncode == 0:\n"
            "    raise SystemExit(77)\n"
            "raise SystemExit(result.returncode)\n",
            extra_imports=("shutil",),
        )
        if precreate_failed_destination:
            _write_fake_date_collision(
                fake_bin, root / ".published.failed.fixed.{pid}"
            )
        elif precreate_dangling_failed_destination:
            _write_fake_date_collision(
                fake_bin,
                root / ".published.failed.fixed.{pid}",
                dangling_symlink=True,
            )
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("BASH_FUNC_"):
                del environment[key]
        environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        environment["TMPDIR"] = str(manifest_tmp)

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
        return result, repo, publish

    def test_completed_restored_previous_failed_copy_move_reconciles_nonzero_status(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = (
                self._run_restored_previous_failed_copy_transition(
                    root, failed_copy_outcome="completed_nonzero"
                )
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "published repository failed post-promotion verification; previous "
                "repository restored; failed copy retained",
                result.stderr,
            )
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_no_effect_restored_previous_failed_copy_move_names_recovery_paths(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = (
                self._run_restored_previous_failed_copy_transition(
                    root, failed_copy_outcome="no_effect"
                )
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "previous repository was restored but failed candidate retention "
                "could not be identified (status 77)",
                result.stderr,
            )
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertIn(str(candidates[0]), result.stderr)
            self.assertIn(str(root / ".published.failed."), result.stderr)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse(list(root.glob(".published.failed.*")))
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_ambiguous_restored_previous_failed_copy_move_names_recovery_paths(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = (
                self._run_restored_previous_failed_copy_transition(
                    root, failed_copy_outcome="replaced_identity"
                )
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "previous repository was restored but failed candidate retention "
                "could not be identified (status 77)",
                result.stderr,
            )
            self.assertIn(str(root / ".published.candidate."), result.stderr)
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertIn(str(failed[0]), result.stderr)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse(list(root.glob(".published.candidate.*")))
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_restored_previous_failed_copy_rejects_preexisting_destination(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = (
                self._run_restored_previous_failed_copy_transition(
                    root,
                    failed_copy_outcome="completed_nonzero",
                    precreate_failed_destination=True,
                )
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "previous repository was restored but failed candidate retention "
                "could not be identified (status 1)",
                result.stderr,
            )
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            expected_identity = (root / "collision-identity").read_text(
                encoding="utf-8"
            ).strip()
            failed_metadata = failed[0].stat()
            self.assertEqual(
                f"{failed_metadata.st_dev}:{failed_metadata.st_ino}", expected_identity
            )
            self.assertEqual(list(failed[0].iterdir()), [])
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertEqual(list((root / "manifest-tmp").iterdir()), [])

    def test_restored_previous_failed_copy_rejects_dangling_symlink_destination(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)

            result, repo, publish = (
                self._run_restored_previous_failed_copy_transition(
                    root,
                    failed_copy_outcome="completed_nonzero",
                    precreate_dangling_failed_destination=True,
                )
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "previous repository was restored but failed candidate retention "
                "could not be identified (status 1)",
                result.stderr,
            )
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue(failed[0].is_symlink())
            self.assertEqual(os.readlink(failed[0]), "missing-collision-target")
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

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
            _write_fake_cmp(fake_bin, cmp_counter, fail_from_call=2)
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
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            retained_index = result.stdout.index("Retained previous pacman repo")
            published_index = result.stdout.index("Published verified pacman repo")
            self.assertLess(retained_index, published_index)

    def test_publisher_contention_preserves_the_existing_writer_lock(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            writer_lock = Path(f"{repo}.writer.lock")
            repo.mkdir()
            writer_lock.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"database")
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

            self.assertEqual(result.returncode, 2)
            self.assertIn(
                "another repository writer appears to be active", result.stderr
            )
            self.assertTrue(writer_lock.is_dir())
            self.assertFalse(publish.exists())

    def test_signal_during_publisher_writer_lock_acquisition_cleans_owned_lock(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"database")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment[
                "ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_WRITER_LOCK_ACQUISITION"
            ] = "1"

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
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertFalse(publish.exists())

    def test_signal_after_destination_lock_acquisition_cleans_both_locks(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"database")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["ARCH_PKGS_PUBLISH_TEST_SIGNAL_AFTER_DESTINATION_LOCK"] = "1"

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
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            self.assertFalse(publish.exists())

    def test_symlinked_repo_alias_contends_on_the_canonical_writer_lock(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo_alias = root / "repo-alias"
            publish = root / "published"
            writer_lock = Path(f"{repo}.writer.lock")
            repo.mkdir()
            repo_alias.symlink_to(repo, target_is_directory=True)
            writer_lock.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"database")
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
                    str(repo_alias),
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
            self.assertIn(
                "another repository writer appears to be active", result.stderr
            )
            self.assertTrue(writer_lock.is_dir())
            self.assertFalse(Path(f"{repo_alias}.writer.lock").exists())
            self.assertFalse(publish.exists())

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
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())

    def test_signal_during_promotion_reconciliation_restores_previous_repository(
        self,
    ):
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
            environment["ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_PROMOTION"] = "1"

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
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())

    def test_signal_during_restoration_does_not_republish_failed_candidate(self):
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
            _write_fake_cmp(fake_bin, cmp_counter, fail_from_call=2)
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_RESTORATION"] = "1"
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

            self.assertEqual(result.returncode, 143)
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())

    def test_promotion_identity_failure_is_reconciled_before_cleanup(self):
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
            environment["ARCH_PKGS_PUBLISH_TEST_FAIL_IDENTITY_AFTER_PROMOTION"] = "1"

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
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_restoration_identity_failure_cannot_republish_failed_candidate(self):
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
            _write_fake_cmp(fake_bin, cmp_counter, fail_from_call=2)
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["ARCH_PKGS_PUBLISH_TEST_FAIL_IDENTITY_AFTER_RESTORATION"] = (
                "1"
            )
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
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((publish / "old.pkg.tar.zst").is_file())
            self.assertFalse((publish / "new.pkg.tar.zst").exists())
            candidates = list(root.glob(".published.candidate.*"))
            self.assertEqual(len(candidates), 1)
            self.assertTrue((candidates[0] / "new.pkg.tar.zst").is_file())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_first_publication_interruption_leaves_no_unverified_live_repo(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (repo / "new.pkg.tar.zst").write_bytes(b"new package")
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
            self.assertFalse(publish.exists())
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
            failed = list(root.glob(".published.failed.*"))
            self.assertEqual(len(failed), 1)
            self.assertTrue((failed[0] / "new.pkg.tar.zst").is_file())

    def test_signal_during_verified_first_finalization_keeps_published_repo(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (repo / "new.pkg.tar.zst").write_bytes(b"new package")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_FIRST_FINALIZATION"] = (
                "1"
            )

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
                (publish / "fixture.db.tar.zst").read_bytes(), b"new database"
            )
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            self.assertFalse(list(root.glob(".published.failed.*")))
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_signal_during_retention_finalization_keeps_verified_publication(self):
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
            environment[
                "ARCH_PKGS_PUBLISH_TEST_SIGNAL_DURING_RETENTION_FINALIZATION"
            ] = "1"

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
                (publish / "fixture.db.tar.zst").read_bytes(), b"new database"
            )
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            previous = list(root.glob("published.previous.*"))
            self.assertEqual(len(previous), 1)
            self.assertEqual(
                (previous[0] / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertTrue((previous[0] / "old.pkg.tar.zst").is_file())
            self.assertFalse(list(root.glob(".published.candidate.*")))
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())

    def test_failed_first_publication_rollback_preserves_both_locks(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (repo / "new.pkg.tar.zst").write_bytes(b"new package")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["ARCH_PKGS_PUBLISH_TEST_SIGNAL_AFTER_PROMOTION"] = "1"
            environment["ARCH_PKGS_PUBLISH_TEST_FAIL_FIRST_ROLLBACK"] = "1"

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
            self.assertIn("preserving repository locks", result.stderr)
            self.assertTrue((publish / "new.pkg.tar.zst").is_file())
            self.assertTrue((root / ".published.publish.lock").is_dir())
            self.assertTrue(Path(f"{repo}.writer.lock").is_dir())
            self.assertFalse(list(root.glob(".published.failed.*")))

    def test_retention_ceiling_fails_without_deleting_rollback_repositories(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            publish = root / "published"
            repo.mkdir()
            publish.mkdir()
            (repo / "fixture.db.tar.zst").write_bytes(b"new database")
            (publish / "fixture.db.tar.zst").write_bytes(b"old database")
            previous_one = root / "published.previous.1"
            previous_two = root / "published.previous.2"
            previous_one.mkdir()
            previous_two.mkdir()
            (previous_one / "sentinel").write_bytes(b"one")
            (previous_two / "sentinel").write_bytes(b"two")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("BASH_FUNC_"):
                    del environment[key]
            environment["ARCH_PKGS_PUBLISH_TEST_MODE"] = "1"
            environment["ARCH_PKGS_PUBLISH_RETENTION"] = "2"

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
            self.assertIn("retained previous-repository limit reached", result.stderr)
            self.assertEqual(
                (publish / "fixture.db.tar.zst").read_bytes(), b"old database"
            )
            self.assertEqual((previous_one / "sentinel").read_bytes(), b"one")
            self.assertEqual((previous_two / "sentinel").read_bytes(), b"two")
            self.assertFalse((root / ".published.publish.lock").exists())
            self.assertFalse(Path(f"{repo}.writer.lock").exists())
