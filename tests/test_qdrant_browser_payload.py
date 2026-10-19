import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qdrant_g2_harness"
SPEC = importlib.util.spec_from_file_location("browser_payload", HARNESS / "browser_payload.py")
PAYLOAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAYLOAD)
BINARY = b"reviewed qdrant executable fixture\n"


def file_entry(name, content=b"fixture", **kwargs):
    member = tarfile.TarInfo(name)
    member.size = len(content)
    member.mode = 0o6777  # Archive permissions must not survive staging.
    for key, value in kwargs.items():
        setattr(member, key, value)
    return member, content


def package_entries(kind):
    if kind == "qdrant":
        files = {name: BINARY if name == "usr/bin/qdrant" else b"fixture"
                 for name in PAYLOAD.QDRANT_FILES}
    else:
        files = {
            PAYLOAD.WEB_ROOT + "/index.html": b"<html>fixture</html>",
            PAYLOAD.WEB_ROOT + "/cloud/data.json": b"{}",
            PAYLOAD.WEB_ROOT + "/assets/a file.js": b"fixture",
            PAYLOAD.WEB_LICENSE: b"license",
        }
    directories = []
    for name in sorted(PAYLOAD.parents(set(files))):
        member = tarfile.TarInfo(name + "/")
        member.type = tarfile.DIRTYPE
        directories.append((member, b""))
    return directories + [file_entry("./" + name, content)
                          for name, content in sorted(files.items())] + [
        file_entry(name) for name in sorted(PAYLOAD.METADATA)
    ]


def write_archive(path, entries, mode="w"):
    with tarfile.open(path, mode, format=tarfile.PAX_FORMAT) as archive:
        for member, content in entries:
            archive.addfile(member, io.BytesIO(content))


class BrowserPayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload = self.root / "payload"
        self.payload.mkdir()
        self.archive = self.root / "candidate.tar"

    def stage(self, entries, kind="web-ui", mode="w"):
        write_archive(self.archive, entries, mode)
        PAYLOAD.stage_archive(self.archive, kind, self.payload)

    def test_real_package_layouts_keep_only_runtime_bytes_and_safe_modes(self):
        self.stage(package_entries("qdrant"), "qdrant")
        self.stage(package_entries("web-ui"), mode="w:gz")
        self.assertEqual((self.payload / "qdrant").read_bytes(), BINARY)
        self.assertEqual((self.payload / "qdrant").stat().st_mode & 0o7777, 0o755)
        self.assertEqual((self.payload / "web-ui/index.html").stat().st_mode & 0o7777, 0o644)
        self.assertEqual(
            {p.relative_to(self.payload).as_posix() for p in self.payload.rglob("*") if p.is_file()},
            {"qdrant", "config.yaml", "qdrant.spdx.json", "web-ui/index.html",
             "web-ui/cloud/data.json", "web-ui/assets/a file.js"},
        )
        PAYLOAD.write_manifests(self.payload, self.root)
        listing = (self.root / "web-ui-tree.txt").read_text()
        self.assertIn("  usr/share/qdrant/web-ui/assets/a file.js\n", listing)
        self.assertEqual(listing.splitlines(), sorted(listing.splitlines(), key=lambda s: s.split("  ", 1)[1]))
        self.assertIn(hashlib.sha256(BINARY).hexdigest() + "  /usr/bin/qdrant\n",
                      (self.root / "payload-inputs.sha256").read_text())

    def test_runtime_replacements_and_cross_package_collisions_are_rejected(self):
        for kind in ("qdrant", "web-ui"):
            for name in ("usr/bin/bash", "usr/bin/python3", "usr/bin/sha256sum",
                         "usr/lib/libc.so.6", "usr/lib/python3.12/site-packages/sitecustomize.py",
                         "usr/share/qdrant/qdrant.spdx.json" if kind == "web-ui"
                         else "usr/share/qdrant/web-ui/index.html"):
                with self.subTest(kind=kind, name=name), self.assertRaisesRegex(ValueError, "unexpected"):
                    self.stage([file_entry(name)], kind)
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.stage([file_entry("usr/bin/qdrant")])

    def test_aliases_and_resolved_extended_paths_cannot_escape_allowlist(self):
        names = ["/usr/bin/bash", "../escape", PAYLOAD.WEB_ROOT + "/../../bin/bash",
                 PAYLOAD.WEB_ROOT + "//file", PAYLOAD.WEB_ROOT + "/./file",
                 PAYLOAD.WEB_ROOT + "/bad\nname", PAYLOAD.WEB_ROOT + "/bad\\name"]
        for name in names:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.stage([file_entry(name)])
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.stage([file_entry(PAYLOAD.WEB_ROOT + "/safe", pax_headers={"path": "usr/bin/bash"})])
        directory = tarfile.TarInfo("/")
        directory.type = tarfile.DIRTYPE
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.stage([(directory, b"")])

    def test_links_special_and_sparse_members_are_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE,
                     tarfile.CHRTYPE, tarfile.BLKTYPE):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "non-regular"):
                self.stage([file_entry(PAYLOAD.WEB_ROOT + "/link", b"", type=kind,
                                       linkname="/usr/bin/bash")])
        with self.assertRaisesRegex(ValueError, "non-regular"):
            self.stage([file_entry(PAYLOAD.WEB_ROOT + "/sparse",
                                   pax_headers={"GNU.sparse.name": "sparse"})])
        self.assertEqual(list(self.payload.iterdir()), [])

    def test_duplicate_normalized_paths_and_file_directory_conflicts_are_rejected(self):
        name = PAYLOAD.WEB_ROOT + "/entry"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.stage([file_entry(name), file_entry("./" + name)])
        for index, entries in enumerate((
                [file_entry(name), file_entry(name + "/child")],
                [file_entry(name + "/child"), file_entry(name)])):
            with self.subTest(order=index):
                shutil.rmtree(self.payload)
                self.payload.mkdir()
                with self.assertRaisesRegex(ValueError, "directory"):
                    self.stage(entries)

    def test_missing_payload_fails(self):
        with self.assertRaisesRegex(ValueError, "missing web-ui payload"):
            self.stage([file_entry(PAYLOAD.WEB_LICENSE)])

    @unittest.skipUnless(shutil.which("zstd"), "zstd is required")
    def test_zstd_packages_and_corrupt_frames(self):
        write_archive(self.archive, package_entries("web-ui"))
        compressed = subprocess.run(["zstd", "-q", "-c", str(self.archive)],
                                    check=True, capture_output=True).stdout
        self.archive.write_bytes(compressed)
        PAYLOAD.stage_archive(self.archive, "web-ui", self.payload)
        self.assertTrue((self.payload / "web-ui/index.html").is_file())
        shutil.rmtree(self.payload)
        self.payload.mkdir()
        self.archive.write_bytes(compressed[:-2])
        with self.assertRaises((ValueError, tarfile.TarError)):
            PAYLOAD.stage_archive(self.archive, "web-ui", self.payload)


