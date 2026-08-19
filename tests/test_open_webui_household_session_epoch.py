import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tools" / "fixtures" / "open-webui-household"
RUNTIME_HELPER = FIXTURE_ROOT / "open-webui-0.11.0-session-epoch.py"
LEDGER_HELPER = (
    REPO_ROOT / "packages" / "open-webui" / "open-webui-session-epoch-ledger.py"
)
SOURCE_PATCH = (
    REPO_ROOT / "packages" / "open-webui" / "0006-enforce-session-epoch.patch"
)
PRISTINE_INIT = FIXTURE_ROOT / "open-webui-0.11.0-pristine-init.py"
UDS_PATCH = FIXTURE_ROOT / "0001-open-webui-0.11-measurement-uds.patch"

OPEN_WEBUI_COMMIT = "f9590b8017199e56d5e953657e6498e3cef1d246"
OPEN_WEBUI_SDIST_SHA256 = (
    "e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SessionEpochCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = load_module("open_webui_session_epoch_fixture", RUNTIME_HELPER)

    def write_credential(self, root: Path, value: bytes, mode: int = 0o400) -> Path:
        path = root / self.runtime.CREDENTIAL_NAME
        path.write_bytes(value)
        path.chmod(mode)
        return path

    def test_service_credential_accepts_only_canonical_bounded_decimal(self):
        valid = {
            b"0": 0,
            b"1": 1,
            str(self.runtime.MAX_SESSION_EPOCH).encode(
                "ascii"
            ): self.runtime.MAX_SESSION_EPOCH,
        }
        for raw, expected in valid.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.runtime.parse_session_epoch(raw), expected)

        invalid = (
            b"",
            b"00",
            b"01",
            b"-1",
            b"+1",
            b"1\n",
            b" 1",
            b"1 ",
            b"1.0",
            b"true",
            b"\xff",
            str(self.runtime.MAX_SESSION_EPOCH + 1).encode("ascii"),
        )
        for raw in invalid:
            with (
                self.subTest(raw=raw),
                self.assertRaises(self.runtime.SessionEpochError),
            ):
                self.runtime.parse_session_epoch(raw)

    def test_service_start_requires_a_read_only_regular_systemd_credential(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                self.assertRaises(self.runtime.SessionEpochError),
            ):
                self.runtime.read_current_session_epoch()

            with (
                mock.patch.dict(
                    os.environ,
                    {self.runtime.CREDENTIALS_DIRECTORY_ENV: "relative"},
                    clear=True,
                ),
                self.assertRaises(self.runtime.SessionEpochError),
            ):
                self.runtime.read_current_session_epoch()

            with mock.patch.dict(
                os.environ,
                {self.runtime.CREDENTIALS_DIRECTORY_ENV: str(root)},
                clear=True,
            ):
                with self.assertRaises(self.runtime.SessionEpochError):
                    self.runtime.read_current_session_epoch()

                credential = self.write_credential(root, b"7", mode=0o600)
                with self.assertRaises(self.runtime.SessionEpochError):
                    self.runtime.read_current_session_epoch()

                credential.chmod(0o400)
                self.assertEqual(self.runtime.read_current_session_epoch(), 7)

                credential.unlink()
                credential.mkdir()
                with self.assertRaises(self.runtime.SessionEpochError):
                    self.runtime.read_current_session_epoch()

    def test_service_credential_rejects_symlinks_and_unreadable_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target"
            target.write_bytes(b"3")
            target.chmod(0o400)
            (root / self.runtime.CREDENTIAL_NAME).symlink_to(target)

            with (
                mock.patch.dict(
                    os.environ,
                    {self.runtime.CREDENTIALS_DIRECTORY_ENV: str(root)},
                    clear=True,
                ),
                self.assertRaises(self.runtime.SessionEpochError),
            ):
                self.runtime.read_current_session_epoch()

            (root / self.runtime.CREDENTIAL_NAME).unlink()
            self.write_credential(root, b"3")
            with (
                mock.patch.dict(
                    os.environ,
                    {self.runtime.CREDENTIALS_DIRECTORY_ENV: str(root)},
                    clear=True,
                ),
                mock.patch.object(self.runtime.os, "open", side_effect=PermissionError),
                self.assertRaises(self.runtime.SessionEpochError),
            ):
                self.runtime.read_current_session_epoch()

    def test_all_session_surfaces_require_the_exact_integer_claim(self):
        surfaces = ("http-header", "http-cookie", "socket-io", "terminal-websocket")
        current = 41
        valid_claims = self.runtime.with_current_session_epoch({"id": "user"}, current)
        self.assertIs(type(valid_claims[self.runtime.SESSION_EPOCH_CLAIM]), int)

        invalid_values = (
            None,
            current - 1,
            current + 1,
            str(current),
            True,
            False,
            float(current),
        )
        for surface in surfaces:
            with self.subTest(surface=surface, case="exact"):
                self.assertTrue(
                    self.runtime.token_epoch_is_current(valid_claims, current)
                )
            with self.subTest(surface=surface, case="missing"):
                self.assertFalse(
                    self.runtime.token_epoch_is_current({"id": "user"}, current)
                )
            for value in invalid_values:
                with self.subTest(surface=surface, value=value):
                    claims = {"id": "user", self.runtime.SESSION_EPOCH_CLAIM: value}
                    self.assertFalse(
                        self.runtime.token_epoch_is_current(claims, current)
                    )

    def test_ordinary_restart_at_the_same_epoch_preserves_sessions(self):
        claims = self.runtime.with_current_session_epoch({"id": "user"}, 9)
        self.assertTrue(self.runtime.token_epoch_is_current(claims, 9))
        self.assertTrue(self.runtime.token_epoch_is_current(claims, 9))


class SessionEpochLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = load_module("open_webui_session_epoch_ledger", LEDGER_HELPER)
        cls.runtime = load_module(
            "open_webui_session_epoch_restore_fixture", RUNTIME_HELPER
        )

    def test_initialize_is_explicit_and_ordinary_reads_do_not_advance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "current"
            self.assertEqual(
                self.ledger.initialize_epoch_ledger(path, required_owner_uid=None),
                0,
            )
            self.assertEqual(path.read_bytes(), b"0")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                self.ledger.read_epoch_ledger(path, required_owner_uid=None), 0
            )
            self.assertEqual(
                self.ledger.read_epoch_ledger(path, required_owner_uid=None), 0
            )
            self.assertEqual(path.read_bytes(), b"0")

    def test_reserve_is_forward_only_atomic_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "current"
            self.ledger.initialize_epoch_ledger(path, required_owner_uid=None)
            self.assertEqual(
                self.ledger.reserve_next_epoch(path, required_owner_uid=None), 1
            )
            self.assertEqual(path.read_bytes(), b"1")

            path.write_bytes(str(self.ledger.MAX_SESSION_EPOCH).encode("ascii"))
            path.chmod(0o600)
            with self.assertRaises(self.ledger.SessionEpochLedgerError):
                self.ledger.reserve_next_epoch(path, required_owner_uid=None)
            self.assertEqual(
                path.read_bytes(),
                str(self.ledger.MAX_SESSION_EPOCH).encode("ascii"),
            )

    def test_reserve_before_restore_invalidates_old_sessions_and_accepts_new_ones(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "current"
            old_epoch = self.ledger.initialize_epoch_ledger(
                path,
                required_owner_uid=None,
            )
            old_claims = self.runtime.with_current_session_epoch(
                {"id": "user"},
                old_epoch,
            )

            restored_epoch = self.ledger.reserve_next_epoch(
                path,
                required_owner_uid=None,
            )
            new_claims = self.runtime.with_current_session_epoch(
                {"id": "user"},
                restored_epoch,
            )

            self.assertFalse(
                self.runtime.token_epoch_is_current(old_claims, restored_epoch)
            )
            self.assertTrue(
                self.runtime.token_epoch_is_current(new_claims, restored_epoch)
            )

    def test_reserve_detects_torn_or_malformed_state_without_repairing_it(self):
        malformed_values = (b"", b"01", b"2\n", b"-1", b"garbage")
        for raw in malformed_values:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "current"
                path.write_bytes(raw)
                path.chmod(0o600)
                with self.assertRaises(self.ledger.SessionEpochLedgerError):
                    self.ledger.initialize_epoch_ledger(
                        path,
                        required_owner_uid=None,
                    )
                with self.assertRaises(self.ledger.SessionEpochLedgerError):
                    self.ledger.reserve_next_epoch(path, required_owner_uid=None)
                self.assertEqual(path.read_bytes(), raw)

    def test_failed_atomic_replace_keeps_the_previous_epoch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "current"
            self.ledger.initialize_epoch_ledger(path, required_owner_uid=None)
            with (
                mock.patch.object(
                    self.ledger.os,
                    "replace",
                    side_effect=OSError("fixture failure"),
                ),
                self.assertRaises(OSError),
            ):
                self.ledger.reserve_next_epoch(path, required_owner_uid=None)
            self.assertEqual(path.read_bytes(), b"0")
            self.assertEqual(list(path.parent.glob(".current.*")), [])

    def test_concurrent_reservations_are_serialized_without_lost_updates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "current"
            self.ledger.initialize_epoch_ledger(path, required_owner_uid=None)
            reservations = 24
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(
                    pool.map(
                        lambda _: self.ledger.reserve_next_epoch(
                            path,
                            required_owner_uid=None,
                        ),
                        range(reservations),
                    )
                )
            self.assertEqual(sorted(results), list(range(1, reservations + 1)))
            self.assertEqual(
                self.ledger.read_epoch_ledger(path, required_owner_uid=None),
                reservations,
            )

    def test_mutating_cli_is_root_only_and_defaults_outside_runtime_restore_state(self):
        self.assertEqual(
            self.ledger.DEFAULT_LEDGER_PATH,
            Path("/var/lib/open-webui-session-epoch/current"),
        )
        with (
            mock.patch.object(self.ledger.os, "geteuid", return_value=1000),
            self.assertRaises(self.ledger.SessionEpochLedgerError),
        ):
            self.ledger.require_root_mutation_authority()

    def test_ledger_rejects_relative_unsafe_wrong_owner_or_symlinked_parent(self):
        with self.assertRaises(self.ledger.SessionEpochLedgerError):
            self.ledger.initialize_epoch_ledger(
                Path("relative/current"),
                required_owner_uid=None,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unsafe = root / "unsafe"
            unsafe.mkdir(mode=0o700)
            unsafe.chmod(0o770)
            with self.assertRaises(self.ledger.SessionEpochLedgerError):
                self.ledger.initialize_epoch_ledger(
                    unsafe / "current",
                    required_owner_uid=None,
                )

            wrong_owner = root / "wrong-owner"
            wrong_owner.mkdir(mode=0o700)
            with self.assertRaises(self.ledger.SessionEpochLedgerError):
                self.ledger.initialize_epoch_ledger(
                    wrong_owner / "current",
                    required_owner_uid=wrong_owner.stat().st_uid + 1,
                )

            real = root / "real"
            real.mkdir(mode=0o700)
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaises(self.ledger.SessionEpochLedgerError):
                self.ledger.initialize_epoch_ledger(
                    linked / "current",
                    required_owner_uid=None,
                )


class OpenWebUISessionEpochPatchContractTests(unittest.TestCase):
    def test_patch_is_bound_to_the_exact_open_webui_subject(self):
        patch = SOURCE_PATCH.read_text()
        self.assertIn(f"X-Open-WebUI-Commit: {OPEN_WEBUI_COMMIT}", patch)
        self.assertIn(f"X-Open-WebUI-Sdist-SHA256: {OPEN_WEBUI_SDIST_SHA256}", patch)
        self.assertIn(
            "X-Open-WebUI-Init-SHA256: "
            "11cd2fad929db12c687795239ab3b6af1b5ea6f3ad7363deedfabf9651dd22d4",
            patch,
        )
        self.assertIn(
            "X-Open-WebUI-Auth-SHA256: "
            "d78b5f3fc2249d0b1719d0d280eb9aeef83922ef7b55c87cd843eedbd2e25c34",
            patch,
        )
        self.assertIn(
            "X-Open-WebUI-Auth-Router-SHA256: "
            "32bf3812b9a44face4bfa7efe4a0770577dc8608127bcbb41f25ea15a6085945",
            patch,
        )

    def test_patch_validates_epoch_before_app_import_or_uvicorn_bind(self):
        for predecessor in (None, UDS_PATCH):
            with (
                self.subTest(predecessor=predecessor),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                source_root = Path(temp_dir)
                init_path = source_root / "open_webui" / "__init__.py"
                init_path.parent.mkdir()
                shutil.copyfile(PRISTINE_INIT, init_path)
                if predecessor is not None:
                    prepared = subprocess.run(
                        ["git", "apply", str(predecessor)],
                        cwd=source_root,
                        text=True,
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )
                    self.assertEqual(prepared.returncode, 0, prepared.stderr)
                applied = subprocess.run(
                    [
                        "git",
                        "apply",
                        "--include=open_webui/__init__.py",
                        str(SOURCE_PATCH),
                    ],
                    cwd=source_root,
                    text=True,
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(applied.returncode, 0, applied.stderr)
                source = init_path.read_text()

            validation = source.index("    read_current_session_epoch()")
            app_import = source.index("    import open_webui.main")
            uvicorn_bind = source.index("    uvicorn.run(")
            self.assertLess(validation, app_import)
            self.assertLess(validation, uvicorn_bind)

    def test_patch_mints_and_validates_every_session_through_central_seams(self):
        patch = SOURCE_PATCH.read_text()
        self.assertIn("+CURRENT_SESSION_EPOCH = read_current_session_epoch()", patch)
        self.assertIn(
            "+    payload = with_current_session_epoch(data, CURRENT_SESSION_EPOCH)",
            patch,
        )
        self.assertIn(
            "+        if not token_epoch_is_current(decoded, CURRENT_SESSION_EPOCH):",
            patch,
        )
        self.assertIn("+            return None", patch)
        self.assertIn("+        raise HTTPException(", patch)
        self.assertIn("+            detail=ERROR_MESSAGES.API_KEY_NOT_ALLOWED,", patch)

    def test_runtime_patch_has_no_ledger_write_authority(self):
        runtime_source = RUNTIME_HELPER.read_text()
        self.assertNotIn("flock", runtime_source)
        self.assertNotIn("replace(", runtime_source)
        self.assertNotIn("reserve", runtime_source)
        self.assertNotIn("O_WRONLY", runtime_source)
        self.assertNotIn("O_RDWR", runtime_source)

    def test_exercised_runtime_helper_is_the_exact_file_added_by_the_patch(self):
        patch_lines = SOURCE_PATCH.read_text().splitlines()
        hunk_start = patch_lines.index("@@ -0,0 +1,100 @@") + 1
        added_lines = []
        for line in patch_lines[hunk_start:]:
            if line == "-- ":
                break
            self.assertTrue(line.startswith("+"), line)
            added_lines.append(line[1:])

        self.assertEqual("\n".join(added_lines) + "\n", RUNTIME_HELPER.read_text())

    def test_stale_signout_reuses_epoch_aware_decode_without_router_mutation(self):
        patch = SOURCE_PATCH.read_text()
        self.assertIn(
            "if not token_epoch_is_current(decoded, CURRENT_SESSION_EPOCH):", patch
        )
        self.assertNotIn("open_webui/routers/auths.py", patch)

    def test_existing_pristine_init_remains_exact(self):
        import hashlib

        self.assertEqual(
            hashlib.sha256(PRISTINE_INIT.read_bytes()).hexdigest(),
            "11cd2fad929db12c687795239ab3b6af1b5ea6f3ad7363deedfabf9651dd22d4",
        )


if __name__ == "__main__":
    unittest.main()
