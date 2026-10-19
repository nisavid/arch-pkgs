"""Exercise expiry warnings and deliberate, atomic TLS identity rotation."""

import importlib.util
import os
from pathlib import Path
import shutil
import ssl
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from tests.test_qdrant_cutover_tls import certificate


ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


expiry = load_tool("check_local_service_tls")
provisioning = load_tool("provision_local_service_tls")


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL required")
class ExpiryTests(unittest.TestCase):
    def test_warning_threshold_and_expired_or_unreadable_certificate(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cert, _ = certificate(directory, "near-expiry")
            self.assertEqual(expiry.check_certificate(cert, 0)[0], 0)
            code, message = expiry.check_certificate(cert, 30)
            self.assertEqual(code, 1)
            self.assertIn("TLS EXPIRY WARNING", message)
            self.assertIn("30 days", message)
            expired, _ = certificate(directory, "expired", expired=True)
            self.assertIn("TLS EXPIRED", expiry.check_certificate(expired)[1])
            self.assertIn("TLS ERROR", expiry.check_certificate(directory / "missing")[1])
            with self.assertRaises(ValueError):
                expiry.check_certificate(cert, -1)

    def test_warning_is_a_failed_process_with_actionable_journal_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            cert, _ = certificate(Path(temporary), "near-expiry")
            result = subprocess.run([
                "python3", str(ROOT / "tools/check_local_service_tls.py"),
                "--certificate", str(cert),
            ], text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("schedule deliberate rotation now", result.stderr)


class AtomicExchangeTests(unittest.TestCase):
    def test_exchange_preserves_both_complete_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "live", Path(temporary) / "staged"
            for path, value in ((first, "old"), (second, "new")):
                path.mkdir()
                (path / "cert.pem").write_text(value + " certificate")
                (path / "key.pem").write_text(value + " key")
            provisioning.exchange_directories(first, second)
            self.assertEqual((first / "cert.pem").read_text(), "new certificate")
            self.assertEqual((first / "key.pem").read_text(), "new key")
            self.assertEqual((second / "cert.pem").read_text(), "old certificate")
            self.assertEqual((second / "key.pem").read_text(), "old key")

    def test_unsupported_exchange_has_no_nonatomic_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "live", Path(temporary) / "staged"
            first.mkdir()
            second.mkdir()
            (first / "cert.pem").write_text("old")
            (second / "cert.pem").write_text("new")
            with mock.patch.object(provisioning.ctypes, "CDLL", return_value=object()):
                with self.assertRaisesRegex(OSError, "unavailable"):
                    provisioning.exchange_directories(first, second)
            self.assertEqual((first / "cert.pem").read_text(), "old")
            self.assertEqual((second / "cert.pem").read_text(), "new")


@unittest.skipUnless(os.geteuid() == 0 and shutil.which("openssl"), "root-owned identity verification requires root")
class ProtectedRotationTests(unittest.TestCase):
    def setUp(self):
        # /tmp is writable by others, while /root blocks consumer traversal.
        self.temporary = tempfile.TemporaryDirectory(prefix="tls-lifecycle-", dir="/run")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o755)
        self.live, self.staged = self.root / "tls", self.root / "tls-next"

    def old_identity(self, *, expired=False):
        self.live.mkdir(mode=0o755)
        cert, key = certificate(self.live, "old", expired=expired)
        cert.rename(self.live / "cert.pem")
        key.rename(self.live / "key.pem")
        (self.live / "cert.pem").chmod(0o644)
        (self.live / "key.pem").chmod(0o640)

    def test_rotate_and_rollback_a_nearly_expired_pair(self):
        self.old_identity()
        old = (self.live / "cert.pem").read_bytes()
        provisioning.provision(self.staged, "root")
        new = (self.staged / "cert.pem").read_bytes()
        self.assertEqual(expiry.check_certificate(self.staged / "cert.pem")[0], 0)
        provisioning.rotate(self.live, self.staged, "root")
        self.assertEqual((self.live / "cert.pem").read_bytes(), new)
        self.assertEqual((self.staged / "cert.pem").read_bytes(), old)
        self.assertEqual(stat.S_IMODE(self.live.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.live / "cert.pem").stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE((self.live / "key.pem").stat().st_mode), 0o640)
        # Normal renewal cannot install a pair with less than 30 days left.
        with self.assertRaises(subprocess.CalledProcessError):
            provisioning.rotate(self.live, self.staged, "root")
        provisioning.rotate(self.live, self.staged, "root", rollback=True)
        self.assertEqual((self.live / "cert.pem").read_bytes(), old)
        provisioning.validate_identity(self.live, 0)

    def test_expired_live_pair_can_be_replaced_but_never_restored(self):
        self.old_identity(expired=True)
        provisioning.provision(self.staged, "root")
        provisioning.rotate(self.live, self.staged, "root")
        current = (self.live / "cert.pem").read_bytes()
        with self.assertRaises(subprocess.CalledProcessError):
            provisioning.rotate(self.live, self.staged, "root", rollback=True)
        self.assertEqual((self.live / "cert.pem").read_bytes(), current)
        provisioning.validate_identity(self.live, 0)

    def test_provisioning_preserves_existing_identity_and_rotation_rejects_extra_files(self):
        provisioning.provision(self.live, "root")
        old = (self.live / "cert.pem").read_bytes()
        provisioning.provision(self.live, "root")
        self.assertEqual((self.live / "cert.pem").read_bytes(), old)
        provisioning.provision(self.staged, "root")
        (self.staged / "unrelated.conf").write_text("do not move")
        with self.assertRaisesRegex(ValueError, "only cert.pem and key.pem"):
            provisioning.rotate(self.live, self.staged, "root")
        self.assertEqual((self.live / "cert.pem").read_bytes(), old)

    def test_unsafe_or_mismatched_staging_never_changes_live_identity(self):
        provisioning.provision(self.live, "root")
        provisioning.provision(self.staged, "root")
        old = (self.live / "cert.pem").read_bytes()
        (self.staged / "key.pem").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "unsafe ownership or permissions"):
            provisioning.rotate(self.live, self.staged, "root")
        (self.staged / "key.pem").chmod(0o640)
        (self.staged / "cert.pem").write_bytes(old)
        with self.assertRaises(ssl.SSLError):
            provisioning.rotate(self.live, self.staged, "root")
        self.assertEqual((self.live / "cert.pem").read_bytes(), old)

    def test_inaccessible_staging_or_parent_never_changes_live_identity(self):
        provisioning.provision(self.live, "root")
        provisioning.provision(self.staged, "root")
        old = (self.live / "cert.pem").read_bytes()
        replacement = (self.staged / "cert.pem").read_bytes()
        for path in (self.staged, self.root):
            with self.subTest(path=path.name):
                path.chmod(0o700)
                try:
                    with self.assertRaisesRegex(ValueError, "traversable"):
                        provisioning.rotate(self.live, self.staged, "root")
                    self.assertEqual((self.live / "cert.pem").read_bytes(), old)
                    self.assertEqual((self.staged / "cert.pem").read_bytes(), replacement)
                finally:
                    path.chmod(0o755)

    def test_provisioning_refuses_existing_inaccessible_directory(self):
        self.live.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "traversable"):
            provisioning.provision(self.live, "root")
        self.assertEqual(list(self.live.iterdir()), [])
        self.live.chmod(0o755)
        provisioning.provision(self.live, "root")
        old = (self.live / "cert.pem").read_bytes()
        self.live.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "traversable"):
            provisioning.provision(self.live, "root")
        self.assertEqual((self.live / "cert.pem").read_bytes(), old)


if __name__ == "__main__":
    unittest.main()