@unittest.skipUnless(shutil.which("zsh"), "zsh is required")
class BrowserLauncherTests(unittest.TestCase):
    """Run the real launcher; record its mount boundary instead of requiring Chrome."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.record = self.root / "bwrap.json"
        recorder = self.bin / "bwrap"
        recorder.write_text('''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
args = sys.argv[1:]
pathlib.Path(os.environ["BWRAP_RECORD"]).write_text(json.dumps(args))
raw = pathlib.Path(args[args.index("/g2-out/raw") - 1])
(raw / "pid-namespace").write_text("pid:[0]\\n")
for name in ("payload-inputs.sha256", "web-ui-tree.txt", "trusted-runtime.sha256"):
    shutil.copyfile(raw.parent / name, raw / name)
if os.environ.get("CORRUPT_EVIDENCE"):
    (raw / os.environ["CORRUPT_EVIDENCE"]).write_text("forged\\n")
''')
        recorder.chmod(0o755)
        self.qpkg = self.root / "qdrant.tar"
        self.wpkg = self.root / "web-ui.tar"
        write_archive(self.qpkg, package_entries("qdrant"))
        write_archive(self.wpkg, package_entries("web-ui"))

    def launch(self, corrupt=None):
        env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
               "BWRAP_RECORD": str(self.record)}
        if corrupt:
            env["CORRUPT_EVIDENCE"] = corrupt
        return subprocess.run([
            "zsh", str(HARNESS / "run-browser.zsh"), str(self.root / "run"),
            str(self.qpkg), hashlib.sha256(self.qpkg.read_bytes()).hexdigest(),
            str(self.wpkg), hashlib.sha256(self.wpkg.read_bytes()).hexdigest(),
            hashlib.sha256(BINARY).hexdigest(),
        ], env=env, capture_output=True, text=True, timeout=30)

    def test_legitimate_payload_keeps_trusted_runtime_and_host_evidence_separate(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.record.read_text())
        binds = [args[i + 1:i + 3] for i, value in enumerate(args) if value == "--ro-bind"]
        self.assertIn(["/usr", "/usr"], binds)
        self.assertIn([str(self.root / "run/payload"), "/g2-payload"], binds)
        self.assertNotIn("--overlay-src", args)
        self.assertNotIn("--ro-overlay", args)
        writable = [args[i + 1:i + 3] for i, value in enumerate(args) if value == "--bind"]
        self.assertEqual(writable, [[str(self.root / "run/state"), "/var/lib/qdrant"],
                                    [str(self.root / "run/out/raw"), "/g2-out/raw"]])
        self.assertFalse((self.root / "run/private/secret.env").exists())
        self.assertEqual((self.root / "run").stat().st_mode & 0o777, 0o700)

    def test_malicious_archives_are_rejected_before_namespace_entry(self):
        for name in ("usr/bin/bash", "usr/bin/python3", "usr/bin/sha256sum", "usr/bin/qdrant",
                     "usr/lib/libc.so.6", "usr/lib/python3.12/site-packages/sitecustomize.py"):
            with self.subTest(name=name):
                write_archive(self.wpkg, package_entries("web-ui") + [file_entry(name)])
                result = self.launch()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unexpected candidate", result.stderr)
                self.assertFalse(self.record.exists())
                self.assertFalse((self.root / "run/private/secret.env").exists())
                shutil.rmtree(self.root / "run")

    def test_forged_payload_tree_or_runtime_evidence_cannot_report_success(self):
        for name in ("payload-inputs.sha256", "web-ui-tree.txt", "trusted-runtime.sha256"):
            with self.subTest(name=name):
                result = self.launch(corrupt=name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("do not match host evidence", result.stderr)
                self.assertFalse((self.root / "run/private/secret.env").exists())
                shutil.rmtree(self.root / "run")


if __name__ == "__main__":
    unittest.main()
