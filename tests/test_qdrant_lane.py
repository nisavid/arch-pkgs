import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
QDRANT_DIR = REPO_ROOT / "packages" / "qdrant"
WEB_UI_DIR = REPO_ROOT / "packages" / "qdrant-web-ui"
WEB_UI_VERIFIER = WEB_UI_DIR / "verify-package.py"
MIGRATION_TOOL = REPO_ROOT / "tools" / "validate_qdrant_migration.zsh"
SECRET_PREFLIGHT = QDRANT_DIR / "qdrant-secret-preflight"
QDRANT_EVIDENCE_DIR = (
    REPO_ROOT / "docs" / "maintainers" / "evidence" / "qdrant-1.19.0-1"
)


class QdrantLaneContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def load_web_ui_verifier(self, source_path: Path = WEB_UI_VERIFIER):
        original_dont_write_bytecode = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec = importlib.util.spec_from_file_location(
                "qdrant_web_ui_verify_package", source_path
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            sys.dont_write_bytecode = original_dont_write_bytecode

    def write_minimal_web_ui_archive_root(
        self,
        root: Path,
        *,
        extra_pkginfo: tuple[str, ...] = (),
        omitted_metadata: tuple[str, ...] = (),
    ) -> None:
        metadata = {
            ".BUILDINFO": "format = 2\npkgname = qdrant-web-ui\n",
            ".MTREE": "#mtree\n/set type=file uid=0 gid=0 mode=644\n",
            ".PKGINFO": "\n".join(
                (
                    "pkgname = qdrant-web-ui",
                    "pkgbase = qdrant-web-ui",
                    "xdata = pkgtype=pkg",
                    "pkgver = 0.2.16-1",
                    "pkgdesc = Static dashboard assets for Qdrant",
                    "url = https://github.com/qdrant/qdrant-web-ui",
                    "builddate = 1786983811",
                    "packager = Qdrant verifier contract test",
                    "size = 1",
                    "arch = any",
                    "license = Apache-2.0",
                    "makedepend = python",
                    *extra_pkginfo,
                    "",
                )
            ),
        }
        for name, contents in metadata.items():
            if name in omitted_metadata:
                continue
            path = root / name
            path.write_text(contents, encoding="utf-8")
            path.chmod(0o644)

    def build_web_ui_test_archive(
        self,
        root: Path,
        archive: Path,
        members: tuple[str, ...],
        *,
        root_identity: bool = True,
    ) -> None:
        command = ["bsdtar", "--format=pax"]
        if root_identity:
            command.extend(
                ("--uid", "0", "--gid", "0", "--uname", "root", "--gname", "root")
            )
        command.extend(("-cf", str(archive), "-C", str(root), *members))
        subprocess.run(command, check=True, capture_output=True, text=True)

    def run_web_ui_verifier(self, archive: Path):
        return subprocess.run(
            [sys.executable, str(WEB_UI_VERIFIER), str(archive)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    def test_server_package_pins_the_accepted_final_and_intermediate_identities(self):
        srcinfo = self.read("packages/qdrant/.SRCINFO")
        migration_srcinfo = self.read("packages/qdrant-migration/.SRCINFO")
        maintenance_record = self.read("packages/qdrant/README.md")

        self.assertIn("pkgver = 1.19.0", srcinfo)
        self.assertIn(
            "e0c9a030ae47d95f7c739598343bd2529c817fe262c4e7b2a4f1070ff82a024e",
            srcinfo,
        )
        self.assertIn("pkgname = qdrant-migration", migration_srcinfo)
        self.assertIn("pkgver = 1.18.3", migration_srcinfo)
        self.assertIn(
            "c5f918b4f37279ec00b22b718ca54bca7b43c9d17628b28b8eba363beceb0c96",
            migration_srcinfo,
        )
        for identity in (
            "af875b4bfd98103f7c0ee34fe4f25c5099893ca9",
            "74f3e85b9473c62560006c043e13737ce6b48412",
            "1.18.3",
            "3ea8cf7ce633256fb1b2a75b0de9d9ce60b22254",
            "db8fa43fcb6aedec1e739487e17a99731b74590a",
            "c5f918b4f37279ec00b22b718ca54bca7b43c9d17628b28b8eba363beceb0c96",
        ):
            with self.subTest(identity=identity):
                self.assertIn(identity, maintenance_record)

    def test_native_build_recipes_filter_only_inherited_architecture_flags(self):
        inherited_flags = (
            "-O2 -pipe -march=x86-64-v3 -mcpu=native " "-mtune=generic -fno-plt"
        )
        expected_flags = "-O2 -pipe -fno-plt"

        for relative_path in (
            "packages/qdrant/PKGBUILD",
            "packages/qdrant-migration/PKGBUILD",
        ):
            with self.subTest(relative_path=relative_path):
                pkgbuild_path = REPO_ROOT / relative_path
                pkgbuild = pkgbuild_path.read_text(encoding="utf-8")
                evaluated = subprocess.run(
                    [
                        "bash",
                        "-c",
                        ('source "$1"; ' '_without_native_arch_flags "$2"'),
                        "qdrant-native-flag-contract",
                        str(pkgbuild_path),
                        inherited_flags,
                    ],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )

                self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
                self.assertEqual(evaluated.stdout, expected_flags)
                self.assertRegex(
                    pkgbuild,
                    r'export CFLAGS="\$\(_without_native_arch_flags "\$\{CFLAGS\}"\)',
                )
                self.assertRegex(
                    pkgbuild,
                    r'export CXXFLAGS="\$\(_without_native_arch_flags "\$\{CXXFLAGS\}"\)',
                )

    def test_native_build_recipes_emit_only_the_declared_non_debug_artifact(self):
        for relative_path in (
            "packages/qdrant/PKGBUILD",
            "packages/qdrant-migration/PKGBUILD",
        ):
            with self.subTest(relative_path=relative_path):
                pkgbuild_path = REPO_ROOT / relative_path
                evaluated = subprocess.run(
                    [
                        "bash",
                        "-c",
                        'source "$1"; printf "%s\\n" "${options[@]}"',
                        "qdrant-native-artifact-contract",
                        str(pkgbuild_path),
                    ],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )

                self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
                self.assertEqual(set(evaluated.stdout.splitlines()), {"!debug", "!lto"})
                srcinfo = pkgbuild_path.with_name(".SRCINFO").read_text(
                    encoding="utf-8"
                )
                self.assertEqual(
                    set(re.findall(r"(?m)^\s*options = (.+)$", srcinfo)),
                    {"!debug", "!lto"},
                )

    def test_server_package_owns_the_dashboard_dependency_and_active_layout(self):
        srcinfo = self.read("packages/qdrant/.SRCINFO")
        pkgbuild = self.read("packages/qdrant/PKGBUILD")
        tmpfiles = self.read("packages/qdrant/qdrant.tmpfiles")

        self.assertRegex(srcinfo, r"(?m)^\s*depends = qdrant-web-ui$")
        self.assertIn(
            "/usr/share/qdrant/web-ui", self.read("packages/qdrant/qdrant.config.yaml")
        )
        self.assertNotIn("/var/lib/qdrant/static", tmpfiles)
        self.assertNotIn("/var/lib/qdrant/static", pkgbuild)

    def test_server_config_is_loopback_only_and_disables_outbound_features(self):
        config = yaml.safe_load(self.read("packages/qdrant/qdrant.config.yaml"))

        self.assertTrue(config["telemetry_disabled"])
        self.assertEqual(config["service"]["host"], "127.0.0.1")
        self.assertEqual(config["service"]["http_port"], 6333)
        self.assertEqual(config["service"]["grpc_port"], 6334)
        self.assertFalse(config["service"]["enable_cors"])
        self.assertFalse(config["service"]["enable_snapshot_url_recovery"])
        self.assertTrue(config["service"]["jwt_rbac"])
        self.assertTrue(config["service"]["hide_jwt_dashboard"])
        self.assertEqual(
            config["service"]["static_content_dir"], "/usr/share/qdrant/web-ui"
        )
        self.assertTrue(config["service"]["enable_static_content"])
        self.assertFalse(config["cluster"]["enabled"])
        self.assertEqual(
            config["storage"]["snapshots_config"]["snapshots_storage"], "local"
        )
        self.assertNotIn("s3_config", config["storage"]["snapshots_config"])
        self.assertNotIn("inference", config)

        self.assertEqual(config["storage"]["max_collections"], 64)
        self.assertEqual(
            config["storage"]["quotas"],
            {
                "enabled": True,
                "max_resident_memory_percent": 80,
                "max_disk_usage_percent": 85,
                "release_margin_percent": 10,
            },
        )
        strict_mode = config["storage"]["collection"]["strict_mode"]
        self.assertTrue(strict_mode["enabled"])
        self.assertEqual(strict_mode["max_query_limit"], 1000)
        self.assertEqual(strict_mode["max_timeout"], 120)
        self.assertTrue(strict_mode["unindexed_filtering_retrieve"])
        self.assertTrue(strict_mode["unindexed_filtering_update"])

    def test_service_fails_closed_without_a_valid_external_secret(self):
        service = self.read("packages/qdrant/qdrant.service")
        preflight = self.read("packages/qdrant/qdrant-secret-preflight")
        source_names = {
            ".SRCINFO",
            "PKGBUILD",
            "README.md",
            "qdrant.config.yaml",
            "qdrant-secret-preflight",
            "qdrant.service",
            "qdrant.sysusers",
            "qdrant.tmpfiles",
            "qdrant-web-ui-headers.patch",
        }
        package_files = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in QDRANT_DIR.iterdir()
            if path.is_file() and path.name in source_names
        )

        self.assertRegex(
            service,
            r"(?m)^EnvironmentFile=/etc/qdrant/qdrant\.env$",
            "the environment file must be mandatory, without systemd's optional '-' prefix",
        )
        self.assertRegex(service, r"(?m)^ExecStartPre=.*qdrant\.env$")
        self.assertRegex(
            preflight,
            r"QDRANT__SERVICE__API_KEY=.*(?:a-f|0-9).*64",
        )
        self.assertFalse((QDRANT_DIR / "qdrant.env").exists())
        self.assertNotRegex(
            package_files,
            r"(?m)^QDRANT__SERVICE__API_KEY=[0-9a-f]{64,}$",
            "no usable admin/HMAC secret may be committed or shipped",
        )

    def test_service_uses_the_package_owned_secret_preflight(self):
        srcinfo = self.read("packages/qdrant/.SRCINFO")
        pkgbuild = self.read("packages/qdrant/PKGBUILD")
        service = self.read("packages/qdrant/qdrant.service")

        self.assertTrue(os.access(SECRET_PREFLIGHT, os.X_OK))
        self.assertRegex(srcinfo, r"(?m)^\s*source = qdrant-secret-preflight$")
        self.assertIn("qdrant-secret-preflight", pkgbuild)
        self.assertIn("/usr/lib/qdrant/qdrant-secret-preflight", pkgbuild)
        self.assertRegex(
            service,
            r"(?m)^ExecStartPre=/usr/lib/qdrant/qdrant-secret-preflight /etc/qdrant/qdrant\.env$",
        )

    @unittest.skipUnless(
        shutil.which("unshare") or shutil.which("fakeroot"),
        "unshare or fakeroot is required",
    )
    def test_secret_preflight_accepts_only_the_exact_safe_file_contract(self):
        namespace_probe = (
            subprocess.run(
                ["unshare", "--user", "--map-root-user", "--", "true"],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if shutil.which("unshare")
            else None
        )
        use_user_namespace = (
            namespace_probe is not None and namespace_probe.returncode == 0
        )
        if not use_user_namespace and not shutil.which("fakeroot"):
            self.skipTest("this host permits neither a user namespace nor fakeroot")

        def run_with_fakeroot(
            path: Path, *, owner: int, group: int
        ) -> subprocess.CompletedProcess[str]:
            shell = 'chown -h "$1:$2" "$3" 2>/dev/null || :; ' 'exec "$4" "$3"'
            return subprocess.run(
                [
                    "fakeroot",
                    "--",
                    "sh",
                    "-c",
                    shell,
                    "qdrant-secret-preflight-test",
                    str(owner),
                    str(group),
                    str(path),
                    str(SECRET_PREFLIGHT),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )

        def run_preflight(
            path: Path,
            *,
            map_fixture_owner_to_root: bool = True,
            force_fakeroot: bool = False,
        ) -> subprocess.CompletedProcess[str]:
            if map_fixture_owner_to_root and use_user_namespace and not force_fakeroot:
                command = [
                    "unshare",
                    "--user",
                    "--map-root-user",
                    "--",
                    str(SECRET_PREFLIGHT),
                    str(path),
                ]
            elif map_fixture_owner_to_root:
                return run_with_fakeroot(path, owner=0, group=0)
            else:
                command = [str(SECRET_PREFLIGHT), str(path)]
            return subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )

        def write_secret(path: Path, content: str, mode: int = 0o640) -> None:
            path.write_text(content, encoding="utf-8")
            path.chmod(mode)

        valid_line = f"QDRANT__SERVICE__API_KEY={'a' * 64}\n"
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            valid = fixture / "valid.env"
            write_secret(valid, valid_line)

            accepted = run_preflight(valid)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            if shutil.which("fakeroot"):
                accepted_fakeroot = run_preflight(valid, force_fakeroot=True)
                self.assertEqual(
                    accepted_fakeroot.returncode,
                    0,
                    accepted_fakeroot.stderr,
                )

            content_cases = {
                "empty": "",
                "short": f"QDRANT__SERVICE__API_KEY={'a' * 63}\n",
                "uppercase-hex": f"QDRANT__SERVICE__API_KEY={'A' * 64}\n",
                "multiple": valid_line + valid_line,
                "extra-variable": valid_line + "OTHER=value\n",
                "wrong-name": f"qdrant__service__api_key={'a' * 64}\n",
                "leading-space": " " + valid_line,
                "trailing-space": valid_line.rstrip("\n") + " \n",
            }
            for name, content in content_cases.items():
                with self.subTest(case=name):
                    candidate = fixture / f"{name}.env"
                    write_secret(candidate, content)
                    rejected = run_preflight(candidate)
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn(
                        "QDRANT__SERVICE__API_KEY",
                        f"{rejected.stdout}\n{rejected.stderr}",
                    )

            for mode in (0o600, 0o644):
                with self.subTest(mode=oct(mode)):
                    candidate = fixture / f"mode-{mode:o}.env"
                    write_secret(candidate, valid_line, mode)
                    rejected = run_preflight(candidate)
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn("0640", f"{rejected.stdout}\n{rejected.stderr}")

            wrong_owner = fixture / "wrong-owner.env"
            write_secret(wrong_owner, valid_line)
            rejected_owner = run_preflight(wrong_owner, map_fixture_owner_to_root=False)
            self.assertNotEqual(rejected_owner.returncode, 0)
            self.assertIn("root", f"{rejected_owner.stdout}\n{rejected_owner.stderr}")

            if shutil.which("fakeroot"):
                wrong_group = fixture / "wrong-group.env"
                write_secret(wrong_group, valid_line)
                rejected_group = run_with_fakeroot(
                    wrong_group, owner=0, group=os.getgid() + 1
                )
                self.assertNotEqual(rejected_group.returncode, 0)
                self.assertIn(
                    "group", f"{rejected_group.stdout}\n{rejected_group.stderr}"
                )

            directory = fixture / "directory.env"
            directory.mkdir(mode=0o640)
            rejected_directory = run_preflight(directory)
            self.assertNotEqual(rejected_directory.returncode, 0)
            self.assertIn(
                "regular", f"{rejected_directory.stdout}\n{rejected_directory.stderr}"
            )

            target = fixture / "target.env"
            write_secret(target, valid_line)
            symlink = fixture / "symlink.env"
            symlink.symlink_to(target)
            rejected_symlink = run_preflight(symlink)
            self.assertNotEqual(rejected_symlink.returncode, 0)
            self.assertIn(
                "symlink", f"{rejected_symlink.stdout}\n{rejected_symlink.stderr}"
            )

            missing = fixture / "missing.env"
            rejected_missing = run_preflight(missing, map_fixture_owner_to_root=False)
            self.assertNotEqual(rejected_missing.returncode, 0)
            self.assertIn(
                "regular", f"{rejected_missing.stdout}\n{rejected_missing.stderr}"
            )

    def test_service_exposes_the_accepted_resource_and_sandbox_limits(self):
        service = self.read("packages/qdrant/qdrant.service")

        for directive in (
            "TasksMax=2048",
            "MemoryHigh=80%",
            "MemoryMax=90%",
            "NoNewPrivileges=true",
            "PrivateDevices=true",
            "ProtectHome=true",
            "ProtectSystem=strict",
            "ProtectClock=true",
            "ProtectHostname=true",
            "ProtectKernelLogs=true",
            "ProtectKernelModules=true",
            "ProtectKernelTunables=true",
            "ProtectProc=invisible",
            "ProcSubset=pid",
            "RemoveIPC=true",
            "RestrictNamespaces=true",
            "IPAddressDeny=any",
            "IPAddressAllow=localhost",
        ):
            with self.subTest(directive=directive):
                self.assertIn(directive, service)
        self.assertRegex(service, r"(?m)^CapabilityBoundingSet=$")
        self.assertRegex(service, r"(?m)^AmbientCapabilities=$")
        self.assertRegex(service, r"(?m)^SystemCallFilter=@system-service$")

    def test_dashboard_response_headers_enforce_the_accepted_browser_boundary(self):
        patch = self.read("packages/qdrant/qdrant-web-ui-headers.patch")

        for directive in (
            "default-src 'self'",
            "base-uri 'none'",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'",
        ):
            with self.subTest(directive=directive):
                self.assertIn(directive, patch)
        for header, value in (
            ("Content-Security-Policy", None),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
        ):
            with self.subTest(header=header):
                self.assertIn(header, patch)
                if value is not None:
                    self.assertRegex(patch, rf"{re.escape(header)}.*{re.escape(value)}")

    def test_catalog_keeps_all_qdrant_lanes_deferred_until_g4_passes(self):
        catalog = self.read("packages/README.md")

        self.assertRegex(
            catalog,
            r"(?m)^\| \[`qdrant`\]\(qdrant/\) \| `qdrant` \| 1\.19\.0-1 \| deferred \|.*\| no \|$",
        )
        self.assertRegex(
            catalog,
            r"(?m)^\| \[`qdrant-web-ui`\]\(qdrant-web-ui/\) \| `qdrant-web-ui` \| 0\.2\.16-1 \| deferred \|.*\| no \|$",
        )
        self.assertRegex(
            catalog,
            r"(?m)^\| \[`qdrant-migration`\]\(qdrant-migration/\) \| `qdrant-migration` \| 1\.18\.3-1 \| deferred \|.*\| no \|$",
        )
        self.assertIn("G0-G3", catalog)
        self.assertIn("coupled Haystack G4 gate", catalog)
        self.assertIn("docs/maintainers/qdrant-migration-acceptance.md", catalog)

    def test_migration_runbook_preserves_both_routes_and_recovery_evidence(self):
        runbook = self.read("docs/maintainers/qdrant-migration-acceptance.md")

        for requirement in (
            "1.17.1 → 1.18.3 → 1.19.0",
            "Empty-state route",
            "Retained-data route",
            "cold copy",
            "same-minor snapshot",
            "next-minor snapshot",
            "full-storage restore",
            "separate empty target",
            "alias replay",
            "stable explicit IDs",
            "restart persistence",
            "dense, sparse, and hybrid",
            "truncated",
            "checksum-mismatched",
            "--force_snapshot",
            "priority=no_sync",
            "seven days",
            "separate explicit approval",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, runbook)
        self.assertIn("tools/validate_qdrant_migration.zsh --plan", runbook)
        self.assertIn("tools/validate_qdrant_migration.zsh --execute", runbook)
        self.assertIn("--work-root /tmp/", runbook)
        self.assertIn("--http-port 16333", runbook)
        self.assertIn("--grpc-port 16334", runbook)
        self.assertIn("cd packages/qdrant-migration", runbook)
        self.assertIn("makepkg --nodeps -f", runbook)
        self.assertIn("does not satisfy pacman's dependency resolution", runbook)
        self.assertIn("G0", runbook)
        self.assertIn("G1", runbook)
        self.assertIn("G2", runbook)
        self.assertIn("G3", runbook)
        self.assertIn("deferred", runbook)
        self.assertIn("Publication eligible: no", runbook)

    def test_migration_runbook_binds_the_strengthened_g3_contract_and_exit_index(self):
        runbook = self.read("docs/maintainers/qdrant-migration-acceptance.md")

        for requirement in (
            "--qdrant-1.17.1-package",
            "d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb",
            "25531392",
            "23f9b7628f8886edf1d6dbd45216a3755eb28bcf00c1e38d391087de58c81bde",
            "1001",
            "indexed_group",
            "unindexed_group",
            "eight pages",
            "limit 1000",
            "limit 1001",
            "1.17.1 full-storage snapshot into a 1.18.3 target",
            "1.18.3 full-storage snapshot into a 1.19.0 target",
            "pre-pressure",
            "post-rejection",
            "post-release retry",
            "post-restart",
            "exit 130",
            "exit 143",
            "manifest.runtime-validated.json",
            "manifest.json",
            "G0/G1 artifact manifest",
            "G2 unit-runtime record",
            "G2 browser record",
            "top-level acceptance index",
            "G4",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, runbook)

    def test_g1_requires_neutral_build_roots_and_private_path_free_archive_metadata(
        self,
    ):
        runbook = self.read("docs/maintainers/qdrant-migration-acceptance.md")

        self.assertIn("neutral build root", runbook)
        self.assertIn(".BUILDINFO", runbook)
        self.assertIn("private or machine-local checkout path", runbook)
        self.assertIn("reject", runbook.casefold())

    def test_g0_pins_the_isolated_network_disabled_builder_contract(self):
        containerfile = self.read("containers/qdrant-builder/Containerfile")
        runbook = self.read("docs/maintainers/qdrant-migration-acceptance.md")
        base_digest = (
            "sha256:ee205c220399524a683cf495d411691b921baed8ab47cdc6d732efa782fae484"
        )
        builder_digest = (
            "sha256:876d4b2bfe03167c6d29f368def3050d4b1d16b3f89deead8379b61ccada10b0"
        )
        image_id = "e4c00aadeb4a4d52f48ebd3d2ea32ae9433a02761e925589b0a6d619a837166f"

        self.assertEqual(
            containerfile.splitlines()[0],
            f"FROM docker.io/library/archlinux@{base_digest}",
        )
        for identity in (
            "containers/qdrant-builder/Containerfile",
            base_digest,
            builder_digest,
            image_id,
            "all three package candidates",
            "container network disabled",
        ):
            with self.subTest(identity=identity):
                self.assertIn(identity, runbook)

    def test_g0_builder_workflow_is_reconstructable_from_empty_caches(self):
        runbook = self.read("docs/maintainers/qdrant-migration-acceptance.md")
        package_readme = self.read("packages/qdrant/README.md")

        for relative_path, document in (
            ("docs/maintainers/qdrant-migration-acceptance.md", runbook),
            ("packages/qdrant/README.md", package_readme),
        ):
            normalized = " ".join(document.split())
            with self.subTest(relative_path=relative_path):
                self.assertRegex(
                    normalized,
                    r"empty.*`SRCDEST`.*`CARGO_HOME` caches",
                )
                self.assertRegex(
                    normalized,
                    r"fresh neutral.*package.*build.*artifact",
                )
                for identity in (
                    "qdrant-web-ui",
                    "1786983811",
                    "qdrant-migration",
                    "1786981596",
                    "qdrant",
                    "1786981317",
                    "`_source_date_epoch`",
                    "SBOM content",
                    "makepkg --verifysource",
                    "makepkg --nodeps -o",
                    "--pull=never",
                    "--network=none",
                ):
                    self.assertIn(identity, normalized)
                self.assertRegex(
                    normalized,
                    r"Prefetch outputs.*(?:not publication|never) candidates",
                )
                self.assertRegex(
                    normalized,
                    r"(?i:only) (?:package archives produced by the network-disabled|offline final archives).*enter G0",
                )

        for exact_command_contract in (
            "SRCDEST=/build/sources",
            "CARGO_HOME=/build/cargo",
            "CARGO_NET_OFFLINE=true",
            "/build/package",
            "/build/build",
            "/build/artifacts",
            "/build/sources",
            "/build/cargo",
            "makepkg --nodeps --cleanbuild --force",
        ):
            with self.subTest(exact_command_contract=exact_command_contract):
                self.assertIn(exact_command_contract, runbook)

    def test_g0_builder_evidence_rejects_cache_and_output_ambiguity(self):
        runbook = self.read("docs/maintainers/qdrant-migration-acceptance.md")
        normalized = " ".join(runbook.split())

        for contract in (
            "prefetch package, build, and artifact roots are never reused",
            "PKGBUILD SHA-256",
            "Cargo.lock SHA-256",
            "package-input manifest SHA-256",
            "source-cache manifest SHA-256",
            "Cargo-cache manifest SHA-256",
            "builder image ID and repository digest",
            "network mode",
            "exact prefetch and final commands",
            "cache, input, and output manifest digests",
            "qdrant-1.19.0-1-x86_64.pkg.tar.zst",
            "qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst",
            "qdrant-web-ui-0.2.16-1-any.pkg.tar.zst",
            "debug or undeclared output",
            "incomplete-cache negative control",
            "must fail before any candidate archive",
            "`--network=none` is the recorded offline boundary",
            "`CARGO_NET_OFFLINE=true` is required for every reconstruction",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, normalized)

        self.assertIn(
            "find <candidate-output-root> -mindepth 1 -maxdepth 1 -printf '%y %f\\n'",
            runbook,
        )
        self.assertRegex(
            normalized,
            r"exact output-set validator.*exactly the three declared archives",
        )

    def test_maintained_1_19_release_delta_is_explicit_in_operator_docs(self):
        for relative_path in (
            "packages/qdrant/README.md",
            "docs/maintainers/qdrant-migration-acceptance.md",
        ):
            document = self.read(relative_path)
            with self.subTest(relative_path=relative_path):
                self.assertIn("single-file mmap", document)
                self.assertRegex(
                    document,
                    r"(?s)single-file mmap.*accepted only after.*migration",
                )
                for deferred_feature in (
                    "TurboQuant",
                    "explicit memory-placement",
                    "speculative prefix",
                ):
                    self.assertIn(deferred_feature, document)
                self.assertRegex(
                    document,
                    r"(?s)TurboQuant.*explicit memory-placement.*speculative prefix.*remain disabled",
                )
                self.assertIn("/points/query", document)
                self.assertRegex(document, r"/points/query.*batch and group")
                self.assertRegex(
                    document,
                    r"(?s)legacy search, recommend, and discover.*not restored",
                )

    def test_remaining_1_19_release_deltas_have_explicit_dispositions(self):
        for relative_path in (
            "docs/maintainers/qdrant-migration-acceptance.md",
            "packages/qdrant/README.md",
        ):
            document = self.read(relative_path)
            normalized = " ".join(document.split())
            with self.subTest(relative_path=relative_path):
                self.assertIn("global `GET /quotas` API", normalized)
                self.assertIn("strict-mode `max_resident_memory_percent`", normalized)
                self.assertIn("deprecated", normalized)
                self.assertRegex(
                    normalized,
                    r"strict-mode `max_resident_memory_percent`.*not preserved",
                )
                self.assertIn(
                    "`storage.quotas.max_resident_memory_percent`", normalized
                )
                self.assertRegex(
                    normalized,
                    r"1\.19 snapshot-recovery changes.*accepted only through.*"
                    r"collection.*full-storage.*corruption(?:-| )rejection.*"
                    r"retry.*restart matrix",
                )
                self.assertRegex(
                    normalized,
                    r"URL snapshot recovery remains disabled.*"
                    r"snapshot storage remains local",
                )
                self.assertRegex(
                    normalized,
                    r"Web UI 0\.2\.16.*Usage Quotas.*accepted as a read-only view.*"
                    r"authenticated global quota state",
                )
                self.assertRegex(
                    normalized,
                    r"Usage Quotas.*does not relax API authentication.*"
                    r"grant users direct dashboard or API access",
                )

    def test_web_ui_package_pins_the_accepted_release_and_architecture(self):
        srcinfo = self.read("packages/qdrant-web-ui/.SRCINFO")
        maintenance_record = self.read("packages/qdrant-web-ui/README.md")

        self.assertIn("pkgname = qdrant-web-ui", srcinfo)
        self.assertIn("pkgver = 0.2.16", srcinfo)
        self.assertIn("pkgrel = 1", srcinfo)
        self.assertRegex(srcinfo, r"(?m)^\s*arch = any$")
        self.assertIn(
            "4446f0cea024078011c78cd24a592c9b563656d15205818563fa6b22d394dd29",
            srcinfo,
        )
        self.assertIn(
            "be85d9cffc5d5ad8122c4fe332cd6731cddcd508a61d77ee918626fc4d977577",
            srcinfo,
        )
        for identity in (
            "018e83a869a3d2b831e92664e8d33f51ec7981b1",
            "d3f7a1174933ab637d9711ea45456d32b878b50e",
            "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
        ):
            with self.subTest(identity=identity):
                self.assertIn(identity, maintenance_record)

    def test_web_ui_payload_is_static_read_only_and_has_no_runtime_bootstrap(self):
        srcinfo = self.read("packages/qdrant-web-ui/.SRCINFO")
        pkgbuild = self.read("packages/qdrant-web-ui/PKGBUILD")

        self.assertNotRegex(srcinfo, r"(?m)^\s*depends = ")
        self.assertNotRegex(srcinfo, r"(?m)^\s*install = ")
        self.assertFalse(list(WEB_UI_DIR.glob("*.install")))
        self.assertIn("/usr/share/qdrant/web-ui", pkgbuild)
        self.assertIn("/usr/share/licenses/${pkgname}/LICENSE", pkgbuild)
        self.assertRegex(pkgbuild, r"find [^\n]+ -type d -exec chmod 755")
        self.assertRegex(pkgbuild, r"find [^\n]+ -type f -exec chmod 644")
        self.assertIn("install -Dm644", pkgbuild)
        self.assertNotRegex(
            pkgbuild,
            r"(?m)^\s*(?:node|npm|npx|pnpm|yarn|curl|wget)\b",
        )

        verifier = self.read("packages/qdrant-web-ui/verify-package.py")
        for payload in (
            "spdx",
            "editor.worker",
            "json.worker",
            "graph_layout",
            ".wasm",
            "root",
            "drwxr-xr-x",
            "-rw-r--r--",
        ):
            with self.subTest(payload=payload):
                self.assertIn(payload, verifier.casefold())

    def test_web_ui_replaces_automatic_feeds_with_packaged_fail_closed_data(self):
        pkgbuild = self.read("packages/qdrant-web-ui/PKGBUILD")
        patcher = self.read("packages/qdrant-web-ui/patch-runtime-urls.py")
        verifier = self.read("packages/qdrant-web-ui/verify-package.py")

        self.assertIn("patch-runtime-urls.py", pkgbuild)
        for replacement in (
            "/dashboard/web-ui-info.json",
            "/dashboard/datasets.json",
            "qdrant.tech/web-ui-info",
            "snapshots.qdrant.io",
        ):
            with self.subTest(replacement=replacement):
                self.assertIn(replacement, patcher)
                self.assertIn(replacement, verifier)
        self.assertIn("disabled:", patcher)
        self.assertEqual(self.read("packages/qdrant-web-ui/web-ui-info.json"), "{}\n")
        self.assertEqual(self.read("packages/qdrant-web-ui/datasets.json"), "[]\n")

    def test_web_ui_cloud_data_neutralizer_is_packaged_and_exact(self):
        relative_path = "packages/qdrant-web-ui/cloud-data.json"

        self.assertTrue((REPO_ROOT / relative_path).is_file())
        self.assertEqual(self.read(relative_path), "null\n")
        pkgbuild = self.read("packages/qdrant-web-ui/PKGBUILD")
        srcinfo = self.read("packages/qdrant-web-ui/.SRCINFO")
        self.assertIn('"${srcdir}/cloud-data.json"', pkgbuild)
        self.assertIn('"${pkgdir}/usr/share/qdrant/web-ui/cloud/data.json"', pkgbuild)
        self.assertIn("source = cloud-data.json", srcinfo)
        self.assertIn(
            "38e0b9de817f645c4bec37c0d4a3e58baecccb040f5718dc069a72c7385a0bed",
            srcinfo,
        )
        verifier = self.read("packages/qdrant-web-ui/verify-package.py")
        self.assertIn('web_root / "cloud/data.json": b"null\\n"', verifier)
        self.assertIn(".INSTALL", verifier)
        self.assertIn("unexpected package install hook", verifier)

    def test_web_ui_verifier_loading_does_not_mutate_the_source_inventory(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            verifier_path = fixture / "verify-package.py"
            shutil.copyfile(WEB_UI_VERIFIER, verifier_path)
            before = sorted(
                str(path.relative_to(fixture)) for path in fixture.rglob("*")
            )

            original_cache_prefix = sys.pycache_prefix
            original_dont_write_bytecode = sys.dont_write_bytecode
            try:
                sys.pycache_prefix = None
                sys.dont_write_bytecode = False
                verifier = self.load_web_ui_verifier(verifier_path)
            finally:
                sys.pycache_prefix = original_cache_prefix
                sys.dont_write_bytecode = original_dont_write_bytecode

            self.assertTrue(callable(verifier.validate_archive_members))
            after = sorted(
                str(path.relative_to(fixture)) for path in fixture.rglob("*")
            )
            self.assertEqual(after, before)

    def test_web_ui_verifier_rejects_archive_and_extracted_tree_links(self):
        verifier = self.load_web_ui_verifier()
        member = "usr/share/qdrant/web-ui/assets/console.svg"
        symlink_listing = (
            "lrwxrwxrwx  0 0 0 0 Jan 01 00:00 " f"{member} -> outside-sentinel"
        )
        hardlink_listing = (
            "hrw-r--r--  0 0 0 0 Jan 01 00:00 " f"{member} link to outside-sentinel"
        )
        regular_listing = f"-rw-r--r--  0 0 0 12 Jan 01 00:00 {member}"

        with self.assertRaisesRegex(SystemExit, "non-regular archive entry"):
            verifier.validate_archive_members([member], [symlink_listing])
        with self.assertRaisesRegex(SystemExit, "non-regular archive entry"):
            verifier.validate_archive_members([member], [hardlink_listing])
        verifier.validate_archive_members([member], [regular_listing])

        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            root = fixture / "root"
            web_root = root / "usr/share/qdrant/web-ui/assets"
            web_root.mkdir(parents=True)
            sentinel = fixture / "outside-sentinel"
            sentinel.write_text("ordinary fixture\n", encoding="utf-8")
            (web_root / "console.svg").symlink_to(sentinel)

            with self.assertRaisesRegex(SystemExit, "symlink"):
                verifier.reject_unsafe_extracted_entries(root)

            (web_root / "console.svg").unlink()
            os.link(sentinel, web_root / "console.svg")
            with self.assertRaisesRegex(SystemExit, "hard-linked"):
                verifier.reject_unsafe_extracted_entries(root)

            (web_root / "console.svg").unlink()
            (web_root / "console.svg").write_text("ordinary asset\n", encoding="utf-8")
            verifier.reject_unsafe_extracted_entries(root)

    def test_web_ui_verifier_rejects_noncanonical_archive_paths(self):
        verifier = self.load_web_ui_verifier()
        regular_listing = (
            "-rw-r--r--  0 1000 1000 12 Jan 01 00:00 "
            "usr/share/qdrant/web-ui/index.html"
        )
        directory_listing = (
            "drwxrwxrwx  0 1000 1000 0 Jan 01 00:00 usr/share/qdrant/web-ui/"
        )

        for member in (
            "./usr/share/qdrant/web-ui/index.html",
            "usr//share/qdrant/web-ui/index.html",
            "usr/share/./qdrant/web-ui/index.html",
        ):
            with self.subTest(member=member), self.assertRaisesRegex(
                SystemExit, "non-canonical archive member"
            ):
                verifier.validate_archive_members([member], [regular_listing])

        with self.assertRaisesRegex(SystemExit, "non-canonical archive member"):
            verifier.validate_archive_members(
                ["usr/share/qdrant/web-ui"], [directory_listing]
            )
        verifier.validate_archive_members(
            ["usr/share/qdrant/web-ui/"],
            ["drwxr-xr-x  0 0 0 0 Jan 01 00:00 usr/share/qdrant/web-ui/"],
        )

        canonical = "usr/share/qdrant/web-ui/index.html"
        with self.assertRaisesRegex(SystemExit, "duplicate archive member"):
            verifier.validate_archive_members(
                [canonical, canonical],
                [
                    f"-rw-r--r--  0 0 0 12 Jan 01 00:00 {canonical}",
                    f"-rw-r--r--  0 0 0 12 Jan 01 00:00 {canonical}",
                ],
            )

    def test_web_ui_verifier_rejects_every_out_of_root_payload_entry(self):
        verifier = self.load_web_ui_verifier()

        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            root = Path(tempdir)
            (root / ".BUILDINFO").write_text("build info\n", encoding="utf-8")
            (root / ".MTREE").write_text("mtree\n", encoding="utf-8")
            (root / ".PKGINFO").write_text("package info\n", encoding="utf-8")
            web_root = root / "usr/share/qdrant/web-ui"
            web_root.mkdir(parents=True)
            (web_root / "index.html").write_text("dashboard\n", encoding="utf-8")
            license_root = root / "usr/share/licenses/qdrant-web-ui"
            license_root.mkdir(parents=True)
            (license_root / "LICENSE").write_text("license\n", encoding="utf-8")

            verifier.reject_unexpected_extracted_payload(root)

            hidden_file = root / "root/.bashrc"
            hidden_file.parent.mkdir()
            hidden_file.write_text("ordinary fixture\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "unexpected package payload"):
                verifier.reject_unexpected_extracted_payload(root)

            hidden_file.unlink()
            hidden_file.parent.rmdir()
            (root / "etc").mkdir()
            with self.assertRaisesRegex(SystemExit, "unexpected package payload"):
                verifier.reject_unexpected_extracted_payload(root)

    def test_web_ui_verifier_cli_accepts_canonical_archive_metadata_before_payload_checks(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            root = fixture / "root"
            root.mkdir()
            self.write_minimal_web_ui_archive_root(root)
            archive = fixture / "canonical-minimal.tar"
            self.build_web_ui_test_archive(
                root, archive, (".BUILDINFO", ".MTREE", ".PKGINFO")
            )

            result = self.run_web_ui_verifier(archive)

        self.assertNotEqual(result.returncode, 0)
        diagnostic = f"{result.stdout}\n{result.stderr}"
        self.assertIn("missing package payload", diagnostic)
        self.assertNotIn("archive member", diagnostic)

    def test_web_ui_verifier_cli_rejects_noncanonical_member_before_mode_or_owner(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            root = fixture / "root"
            root.mkdir()
            self.write_minimal_web_ui_archive_root(root)
            (root / ".PKGINFO").chmod(0o600)
            archive = fixture / "noncanonical.tar"
            self.build_web_ui_test_archive(
                root,
                archive,
                ("./.PKGINFO",),
                root_identity=False,
            )

            result = self.run_web_ui_verifier(archive)

        self.assertNotEqual(result.returncode, 0)
        diagnostic = f"{result.stdout}\n{result.stderr}"
        self.assertIn(
            "non-canonical archive member is not allowed: ./.PKGINFO",
            diagnostic,
        )

    def test_web_ui_verifier_cli_rejects_file_directory_logical_path_collision(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            file_root = fixture / "file-root"
            file_root.mkdir()
            (file_root / "usr").write_text("ordinary fixture\n", encoding="utf-8")
            (file_root / "usr").chmod(0o644)

            directory_root = fixture / "directory-root"
            directory_root.mkdir()
            self.write_minimal_web_ui_archive_root(directory_root)
            (directory_root / "usr").mkdir(mode=0o755)

            archive = fixture / "logical-path-collision.tar"
            self.build_web_ui_test_archive(file_root, archive, ("usr",))
            subprocess.run(
                [
                    "bsdtar",
                    "--uid",
                    "0",
                    "--gid",
                    "0",
                    "--uname",
                    "root",
                    "--gname",
                    "root",
                    "-rf",
                    str(archive),
                    "-C",
                    str(directory_root),
                    "usr",
                    ".BUILDINFO",
                    ".MTREE",
                    ".PKGINFO",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            result = self.run_web_ui_verifier(archive)

        self.assertNotEqual(result.returncode, 0)
        diagnostic = f"{result.stdout}\n{result.stderr}"
        self.assertIn("duplicate logical archive member: usr", diagnostic)

    def test_web_ui_verifier_cli_requires_numeric_root_ownership(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            root = fixture / "root"
            root.mkdir()
            self.write_minimal_web_ui_archive_root(root)
            archive = fixture / "misleading-root-names.tar"
            subprocess.run(
                [
                    "bsdtar",
                    "--format=pax",
                    "--uid",
                    "1000",
                    "--gid",
                    "1000",
                    "--uname",
                    "root",
                    "--gname",
                    "root",
                    "-cf",
                    str(archive),
                    "-C",
                    str(root),
                    ".BUILDINFO",
                    ".MTREE",
                    ".PKGINFO",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            result = self.run_web_ui_verifier(archive)

        self.assertNotEqual(result.returncode, 0)
        diagnostic = f"{result.stdout}\n{result.stderr}"
        self.assertIn("unexpected numeric archive owner", diagnostic)
        self.assertIn("1000:1000", diagnostic)

    def test_web_ui_verifier_cli_rejects_hidden_payload_outside_the_package_roots(
        self,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            root = fixture / "root"
            root.mkdir()
            self.write_minimal_web_ui_archive_root(root)
            hidden = root / "root/.bashrc"
            hidden.parent.mkdir(mode=0o755)
            hidden.write_text("ordinary fixture\n", encoding="utf-8")
            hidden.chmod(0o644)
            archive = fixture / "hidden-payload.tar"
            self.build_web_ui_test_archive(
                root, archive, (".BUILDINFO", ".MTREE", ".PKGINFO", "root")
            )

            result = self.run_web_ui_verifier(archive)

        self.assertNotEqual(result.returncode, 0)
        diagnostic = f"{result.stdout}\n{result.stderr}"
        self.assertIn("unexpected package payload", diagnostic)
        self.assertIn("root/.bashrc", diagnostic)

    def test_web_ui_verifier_cli_rejects_archive_symlinks_and_hardlinks(self):
        for link_kind in ("symlink", "hardlink"):
            with self.subTest(link_kind=link_kind), tempfile.TemporaryDirectory(
                dir="/tmp"
            ) as tempdir:
                fixture = Path(tempdir)
                root = fixture / "root"
                root.mkdir()
                self.write_minimal_web_ui_archive_root(root)
                assets = root / "usr/share/qdrant/web-ui/assets"
                assets.mkdir(parents=True, mode=0o755)
                if link_kind == "symlink":
                    (assets / "console.svg").symlink_to("outside-sentinel")
                else:
                    source = assets / "source.svg"
                    source.write_text("ordinary fixture\n", encoding="utf-8")
                    source.chmod(0o644)
                    os.link(source, assets / "console.svg")
                archive = fixture / f"{link_kind}.tar"
                self.build_web_ui_test_archive(
                    root,
                    archive,
                    (".BUILDINFO", ".MTREE", ".PKGINFO", "usr"),
                )

                result = self.run_web_ui_verifier(archive)

                self.assertNotEqual(result.returncode, 0)
                diagnostic = f"{result.stdout}\n{result.stderr}"
                self.assertRegex(
                    diagnostic,
                    r"(?:non-regular archive entry|hard-linked extracted package entry)",
                )

    def test_web_ui_verifier_cli_rejects_duplicate_identity_and_transaction_metadata(
        self,
    ):
        cases = {
            "duplicate-pkgname": ("pkgname = hostile-alias", "pkgname"),
            "conflict": ("conflict = filesystem", "conflict"),
            "replaces": ("replaces = filesystem", "replaces"),
        }
        for name, (metadata_line, field) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                dir="/tmp"
            ) as tempdir:
                fixture = Path(tempdir)
                root = fixture / "root"
                root.mkdir()
                self.write_minimal_web_ui_archive_root(
                    root, extra_pkginfo=(metadata_line,)
                )
                archive = fixture / f"{name}.tar"
                self.build_web_ui_test_archive(
                    root, archive, (".BUILDINFO", ".MTREE", ".PKGINFO")
                )

                result = self.run_web_ui_verifier(archive)

                self.assertNotEqual(result.returncode, 0)
                diagnostic = f"{result.stdout}\n{result.stderr}"
                self.assertIn(field, diagnostic)
                self.assertRegex(
                    diagnostic.casefold(), r"metadata|not allowed|duplicate"
                )

    def test_web_ui_verifier_cli_requires_buildinfo_and_mtree(self):
        for omitted in (".BUILDINFO", ".MTREE"):
            with self.subTest(omitted=omitted), tempfile.TemporaryDirectory(
                dir="/tmp"
            ) as tempdir:
                fixture = Path(tempdir)
                root = fixture / "root"
                root.mkdir()
                self.write_minimal_web_ui_archive_root(
                    root, omitted_metadata=(omitted,)
                )
                members = tuple(
                    name
                    for name in (".BUILDINFO", ".MTREE", ".PKGINFO")
                    if (root / name).is_file()
                )
                archive = fixture / f"missing-{omitted[1:].casefold()}.tar"
                self.build_web_ui_test_archive(root, archive, members)

                result = self.run_web_ui_verifier(archive)

                self.assertNotEqual(result.returncode, 0)
                diagnostic = f"{result.stdout}\n{result.stderr}"
                self.assertIn(omitted, diagnostic)
                self.assertRegex(diagnostic.casefold(), r"missing|required")


class QdrantMigrationPlannerContractTests(unittest.TestCase):
    def read_evidence(self, name: str = "manifest.json") -> dict:
        return json.loads((QDRANT_EVIDENCE_DIR / name).read_text(encoding="utf-8"))

    def obligation_results(self, evidence: dict) -> dict[str, dict]:
        return {
            obligation["id"]: obligation
            for obligation in evidence["obligation_results"]
        }

    def run_tool(self, *arguments: str, env: dict[str, str] | None = None):
        return subprocess.run(
            ["zsh", str(MIGRATION_TOOL), *arguments],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def run_sourced_tool(self, program: str, env: dict[str, str] | None = None):
        return subprocess.run(
            [
                "zsh",
                "-f",
                "-c",
                (
                    "export QDRANT_MIGRATION_TEST_SOURCE_ONLY=1; "
                    f"source {shlex.quote(str(MIGRATION_TOOL))}; {program}"
                ),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    def test_fixture_spec_is_deterministic_and_large_enough_for_boundary_queries(self):
        result = self.run_sourced_tool(
            "fixture_points_body; print -r -- __EXPECTED__; "
            "fixture_expected_query_ids_json"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        points_text, expected_text = result.stdout.split("\n__EXPECTED__\n", 1)
        points = json.loads(points_text)["points"]
        expected_query_ids = json.loads(expected_text)

        self.assertEqual(len(points), 1001)
        self.assertEqual(len({point["id"] for point in points}), 1001)
        self.assertEqual(
            expected_query_ids,
            [
                "00000000-0000-4000-8000-000000000001",
                "00000000-0000-4000-8000-000000000002",
            ],
        )
        self.assertEqual([point["id"] for point in points[:2]], expected_query_ids)
        for point in points:
            self.assertIn("indexed_group", point["payload"])
            self.assertIn("unindexed_group", point["payload"])
            self.assertIn("limit_bucket", point["payload"])

    def test_fixture_query_validator_rejects_any_expected_payload_drift(self):
        response = json.dumps(
            {
                "result": {
                    "points": [
                        {
                            "id": "00000000-0000-4000-8000-000000000001",
                            "payload": {
                                "label": "alpha",
                                "generation": 999,
                                "ordinal": 1,
                                "indexed_group": "target",
                                "unindexed_group": "target",
                                "limit_bucket": "excluded",
                            },
                        },
                        {
                            "id": "00000000-0000-4000-8000-000000000002",
                            "payload": {
                                "label": "beta",
                                "generation": 17,
                                "ordinal": 2,
                                "indexed_group": "target",
                                "unindexed_group": "target",
                                "limit_bucket": "bulk",
                            },
                        },
                    ]
                }
            },
            separators=(",", ":"),
        )
        result = self.run_sourced_tool(
            f"api_json() {{ print -r -- {shlex.quote(response)}; }}; "
            "query_fingerprint migration-fixture dense >/dev/null"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("predefined", f"{result.stdout}\n{result.stderr}")

    def test_fixture_schema_identity_is_captured_once_and_compared_exactly(self):
        initial = json.dumps(
            {
                "result": {
                    "payload_schema": {
                        "indexed_group": {"data_type": "keyword", "points": 1001}
                    }
                }
            },
            separators=(",", ":"),
        )
        drifted = json.dumps(
            {
                "result": {
                    "payload_schema": {
                        "indexed_group": {"data_type": "keyword", "points": 1001},
                        "unexpected": {"data_type": "keyword", "points": 1},
                    }
                }
            },
            separators=(",", ":"),
        )
        result = self.run_sourced_tool(
            f"capture_or_compare_fixture_schema {shlex.quote(initial)}; "
            f"if capture_or_compare_fixture_schema {shlex.quote(drifted)}; then "
            "exit 1; fi"
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fixture_runtime_proves_filters_pagination_and_the_exact_query_limit(self):
        evidence = self.read_evidence()
        obligations = self.obligation_results(evidence)

        schema = obligations["fixture_schema_verified"]
        self.assertEqual(schema["status"], "pass")
        self.assertEqual(schema["details"]["point_count"], 1001)
        self.assertEqual(schema["details"]["indexed_payload_fields"], ["indexed_group"])
        self.assertEqual(
            schema["details"]["deliberately_unindexed_payload_fields"],
            ["unindexed_group", "limit_bucket"],
        )

        filters = obligations["fixture_filters_verified"]
        self.assertEqual(filters["status"], "pass")
        self.assertTrue(filters["details"]["exact_results"])
        self.assertEqual(
            filters["details"]["indexed_result_sha256"],
            filters["details"]["unindexed_result_sha256"],
        )

        pagination = obligations["fixture_pagination_verified"]
        self.assertEqual(pagination["status"], "pass")
        self.assertEqual(pagination["details"]["page_size"], 128)
        self.assertEqual(pagination["details"]["pages"], 8)
        self.assertEqual(pagination["details"]["point_count"], 1001)
        self.assertTrue(pagination["details"]["no_duplicates"])
        self.assertTrue(pagination["details"]["complete"])

        query_limit = obligations["fixture_query_limit_verified"]
        self.assertEqual(query_limit["status"], "pass")
        self.assertEqual(query_limit["details"]["configured_max_query_limit"], 1000)
        self.assertEqual(query_limit["details"]["query_limit_1000_result_count"], 1000)
        self.assertTrue(query_limit["details"]["query_limit_1000_succeeded"])
        self.assertTrue(query_limit["details"]["query_limit_1001_rejected"])
        self.assertEqual(query_limit["details"]["rejected_limit"], 1001)
        self.assertTrue(query_limit["details"]["server_remained_ready"])

    def test_post_rejection_readiness_is_an_authenticated_api_observation(self):
        result = self.run_sourced_tool(
            "api_json() { [[ $1 == GET && $2 == /collections ]] || return 2; "
            'print -r -- \'{"status":"ok","result":{"collections":[]}}\'; }; '
            "verify_authenticated_readiness 'after rejected boundary query'; "
            'api_json() { print -r -- \'{"status":"error"}\'; }; '
            "if verify_authenticated_readiness 'after rejected boundary query'; "
            "then exit 1; fi; true"
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_documents_plan_mode_and_the_three_exact_binary_inputs(self):
        result = self.run_tool("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--plan", result.stdout)
        self.assertIn("--execute", result.stdout)
        self.assertIn("--work-root", result.stdout)
        self.assertIn("--http-port", result.stdout)
        self.assertIn("--grpc-port", result.stdout)
        self.assertIn("16333", result.stdout)
        self.assertIn("16334", result.stdout)
        for version in ("1.17.1", "1.18.3", "1.19.0"):
            with self.subTest(version=version):
                self.assertIn(f"--qdrant-{version}", result.stdout)
        self.assertIn("--qdrant-1.17.1-package", result.stdout)

    @unittest.skipUnless(
        Path("/var/cache/pacman/pkg/qdrant-1.17.1-1-x86_64.pkg.tar.zst").is_file()
        and Path("/usr/bin/qdrant").is_file(),
        "the retained exact 1.17.1 package and binary are required",
    )
    def test_retained_1_17_package_identity_and_embedded_payload_are_exact(self):
        package = "/var/cache/pacman/pkg/qdrant-1.17.1-1-x86_64.pkg.tar.zst"
        result = self.run_sourced_tool(
            f"validate_qdrant_1_17_package {shlex.quote(package)} /usr/bin/qdrant; "
            'jq -nc --arg archive "$MIGRATION_QDRANT_1_17_PACKAGE_SHA256" '
            '--arg config "$MIGRATION_QDRANT_1_17_CONFIG_SHA256" '
            '--arg binary "$MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256" '
            "'{archive:$archive,config:$config,binary:$binary}'"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        identity = json.loads(result.stdout)
        self.assertEqual(
            identity["archive"],
            "d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb",
        )
        self.assertEqual(
            identity["binary"],
            "1d9e300802fe1588c6b6aef5167c32f8d215b5d79c07eaf6699ea1a80d92bf72",
        )
        self.assertRegex(identity["config"], r"^[0-9a-f]{64}$")

    def test_retained_1_17_package_binding_never_publishes_build_paths(self):
        retained = self.read_evidence()["inputs"]["retained_baseline"]

        self.assertEqual(retained["package_name_metadata"], "qdrant")
        self.assertEqual(retained["package_version"], "1.17.1-1")
        self.assertEqual(retained["package_arch"], "x86_64")
        self.assertEqual(retained["package_archive_size"], 25531392)
        self.assertEqual(
            retained["package_archive_sha256"],
            "d237ac6b804c7b4ec3f73f8ef57340ebaba62abff7853636286f140c8affd5cb",
        )
        self.assertEqual(retained["package_config_path"], "etc/qdrant/config.yaml")
        self.assertTrue(retained["supplied_binary_byte_identical"])
        self.assertNotIn(".BUILDINFO", json.dumps(retained, sort_keys=True))

    def test_corrected_isolated_native_artifact_tuple_is_pinned(self):
        binaries = {
            binary["version"]: binary for binary in self.read_evidence()["binaries"]
        }
        runbook = (
            REPO_ROOT / "docs/maintainers/qdrant-migration-acceptance.md"
        ).read_text(encoding="utf-8")
        artifacts = (
            (
                "1.18.3",
                "qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst",
                "591f16328fcff0fc0193353a65f4c783afc1d24258ae251d3a8927283276ce9e",
                "26721008",
                "97c16f4582cc0b9f86c7b451d88f7ea8ca56a1e45582168241de7487d31546a7",
                "72145432",
            ),
            (
                "1.19.0",
                "qdrant-1.19.0-1-x86_64.pkg.tar.zst",
                "15f15fe2c0c774691bf3193bc8fc7883fa530c89db697f7c0bcc2720d231b011",
                "28018464",
                "bf24efd92208fab1a8f4769a56158280b458b7a42850095ac875824571005f8c",
                "72134360",
            ),
        )

        for (
            version,
            archive,
            archive_sha,
            archive_size,
            binary_sha,
            binary_size,
        ) in artifacts:
            with self.subTest(version=version):
                self.assertEqual(binaries[version]["binary_sha256"], binary_sha)
                for identity in (
                    archive,
                    archive_sha,
                    archive_size,
                    binary_sha,
                    binary_size,
                ):
                    self.assertIn(identity, runbook)

    def test_exact_candidate_binary_digest_gate_rejects_mismatch(self):
        expected = "97c16f4582cc0b9f86c7b451d88f7ea8ca56a1e45582168241de7487d31546a7"
        actual = "0" * 64
        matching = self.run_sourced_tool(
            f"file_sha256() {{ print -r -- {expected}; }}; "
            f"validate_exact_candidate_binary /tmp/not-read 1.18.3 {expected}; "
            "print -r -- $REPLY"
        )
        mismatch = self.run_sourced_tool(
            f"file_sha256() {{ print -r -- {actual}; }}; "
            f"validate_exact_candidate_binary /tmp/not-read 1.18.3 {expected}"
        )

        self.assertEqual(matching.returncode, 0, matching.stderr)
        self.assertEqual(matching.stdout.strip(), expected)
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("qdrant 1.18.3 binary digest mismatch", mismatch.stderr)
        self.assertIn(actual, mismatch.stderr)
        self.assertIn(expected, mismatch.stderr)

    def test_plan_hashes_a_wrong_candidate_before_executing_it(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            marker = fixture / "wrong-candidate-executed"
            binaries: dict[str, Path] = {}
            for version in ("1.17.1", "1.18.3", "1.19.0"):
                binary = fixture / f"qdrant-{version}"
                marker_write = (
                    f"printf '%s\\n' invoked > {shlex.quote(str(marker))}\n"
                    if version == "1.18.3"
                    else ""
                )
                binary.write_text(
                    "#!/bin/sh\n"
                    + marker_write
                    + f"printf '%s\\n' 'qdrant {version}'\n",
                    encoding="utf-8",
                )
                binary.chmod(0o755)
                binaries[version] = binary

            retained_package = fixture / "qdrant-1.17.1-1-x86_64.pkg.tar.zst"
            retained_package.write_bytes(b"not the retained package")
            result = self.run_tool(
                "--plan",
                "--qdrant-1.17.1-package",
                str(retained_package),
                "--qdrant-1.17.1",
                str(binaries["1.17.1"]),
                "--qdrant-1.18.3",
                str(binaries["1.18.3"]),
                "--qdrant-1.19.0",
                str(binaries["1.19.0"]),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(
                marker.exists(), marker.read_text() if marker.exists() else ""
            )
            self.assertIn(
                "qdrant 1.18.3 binary digest mismatch",
                f"{result.stdout}\n{result.stderr}",
            )

    def test_plan_rejects_missing_required_binary_artifacts(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            result = self.run_tool(
                "--plan",
                "--qdrant-1.17.1",
                f"{tempdir}/missing-1.17.1",
                "--qdrant-1.18.3",
                f"{tempdir}/missing-1.18.3",
                "--qdrant-1.19.0",
                f"{tempdir}/missing-1.19.0",
            )

        self.assertNotEqual(result.returncode, 0)
        diagnostic = f"{result.stdout}\n{result.stderr}"
        for version in ("1.17.1", "1.18.3", "1.19.0"):
            with self.subTest(version=version):
                self.assertIn(version, diagnostic)

    @unittest.skipUnless(
        Path("/var/cache/pacman/pkg/qdrant-1.17.1-1-x86_64.pkg.tar.zst").is_file()
        and Path("/usr/bin/qdrant").is_file(),
        "the retained exact 1.17.1 package and binary are required",
    )
    def test_plan_describes_both_routes_without_service_or_network_mutation(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            binary_paths: dict[str, Path] = {}
            for version in ("1.17.1", "1.18.3", "1.19.0"):
                if version == "1.17.1":
                    binary_paths[version] = Path("/usr/bin/qdrant")
                    continue
                binary = fixture / f"qdrant-{version}"
                binary.write_text(
                    f"#!/bin/sh\nprintf '%s\\n' 'qdrant {version}'\n",
                    encoding="utf-8",
                )
                binary.chmod(0o755)
                binary_paths[version] = binary

            marker = fixture / "unexpected-mutation"
            guard_bin = fixture / "guard-bin"
            guard_bin.mkdir()
            for command in ("curl", "wget", "systemctl", "podman", "docker"):
                guard = guard_bin / command
                guard.write_text(
                    '#!/bin/sh\nprintf \'%s\\n\' "$0 $*" >> "$QDRANT_MUTATION_MARKER"\nexit 97\n',
                    encoding="utf-8",
                )
                guard.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{guard_bin}:/usr/bin"
            environment["QDRANT_MUTATION_MARKER"] = str(marker)
            plan_arguments = (
                "--plan",
                "--qdrant-1.17.1-package",
                "/var/cache/pacman/pkg/qdrant-1.17.1-1-x86_64.pkg.tar.zst",
                "--qdrant-1.17.1",
                str(binary_paths["1.17.1"]),
                "--qdrant-1.18.3",
                str(binary_paths["1.18.3"]),
                "--qdrant-1.19.0",
                str(binary_paths["1.19.0"]),
            )
            result = self.run_sourced_tool(
                "validate_exact_candidate_binary() { "
                'REPLY=$(file_sha256 "$1"); }; main '
                + " ".join(shlex.quote(argument) for argument in plan_arguments),
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(
                marker.exists(), marker.read_text() if marker.exists() else ""
            )

        plan = result.stdout.casefold()
        for requirement in (
            "empty-state",
            "retained-data",
            "1.17.1",
            "1.18.3",
            "1.19.0",
            "cold copy",
            "snapshot",
            "full-storage restore",
            "1.17.1 full-storage snapshot into a separate 1.18.3 target",
            "1.18.3 full-storage snapshot into a separate 1.19.0 target",
            "1001-point fixture",
            "query limit 1000",
            "query limit 1001",
            "four-stage disk and memory fingerprints",
            "alias",
            "stable id",
            "restart",
            "corruption",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, plan)

    def test_execute_rejects_wrong_candidate_bytes_without_executing_or_mutating(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            marker = fixture / "wrong-candidate-executed"
            binary_paths: dict[str, Path] = {}
            for version in ("1.17.1", "1.18.3", "1.19.0"):
                binary = fixture / f"qdrant-{version}"
                marker_write = (
                    f"printf '%s\\n' invoked > {shlex.quote(str(marker))}\n"
                    if version == "1.18.3"
                    else ""
                )
                binary.write_text(
                    "#!/bin/sh\n"
                    + marker_write
                    + f"printf '%s\\n' 'qdrant {version}'\n",
                    encoding="utf-8",
                )
                binary.chmod(0o755)
                binary_paths[version] = binary
            retained_package = fixture / "qdrant-1.17.1-1-x86_64.pkg.tar.zst"
            retained_package.write_bytes(b"not the retained package")
            work_root = fixture / "fresh-work-root"

            result = self.run_tool(
                "--execute",
                "--work-root",
                str(work_root),
                "--qdrant-1.17.1-package",
                str(retained_package),
                "--qdrant-1.17.1",
                str(binary_paths["1.17.1"]),
                "--qdrant-1.18.3",
                str(binary_paths["1.18.3"]),
                "--qdrant-1.19.0",
                str(binary_paths["1.19.0"]),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(work_root.exists())
            self.assertFalse(
                marker.exists(), marker.read_text() if marker.exists() else ""
            )

        diagnostic = f"{result.stdout}\n{result.stderr}"
        self.assertIn("qdrant 1.18.3 binary digest mismatch", diagnostic)

    def test_execute_rejects_unsafe_work_roots_and_ports_before_mutation(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            binary_arguments: list[str] = []
            for version in ("1.17.1", "1.18.3", "1.19.0"):
                binary = fixture / f"qdrant-{version}"
                binary.write_text(
                    f"#!/bin/sh\nprintf '%s\\n' 'qdrant {version}'\n",
                    encoding="utf-8",
                )
                binary.chmod(0o755)
                binary_arguments.extend((f"--qdrant-{version}", str(binary)))

            sentinel = fixture / "keep"
            sentinel.write_text("unchanged\n", encoding="utf-8")
            cases = (
                (
                    "outside-tmp",
                    ("--work-root", "/var/empty/qdrant-migration-contract"),
                    "under /tmp",
                    None,
                ),
                (
                    "existing-root",
                    ("--work-root", str(fixture)),
                    "already exists",
                    None,
                ),
                (
                    "privileged-port",
                    ("--work-root", str(fixture / "low-port"), "--http-port", "80"),
                    "1024",
                    fixture / "low-port",
                ),
                (
                    "colliding-ports",
                    (
                        "--work-root",
                        str(fixture / "same-port"),
                        "--http-port",
                        "16333",
                        "--grpc-port",
                        "16333",
                    ),
                    "distinct",
                    fixture / "same-port",
                ),
            )
            for name, arguments, expected_diagnostic, fresh_root in cases:
                with self.subTest(name=name):
                    result = self.run_tool("--execute", *arguments, *binary_arguments)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(
                        expected_diagnostic,
                        f"{result.stdout}\n{result.stderr}",
                    )
                    if fresh_root is not None:
                        self.assertFalse(fresh_root.exists())
                    self.assertEqual(
                        sentinel.read_text(encoding="utf-8"), "unchanged\n"
                    )

    def test_plan_rejects_execute_only_work_root_and_port_options(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            fixture = Path(tempdir)
            arguments: list[str] = []
            for version in ("1.17.1", "1.18.3", "1.19.0"):
                binary = fixture / f"qdrant-{version}"
                binary.write_text(
                    f"#!/bin/sh\nprintf '%s\\n' 'qdrant {version}'\n",
                    encoding="utf-8",
                )
                binary.chmod(0o755)
                arguments.extend((f"--qdrant-{version}", str(binary)))

            result = self.run_tool(
                "--plan",
                "--work-root",
                str(fixture / "unused"),
                "--http-port",
                "16333",
                *arguments,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((fixture / "unused").exists())
        self.assertIn("--plan", f"{result.stdout}\n{result.stderr}")

    def test_execute_contract_binds_every_g3_snapshot_edge_and_recovery_retry(self):
        evidence = self.read_evidence()
        obligations = self.obligation_results(evidence)
        required = {
            "restore_1_17_same_1_17",
            "restore_1_17_next_1_18",
            "restore_1_18_same_1_18",
            "restore_1_18_next_1_19",
            "restore_1_19_same_1_19",
            "reject_1_17_to_1_18_truncated",
            "retry_1_17_to_1_18_truncated",
            "reject_1_17_to_1_18_checksum",
            "retry_1_17_to_1_18_checksum",
            "reject_1_18_to_1_19_truncated",
            "retry_1_18_to_1_19_truncated",
            "reject_1_18_to_1_19_checksum",
            "retry_1_18_to_1_19_checksum",
        }

        self.assertLessEqual(required, set(evidence["required_g3_obligations"]))
        for obligation in required:
            with self.subTest(obligation=obligation):
                self.assertEqual(obligations[obligation]["status"], "pass")
                details = obligations[obligation]["details"]
                if obligation.startswith("reject_"):
                    self.assertTrue(details["target_was_disposable"])
                elif obligation.startswith("retry_"):
                    self.assertTrue(details["same_target_after_failure"])
                    self.assertTrue(details["retrieval_equivalent"])
                else:
                    self.assertTrue(details["retrieval_equivalent"])

    def test_full_storage_restore_crosses_both_consecutive_minor_boundaries(self):
        outcomes = {
            outcome["id"]: outcome
            for outcome in self.read_evidence()["restore_outcomes"]
        }
        expected_boundaries = {
            "restore_full_1_17_next_1_18": ("1.17.1", "1.18.3"),
            "restore_full_1_18_next_1_19": ("1.18.3", "1.19.0"),
        }

        for obligation, (source, target) in expected_boundaries.items():
            with self.subTest(obligation=obligation):
                outcome = outcomes[obligation]
                self.assertEqual(outcome["status"], "pass")
                self.assertEqual(outcome["details"]["kind"], "full_storage")
                self.assertEqual(outcome["details"]["source_version"], source)
                self.assertEqual(outcome["details"]["target_version"], target)
                self.assertTrue(outcome["details"]["retrieval_equivalent"])
                self.assertTrue(outcome["details"]["restart_verified"])

    def test_execute_requires_a_proven_loopback_only_network_boundary(self):
        evidence = self.read_evidence()
        isolation = evidence["isolation"]

        self.assertEqual(isolation["boundary"], "systemd-run+bwrap")
        self.assertTrue(isolation["environment_cleared"])
        self.assertTrue(isolation["network_namespace"])
        self.assertTrue(isolation["network_namespace_identity_checked"])
        self.assertTrue(isolation["network_namespace_distinct"])
        self.assertTrue(isolation["loopback_bind_allowed"])
        self.assertTrue(isolation["non_loopback_egress_denied"])
        ports = evidence["ports"]
        self.assertEqual(ports["host"], "127.0.0.1")
        self.assertTrue(ports["loopback_only"])
        self.assertIsInstance(ports["http"], int)
        self.assertIsInstance(ports["grpc"], int)
        self.assertGreaterEqual(ports["http"], 1024)
        self.assertLessEqual(ports["http"], 65535)
        self.assertGreaterEqual(ports["grpc"], 1024)
        self.assertLessEqual(ports["grpc"], 65535)
        self.assertNotEqual(ports["http"], ports["grpc"])

    def test_execute_boundary_excludes_host_sensitive_filesystems(self):
        isolation = self.read_evidence()["isolation"]

        self.assertTrue(isolation["user_namespace"])
        self.assertTrue(isolation["mount_namespace"])
        self.assertTrue(isolation["pid_namespace"])
        self.assertTrue(isolation["host_sensitive_roots_absent"])
        self.assertFalse(isolation["host_root_bound"])
        self.assertEqual(
            isolation["runtime_view"],
            [
                "/usr",
                "/proc",
                "/dev",
                "/sys/fs/cgroup",
                "/etc/ssl/certs/ca-certificates.crt",
                "/tmp/<work-root>",
                "/run/qdrant-inputs",
            ],
        )

    def test_execute_boundary_owns_transient_unit_interruption_cleanup(self):
        evidence = self.read_evidence()
        policy = evidence["isolation"]["transient_unit_policy"]
        self.assertEqual(
            policy,
            {
                "runtime_max_sec": 900,
                "timeout_stop_sec": 30,
                "kill_mode": "control-group",
                "send_sigkill": True,
                "wait": True,
                "collect": True,
                "outer_keepalive_supervisor": True,
            },
        )

        transient_cleanup = evidence["cleanup"]["transient_unit"]
        for field in (
            "outer_keepalive_closed",
            "owned_systemd_run_client_reaped",
            "wait_completed",
            "collect_requested",
            "unit_collected",
            "owned_unit_absent",
            "owned_cgroup_absent",
        ):
            with self.subTest(field=field):
                self.assertTrue(transient_cleanup[field])
        self.assertEqual(transient_cleanup["client_exit_status"], 0)

        for signal, expected_status in (("INT", 130), ("TERM", 143)):
            with self.subTest(signal=signal):
                receipt = self.read_evidence(f"interrupt-{signal}.json")
                self.assertEqual(receipt["disposition"], "accepted")
                self.assertEqual(receipt["signal"], signal)
                self.assertEqual(receipt["conventional_exit_status"], expected_status)
                self.assertTrue(receipt["candidate_absent"])
                self.assertTrue(receipt["accepted_manifest_absent"])
                self.assertTrue(receipt["pre_interrupt"]["synchronized_ready_marker"])
                self.assertTrue(
                    receipt["pre_interrupt"]["isolated_http_listener_observed"]
                )
                self.assertTrue(
                    receipt["pre_interrupt"]["isolated_grpc_listener_observed"]
                )
                self.assertEqual(receipt["cleanup"]["status"], "passed")
                for field in (
                    "owned_processes_absent",
                    "owned_listeners_absent",
                    "owned_unit_absent",
                    "owned_cgroup_absent",
                    "collection_wait_completed",
                    "collection_wait_unit_matched",
                    "collection_client_reaped",
                    "collection_cgroup_identity_matched",
                    "collection_receipt_exact",
                ):
                    self.assertTrue(receipt["cleanup"][field])

    def test_transient_collection_receipt_requires_exact_wait_reap_and_cgroup_absence(
        self,
    ):
        absent_cgroup = (
            "/qdrant-migration-contract-cgroup-that-does-not-exist/"
            "qdrant-migration-contract.service"
        )
        ordinary_accepted_state = (
            "MIGRATION_TRANSIENT_WAIT_COMPLETED=1; "
            "MIGRATION_TRANSIENT_WAIT_UNIT=qdrant-migration-contract.service; "
            "MIGRATION_TRANSIENT_WAIT_STATUS=0; "
            "MIGRATION_TRANSIENT_CLIENT_PID=''; "
            "MIGRATION_TRANSIENT_CLIENT_START=''; "
            "MIGRATION_TRANSIENT_CLIENT_EXE=''; "
        )
        accepted = self.run_sourced_tool(
            ordinary_accepted_state + "transient_collection_receipt_is_exact "
            f"qdrant-migration-contract.service {absent_cgroup} 0"
        )
        signal_accepted = self.run_sourced_tool(
            ordinary_accepted_state
            + "MIGRATION_TRANSIENT_WAIT_STATUS=143; "
            + "transient_collection_receipt_is_exact "
            f"qdrant-migration-contract.service {absent_cgroup} 143"
        )
        bad_wait = self.run_sourced_tool(
            ordinary_accepted_state
            + "MIGRATION_TRANSIENT_WAIT_STATUS=1; "
            + "transient_collection_receipt_is_exact "
            f"qdrant-migration-contract.service {absent_cgroup} 0"
        )
        wrong_expected_status = self.run_sourced_tool(
            ordinary_accepted_state
            + "MIGRATION_TRANSIENT_WAIT_STATUS=143; "
            + "transient_collection_receipt_is_exact "
            f"qdrant-migration-contract.service {absent_cgroup} 0"
        )
        bad_identity = self.run_sourced_tool(
            ordinary_accepted_state
            + "MIGRATION_TRANSIENT_WAIT_UNIT=other.service; "
            + "transient_collection_receipt_is_exact "
            f"qdrant-migration-contract.service {absent_cgroup} 0"
        )
        bad_cgroup_identity = self.run_sourced_tool(
            ordinary_accepted_state + "transient_collection_receipt_is_exact "
            "qdrant-migration-contract.service /other.service 0"
        )
        lingering_cgroup = self.run_sourced_tool(
            ordinary_accepted_state + "transient_collection_receipt_is_exact "
            "qdrant-migration-contract.service / 0"
        )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(signal_accepted.returncode, 0, signal_accepted.stderr)
        for result in (
            bad_wait,
            wrong_expected_status,
            bad_identity,
            bad_cgroup_identity,
            lingering_cgroup,
        ):
            self.assertNotEqual(result.returncode, 0)

    def test_interrupt_readiness_marker_requires_live_owned_isolated_surfaces(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            marker = Path(tempdir) / "ready.json"
            invalid = Path(tempdir) / "invalid.json"
            wrong_binary = Path(tempdir) / "wrong-binary.json"
            marker.write_text(
                json.dumps(
                    {
                        "schema": "qdrant-migration-interrupt-readiness/v1",
                        "ready": True,
                        "owned_process_observed": True,
                        "isolated_http_listener_observed": True,
                        "isolated_grpc_listener_observed": True,
                        "isolated_network_namespace_observed": True,
                        "process_identity_sha256": "a" * 64,
                        "network_namespace_sha256": "b" * 64,
                        "binary_sha256": "c" * 64,
                        "ports": {"http": 16333, "grpc": 16334},
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            marker.chmod(0o600)
            invalid.write_text(
                marker.read_text(encoding="utf-8").replace(
                    '"isolated_grpc_listener_observed":true',
                    '"isolated_grpc_listener_observed":false',
                ),
                encoding="utf-8",
            )
            invalid.chmod(0o600)
            wrong_binary.write_text(
                marker.read_text(encoding="utf-8").replace("c" * 64, "d" * 64),
                encoding="utf-8",
            )
            wrong_binary.chmod(0o600)
            accepted = self.run_sourced_tool(
                "MIGRATION_HTTP_PORT=16333; MIGRATION_GRPC_PORT=16334; "
                "MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256=$(printf c%.0s {1..64}); "
                f"validate_interrupt_readiness_marker {shlex.quote(str(marker))}"
            )
            rejected = [
                self.run_sourced_tool(
                    "MIGRATION_HTTP_PORT=16333; MIGRATION_GRPC_PORT=16334; "
                    "MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256=$(printf c%.0s {1..64}); "
                    f"validate_interrupt_readiness_marker {shlex.quote(str(candidate))}"
                )
                for candidate in (invalid, wrong_binary)
            ]

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        for result in rejected:
            self.assertNotEqual(result.returncode, 0)

    def test_interrupt_receipt_validator_rejects_incoherent_exact_target_fields(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            receipt = Path(tempdir) / "receipt.json"
            invalid = Path(tempdir) / "invalid.json"
            globals_program = (
                "MIGRATION_TOOL_SHA256=$(printf a%.0s {1..64}); "
                "MIGRATION_QDRANT_1_17_PACKAGE_SHA256=$(printf b%.0s {1..64}); "
                "MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256=$(printf c%.0s {1..64}); "
                "MIGRATION_QDRANT_1_18_BINARY_SHA256=$(printf d%.0s {1..64}); "
                "MIGRATION_QDRANT_1_19_BINARY_SHA256=$(printf e%.0s {1..64}); "
            )
            accepted_program = globals_program + (
                'fixture_sha=$(text_sha256 "$(fixture_spec_json)"); '
                'target_exe_sha=$(file_sha256 "$(readlink -f /proc/$$/exe)"); '
                'jq -nc --arg tool "$MIGRATION_TOOL_SHA256" '
                '--arg package "$MIGRATION_QDRANT_1_17_PACKAGE_SHA256" '
                '--arg q17 "$MIGRATION_QDRANT_1_17_PACKAGE_BINARY_SHA256" '
                '--arg q18 "$MIGRATION_QDRANT_1_18_BINARY_SHA256" '
                '--arg q19 "$MIGRATION_QDRANT_1_19_BINARY_SHA256" '
                '--arg fixture "$fixture_sha" --arg target_exe "$target_exe_sha" '
                '\'{schema:"qdrant-migration-interrupt-receipt/v1",disposition:"accepted",'
                'signal:"INT",conventional_exit_status:130,'
                'target:{kind:"outer-validation-process",target_identity_sha256:("1"*64),'
                "target_executable_sha256:$target_exe,tool_sha256:$tool},"
                "inputs:{fixture_spec_sha256:$fixture,package_archive_sha256:$package,"
                "binary_sha256:[$q17,$q18,$q19]},candidate_absent:true,"
                "accepted_manifest_absent:true,pre_interrupt:{synchronized_ready_marker:true,"
                'readiness_marker_sha256:("2"*64),owned_process_observed:true,'
                "isolated_http_listener_observed:true,isolated_grpc_listener_observed:true,"
                "isolated_network_namespace_observed:true},"
                'cleanup:{status:"passed",failure:"none",owned_processes_absent:true,'
                "owned_listeners_absent:true,owned_unit_absent:true,owned_cgroup_absent:true,"
                "collection_wait_completed:true,collection_wait_status:143,"
                "collection_wait_status_expected:143,collection_wait_unit_matched:true,"
                "collection_client_reaped:true,collection_cgroup_identity_matched:true,"
                "collection_receipt_exact:true}}' "
                f"> {shlex.quote(str(receipt))}; chmod 600 {shlex.quote(str(receipt))}; "
                f"validate_interrupt_receipt {shlex.quote(str(receipt))} INT 130"
            )
            accepted = self.run_sourced_tool(accepted_program)

            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            valid_receipt = json.loads(receipt.read_text(encoding="utf-8"))
            mutations = (
                ("target-kind", ("target", "kind"), "wrong"),
                (
                    "target-executable",
                    ("target", "target_executable_sha256"),
                    "f" * 64,
                ),
                ("cleanup-failure", ("cleanup", "failure"), "residue"),
                ("cleanup-status", ("cleanup", "status"), "failed"),
                ("collection-wait-status", ("cleanup", "collection_wait_status"), 0),
                (
                    "collection-cgroup-identity",
                    ("cleanup", "collection_cgroup_identity_matched"),
                    False,
                ),
                (
                    "collection-receipt",
                    ("cleanup", "collection_receipt_exact"),
                    False,
                ),
            )
            for name, (parent, field), value in mutations:
                with self.subTest(name=name):
                    candidate = json.loads(json.dumps(valid_receipt))
                    candidate[parent][field] = value
                    invalid.write_text(
                        json.dumps(candidate, separators=(",", ":")),
                        encoding="utf-8",
                    )
                    invalid.chmod(0o600)
                    rejected = self.run_sourced_tool(
                        globals_program
                        + f"validate_interrupt_receipt {shlex.quote(str(invalid))} INT 130"
                    )
                    self.assertNotEqual(rejected.returncode, 0)

    def test_final_acceptance_requires_hash_bound_int_and_term_receipts(self):
        evidence = self.read_evidence()
        receipts = {
            receipt["signal"]: receipt
            for receipt in evidence["inputs"]["interrupt_receipts"]
        }
        self.assertEqual(set(receipts), {"INT", "TERM"})

        for signal, expected_status in (("INT", 130), ("TERM", 143)):
            with self.subTest(signal=signal):
                receipt = receipts[signal]
                durable_receipt = self.read_evidence(receipt["receipt_name"])
                self.assertEqual(receipt["conventional_exit_status"], expected_status)
                self.assertEqual(
                    receipt["receipt_sha256"],
                    hashlib.sha256(
                        (QDRANT_EVIDENCE_DIR / receipt["receipt_name"]).read_bytes()
                    ).hexdigest(),
                )
                for field in (
                    "schema",
                    "disposition",
                    "signal",
                    "conventional_exit_status",
                    "target",
                    "inputs",
                    "pre_interrupt",
                    "candidate_absent",
                    "accepted_manifest_absent",
                    "cleanup",
                ):
                    self.assertEqual(receipt[field], durable_receipt[field])

                self.assertEqual(
                    receipt["target"]["tool_sha256"],
                    evidence["tool"]["sha256"],
                )
                self.assertEqual(
                    receipt["inputs"]["fixture_spec_sha256"],
                    evidence["inputs"]["storage_seed"]["fixture_spec_sha256"],
                )
                self.assertEqual(
                    receipt["inputs"]["binary_sha256"],
                    [binary["binary_sha256"] for binary in evidence["binaries"]],
                )

    def test_candidate_binding_validator_rejects_receipt_artifact_mismatch(self):
        candidate_program = (
            "tool=$(printf a%.0s {1..64}); q17=$(printf b%.0s {1..64}); "
            "q18=$(printf c%.0s {1..64}); q19=$(printf d%.0s {1..64}); "
            "schema=$(printf e%.0s {1..64}); "
            'candidate=$(jq -nc --arg tool "$tool" --arg q17 "$q17" '
            '--arg q18 "$q18" --arg q19 "$q19" --arg schema "$schema" '
            "'{tool:{sha256:$tool},binaries:[{binary_sha256:$q17},{binary_sha256:$q18},"
            "{binary_sha256:$q19}],inputs:{storage_seed:{payload_schema_sha256:$schema},"
            "interrupt_receipts:[{target:{tool_sha256:$tool},inputs:{binary_sha256:[$q17,$q18,$q19]}},"
            "{target:{tool_sha256:$tool},inputs:{binary_sha256:[$q17,$q18,$q19]}}]},"
            'events:[{id:"fixture_schema_verified",details:{schema_sha256:$schema}}]}\'); '
        )
        accepted = self.run_sourced_tool(
            candidate_program + 'validate_candidate_artifact_bindings "$candidate"'
        )
        rejected = self.run_sourced_tool(
            candidate_program + 'mismatch=$(print -r -- "$candidate" | jq -c '
            "'.inputs.interrupt_receipts[1].inputs.binary_sha256[1]=(\"f\"*64)'); "
            'validate_candidate_artifact_bindings "$mismatch"'
        )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotEqual(rejected.returncode, 0)

    def test_final_acceptance_retains_candidate_and_declares_exact_promotion_delta(
        self,
    ):
        accepted = self.read_evidence()
        candidate = self.read_evidence("manifest.runtime-validated.json")
        candidate_path = QDRANT_EVIDENCE_DIR / "manifest.runtime-validated.json"
        candidate_sha256 = hashlib.sha256(candidate_path.read_bytes()).hexdigest()

        self.assertEqual(candidate["disposition"], "runtime_validated")
        self.assertEqual(accepted["disposition"], "accepted")
        self.assertEqual(accepted["runtime_candidate_sha256"], candidate_sha256)
        self.assertEqual(
            accepted["promotion_delta"],
            {
                "candidate_sha256": candidate_sha256,
                "disposition": {
                    "from": "runtime_validated",
                    "to": "accepted",
                },
                "added_paths": [
                    "cleanup.transient_unit",
                    "promotion_delta",
                    "runtime_candidate_sha256",
                ],
                "removed_paths": [],
            },
        )

        promoted = json.loads(json.dumps(accepted))
        promoted["disposition"] = "runtime_validated"
        del promoted["cleanup"]["transient_unit"]
        del promoted["promotion_delta"]
        del promoted["runtime_candidate_sha256"]
        self.assertEqual(promoted, candidate)

    def test_promotion_validator_rejects_any_delta_other_than_the_exact_contract(self):
        promotion_program = (
            "candidate_sha=$(printf a%.0s {1..64}); "
            'accepted=$(jq -nc --arg sha "$candidate_sha" '
            '\'{disposition:"accepted",runtime_candidate_sha256:$sha,'
            "promotion_delta:{candidate_sha256:$sha,"
            'disposition:{from:"runtime_validated",to:"accepted"},'
            'added_paths:["cleanup.transient_unit","promotion_delta",'
            '"runtime_candidate_sha256"],removed_paths:[]}}\'); '
        )
        accepted = self.run_sourced_tool(
            promotion_program + 'validate_promotion_delta "$accepted" "$candidate_sha"'
        )
        rejected = self.run_sourced_tool(
            promotion_program + 'invalid=$(print -r -- "$accepted" | jq -c '
            "'.promotion_delta.removed_paths=[\"inputs\"]'); "
            'validate_promotion_delta "$invalid" "$candidate_sha"'
        )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotEqual(rejected.returncode, 0)

    def test_stop_poll_treats_one_unreadable_identity_sample_as_indeterminate(self):
        program = f"""
export QDRANT_MIGRATION_TEST_SOURCE_ONLY=1
source {shlex.quote(str(MIGRATION_TOOL))}
typeset -ga samples=(running indeterminate running stopped)
typeset -gi sample_index=0
sample_owned_process_state() {{
  (( sample_index += 1 ))
  REPLY=$samples[$sample_index]
}}
sleep() {{ :; }}
wait_for_owned_process_stop 4242 1234 /usr/bin/qdrant 4
[[ $REPLY == stopped && $sample_index == 4 ]]
"""
        result = subprocess.run(
            ["zsh", "-f", "-c", program],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_post_term_poll_does_not_treat_one_mismatch_sample_as_exit(self):
        program = f"""
export QDRANT_MIGRATION_TEST_SOURCE_ONLY=1
source {shlex.quote(str(MIGRATION_TOOL))}
typeset -ga samples=(running mismatch running stopped)
typeset -gi sample_index=0
sample_owned_process_state() {{
  (( sample_index += 1 ))
  REPLY=$samples[$sample_index]
}}
sleep() {{ :; }}
wait_for_owned_process_stop 4242 1234 /usr/bin/qdrant 4
[[ $REPLY == stopped && $sample_index == 4 ]]
"""
        result = subprocess.run(
            ["zsh", "-f", "-c", program],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_process_ownership_uses_start_token_and_exact_executable(self):
        result = self.run_sourced_tool(
            "sleep 10 & pid=$!; "
            "start=$(process_start_token $pid); "
            "exe=$(readlink -f -- /proc/$pid/exe); "
            "sample_owned_process_state $pid $start $exe; "
            "[[ $REPLY == running ]] || exit 10; "
            "sample_owned_process_state $pid $(( start + 1 )) $exe; "
            "[[ $REPLY == mismatch ]] || exit 11; "
            "sample_owned_process_state $pid $start /usr/bin/not-the-owned-process; "
            "[[ $REPLY == mismatch ]] || exit 12; "
            "kill $pid; wait $pid 2>/dev/null || true"
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_execute_emits_a_schema_versioned_comprehensive_evidence_manifest(self):
        evidence = self.read_evidence()

        self.assertEqual(evidence["schema"], "qdrant-migration-evidence/v1")
        self.assertEqual(evidence["disposition"], "accepted")
        for evidence_contract in (
            "binaries",
            "inputs",
            "query_fingerprints",
            "restore_outcomes",
            "rejection_outcomes",
            "resource_pressure",
            "isolation",
            "cleanup",
            "runtime",
        ):
            with self.subTest(evidence_contract=evidence_contract):
                self.assertIn(evidence_contract, evidence)

        self.assertEqual(len(evidence["binaries"]), 3)
        self.assertTrue(evidence["inputs"]["cold_copies"])
        self.assertTrue(evidence["inputs"]["snapshots"])
        self.assertTrue(evidence["runtime"]["invocation"])
        self.assertTrue(evidence["runtime"]["tool_versions"])
        self.assertEqual(
            evidence["tool"]["sha256"],
            hashlib.sha256(MIGRATION_TOOL.read_bytes()).hexdigest(),
        )

        public_record = json.dumps(evidence, sort_keys=True)
        for private_identity in (
            r"/home/",
            r"/root/",
            r"user-[0-9]+",
            r"net:\[[0-9]+\]",
            r"qdrant-migration-[0-9]+",
        ):
            with self.subTest(private_identity=private_identity):
                self.assertNotRegex(public_record, private_identity)

    def test_execute_contract_exercises_disk_and_memory_pressure_recovery(self):
        pressure = {
            result["id"]: result for result in self.read_evidence()["resource_pressure"]
        }

        for resource, threshold, release_below in (
            ("disk", 85, 75),
            ("memory", 80, 70),
        ):
            with self.subTest(resource=resource):
                below = pressure[f"{resource}_below_threshold_write"]
                rejected = pressure[f"{resource}_above_threshold_rejection"]
                recovery = pressure[f"{resource}_release_margin_recovery"]

                self.assertEqual(below["status"], "pass")
                self.assertEqual(
                    below["details"]["configured_threshold_percent"], threshold
                )
                self.assertLess(below["details"]["observed_percent"], threshold)
                self.assertTrue(below["details"]["write_succeeded"])

                self.assertEqual(rejected["status"], "pass")
                self.assertGreaterEqual(
                    rejected["details"]["observed_percent"], threshold
                )
                self.assertEqual(rejected["details"]["http_code"], "507")
                self.assertTrue(rejected["details"]["rejected"])
                self.assertTrue(rejected["details"]["server_remained_ready"])

                self.assertEqual(recovery["status"], "pass")
                self.assertEqual(
                    recovery["details"]["release_below_percent"], release_below
                )
                self.assertLess(recovery["details"]["observed_percent"], release_below)
                self.assertTrue(recovery["details"]["retry_succeeded"])

        memory_rejection = pressure["memory_above_threshold_rejection"]["details"]
        rejected_batch = memory_rejection["rejected_load_batch"]
        self.assertEqual(
            memory_rejection["threshold_trigger"],
            "quota_observed_after_rejected_load",
        )
        self.assertTrue(memory_rejection["load_batch_rejected"])
        self.assertEqual(memory_rejection["load_rejection_http_code"], "507")
        self.assertTrue(memory_rejection["load_rejection_error"])
        self.assertEqual(rejected_batch["ids_count"], 100)
        self.assertEqual(len(rejected_batch["ids"]), 100)
        self.assertTrue(rejected_batch["absent"])

        memory_recovery = pressure["memory_release_margin_recovery"]["details"]
        self.assertEqual(
            memory_recovery["usage_authority"],
            "GET /quotas result.usage.resident_memory_percent",
        )
        for field in (
            "rss_bytes",
            "raw_rss_percent_of_cgroup_limit",
            "cgroup_current_bytes",
            "cgroup_limit_bytes",
        ):
            with self.subTest(field=field):
                self.assertGreater(memory_recovery[field], 0)

    def test_pressure_integrity_binds_four_exact_stages_per_resource(self):
        pressure = {
            result["id"]: result for result in self.read_evidence()["resource_pressure"]
        }
        for resource in ("disk", "memory"):
            with self.subTest(resource=resource):
                integrity = pressure[f"{resource}_integrity_after_pressure"]
                details = integrity["details"]
                self.assertEqual(integrity["status"], "pass")
                self.assertEqual(
                    set(details["stages"]),
                    {
                        "pre_pressure",
                        "post_rejection",
                        "post_release_retry",
                        "post_restart",
                    },
                )
                self.assertEqual(
                    details["stages"]["pre_pressure"],
                    details["stages"]["post_rejection"],
                )
                self.assertEqual(
                    details["stages"]["post_release_retry"],
                    details["stages"]["post_restart"],
                )
                for stage in details["stages"].values():
                    self.assertGreater(stage["point_count"], 0)
                    self.assertTrue(stage["exact_points"])
                    self.assertRegex(stage["points_sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(details["rejected_ids_absent"])
                self.assertTrue(details["rejected_batch_absent"])
                self.assertTrue(details["exact_points"])
                self.assertTrue(details["rejection_preserved_exact_fingerprint"])
                self.assertTrue(details["restart_preserved_exact_fingerprint"])

    def test_pressure_integrity_validator_rejects_stage_or_rejected_id_drift(self):
        fixture_program = (
            'pre=\'{"point_count":1,"exact_points":[{"id":1,'
            '"payload":{"state":"accepted"}}],"points_sha256":'
            '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\'; '
            'retry=\'{"point_count":2,"exact_points":[{"id":1,'
            '"payload":{"state":"accepted"}},{"id":2,'
            '"payload":{"state":"retried"}}],"points_sha256":'
            '"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}\'; '
            'expected=\'[{"id":2,"payload":{"state":"retried"}}]\'; '
            'missing=\'[{"id":3,"payload":{"state":"retried"}}]\'; '
        )
        accepted = self.run_sourced_tool(
            fixture_program
            + 'pressure_integrity_details disk "$expected" "$pre" "$pre" '
            '"$retry" "$retry" >/dev/null'
        )
        unequal_stage = self.run_sourced_tool(
            fixture_program
            + 'pressure_integrity_details disk "$expected" "$pre" "$retry" '
            '"$retry" "$retry" >/dev/null'
        )
        missing_retry_id = self.run_sourced_tool(
            fixture_program
            + 'pressure_integrity_details disk "$missing" "$pre" "$pre" '
            '"$retry" "$retry" >/dev/null'
        )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotEqual(unequal_stage.returncode, 0)
        self.assertNotEqual(missing_retry_id.returncode, 0)

    def test_rejected_memory_load_batch_validator_fails_on_any_applied_id(self):
        accepted = self.run_sourced_tool(
            "api_json() { print -r -- '{\"result\":[]}'; }; "
            "ids='[100000,100001]'; "
            'verify_rejected_batch_absent pressure-memory-load "$ids" >/dev/null'
        )
        partial = self.run_sourced_tool(
            "api_json() { "
            'print -r -- \'{"result":[{"id":100001,"payload":null}]}\'; }; '
            "ids='[100000,100001]'; "
            'verify_rejected_batch_absent pressure-memory-load "$ids" >/dev/null; '
            "true"
        )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotEqual(partial.returncode, 0)

    def test_memory_pressure_rejection_flag_serializes_as_a_json_boolean(self):
        false_result = self.run_sourced_tool("json_boolean_from_integer 0")
        true_result = self.run_sourced_tool("json_boolean_from_integer 1")
        invalid_result = self.run_sourced_tool("json_boolean_from_integer 2")

        self.assertEqual(false_result.returncode, 0, false_result.stderr)
        self.assertEqual(true_result.returncode, 0, true_result.stderr)
        self.assertIs(json.loads(false_result.stdout), False)
        self.assertIs(json.loads(true_result.stdout), True)
        self.assertNotEqual(invalid_result.returncode, 0)

        pressure = {
            result["id"]: result for result in self.read_evidence()["resource_pressure"]
        }
        observed = pressure["memory_above_threshold_rejection"]["details"][
            "load_batch_rejected"
        ]
        self.assertIs(observed, True)

    def test_evidence_gate_validates_each_resource_pressure_obligation(self):
        evidence = self.read_evidence()
        pressure = {result["id"]: result for result in evidence["resource_pressure"]}
        required_pressure = {
            "disk_below_threshold_write",
            "disk_above_threshold_rejection",
            "disk_release_margin_recovery",
            "memory_below_threshold_write",
            "memory_above_threshold_rejection",
            "memory_release_margin_recovery",
            "disk_integrity_after_pressure",
            "memory_integrity_after_pressure",
        }

        self.assertLessEqual(
            required_pressure, set(evidence["required_g3_obligations"])
        )
        self.assertEqual(set(pressure), required_pressure)
        for event_id in required_pressure:
            with self.subTest(event_id=event_id):
                self.assertEqual(pressure[event_id]["status"], "pass")

    def test_strengthened_g3_explicitly_supersedes_the_earlier_final_e_record(self):
        runbook = (
            REPO_ROOT / "docs/maintainers/qdrant-migration-acceptance.md"
        ).read_text(encoding="utf-8")

        self.assertIn("final-e", runbook)
        self.assertIn("superseded", runbook.casefold())
        self.assertRegex(
            runbook,
            r"(?s)final-e.*(?:non-authoritative|cannot satisfy).*strengthened G3",
        )


if __name__ == "__main__":
    unittest.main()
