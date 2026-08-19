import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "packages" / "open-webui"
EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "maintainers"
    / "evidence"
    / "open-webui-offline-package-build-2026-08-19.json"
)
INSPECTION_RECEIPT = (
    REPO_ROOT
    / "docs"
    / "maintainers"
    / "evidence"
    / "open-webui-offline-package-inspection-2026-08-19.json"
)
INSPECTION_TOOL = PACKAGE_DIR / "inspect-open-webui-package.py"
MAINTAINER_NOTE = (
    REPO_ROOT
    / "docs"
    / "maintainers"
    / "open-webui-offline-package-build-2026-08-19.md"
)
HOUSEHOLD_NOTE = REPO_ROOT / "docs" / "maintainers" / "open-webui-household-envelope.md"
CATALOG = REPO_ROOT / "packages" / "README.md"
MEASUREMENT_TOOL = REPO_ROOT / "tools" / "measure_open_webui_household.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measurement_tool():
    spec = importlib.util.spec_from_file_location(
        "measure_open_webui_household_for_package_evidence",
        MEASUREMENT_TOOL,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Open WebUI measurement tool")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class OpenWebUIOfflinePackageEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.receipt = json.loads(INSPECTION_RECEIPT.read_text(encoding="utf-8"))
        cls.tool = load_measurement_tool()

    def test_record_binds_the_reviewed_source_and_offline_inputs(self):
        record = self.record
        self.assertEqual(
            record["schema"],
            "arch-pkgs.open-webui.offline-package-build.v1",
        )
        subject = record["source_subject"]
        self.assertEqual(
            subject["commit"],
            "44223148ba1825c048e06865f458ddd58c05450c",
        )
        self.assertEqual(
            subject["package_tree_oid"], "ec1dfe7e841e9ef3548ff5350399b2ccfbd86d86"
        )
        self.assertEqual(subject["package_version"], "0.11.0-3")
        self.assertEqual(subject["architecture"], "x86_64")
        self.assertEqual(subject["source_entry_count"], 28)
        self.assertEqual(subject["checksum_entry_count"], 28)
        self.assertEqual(
            subject["pkgbuild_sha256"],
            "b160bdffd4a329269f838d4bcd9728dbcf13a44d95d05371ccac80ecd5634510",
        )
        self.assertEqual(
            subject["srcinfo_sha256"],
            "be50a66f3514feee992ba933fc694ee06e76fdf0345d60426634b04fcef0d1b9",
        )

        release = record["build_input_release"]
        self.assertTrue(release["prerelease"])
        self.assertTrue(release["build_input_only"])
        self.assertEqual(
            release["target_commit"],
            "54d8505614da17709cf99ffd7706ba9e957647da",
        )
        self.assertNotEqual(release["target_commit"], subject["commit"])
        self.assertEqual(
            [
                (item["name"], item["size_bytes"], item["sha256"])
                for item in release["assets"]
            ],
            [
                (
                    "open-webui-npm-offline-closure-0.11.0.tar.zst",
                    886706456,
                    "6238b436c6669a311623d97724c6b2ada0e77090d0e5219860acc38c53fb32b1",
                ),
                (
                    "open-webui-python-offline-closure-0.11.0-cp314-x86_64.tar.zst",
                    144877017,
                    "bcd3c5c651fc42e8e5a73a4c81f4b5760e82f6b39eb714caf999700bad4ed27c",
                ),
            ],
        )
        self.assertEqual(release["npm"]["lock_record_count"], 1275)
        self.assertEqual(release["npm"]["unique_tarball_count"], 1233)
        self.assertEqual(release["python"]["wheel_count"], 222)
        self.assertEqual(release["python"]["target"], "CPython 3.14, Linux x86_64")
        self.assertEqual(
            self.record["build"]["node_build_dependency"]["size_bytes"], 15781130
        )

        srcinfo = (PACKAGE_DIR / ".SRCINFO").read_text(encoding="utf-8")
        for asset in release["assets"]:
            self.assertIn(asset["name"], srcinfo)
            self.assertIn(asset["sha256"], srcinfo)

    def test_record_binds_archive_inspection_receipt(self):
        package = self.record["package"]
        binding = self.record["inspection_receipt"]
        receipt = self.receipt
        self.assertEqual(
            binding["path"],
            "docs/maintainers/evidence/"
            "open-webui-offline-package-inspection-2026-08-19.json",
        )
        self.assertEqual(binding["size_bytes"], INSPECTION_RECEIPT.stat().st_size)
        self.assertEqual(binding["sha256"], sha256(INSPECTION_RECEIPT))
        self.assertEqual(
            binding["verifier"], "packages/open-webui/inspect-open-webui-package.py"
        )
        self.assertEqual(binding["verifier_sha256"], sha256(INSPECTION_TOOL))
        self.assertEqual(
            receipt["schema"], "arch-pkgs.open-webui.package-inspection.v1"
        )
        self.tool.assert_public_safe(receipt)
        self.assertEqual(binding["archive_sha256"], receipt["archive"]["sha256"])
        self.assertEqual(
            binding["archive_manifest_sha256"],
            receipt["archive"]["manifest_sha256"],
        )
        self.assertEqual(package["filename"], "open-webui-0.11.0-3-x86_64.pkg.tar.zst")
        self.assertEqual(package["size_bytes"], receipt["archive"]["size_bytes"])
        self.assertEqual(package["sha256"], receipt["archive"]["sha256"])
        self.assertEqual(
            package["installed_size_bytes"], receipt["payload"]["regular_file_bytes"]
        )
        self.assertEqual(
            package["archive_member_count"], receipt["archive"]["member_count"]
        )
        self.assertEqual(
            package["payload_entry_count"], receipt["payload"]["entry_count"]
        )
        self.assertEqual(
            package["symlink_count"], receipt["archive"]["type_counts"]["symlink"]
        )
        self.assertEqual(
            package["frontend_entry_count"], receipt["payload"]["frontend_entry_count"]
        )
        self.assertEqual(
            package["private_distribution_count"],
            receipt["payload"]["private_distribution_count"],
        )
        self.assertEqual(
            package["pyodide"]["file_count"],
            receipt["payload"]["pyodide_payload"]["file_count"],
        )
        self.assertEqual(
            package["pyodide"]["wheel_count"],
            receipt["payload"]["pyodide_wheels"]["count"],
        )
        self.assertEqual(
            package["pyodide"]["total_bytes"],
            receipt["payload"]["pyodide_payload"]["total_bytes"],
        )
        self.assertEqual(
            package["pyodide"]["installed_manifest_sha256"],
            receipt["payload"]["pyodide_payload"]["manifest_sha256"],
        )
        self.assertEqual(
            package["pyodide"]["system_provider_name_overlaps"],
            [
                item["provider"]
                for item in receipt["payload"]["pyodide_wheels"]["provider_exceptions"]
            ],
        )
        self.assertEqual(
            package["pyodide"]["system_provider_name_overlaps"],
            ["numpy", "pandas", "pillow", "scikit-learn", "scipy"],
        )
        self.assertEqual(package["private_distribution_count"], 223)
        self.assertFalse(package["publicly_retained"])

        metadata = package["metadata"]
        self.assertEqual(
            metadata["pkginfo"]["size_bytes"],
            receipt["metadata"][".PKGINFO"]["size_bytes"],
        )
        self.assertEqual(
            metadata["buildinfo"]["size_bytes"],
            receipt["metadata"][".BUILDINFO"]["size_bytes"],
        )
        self.assertEqual(
            metadata["buildinfo"]["build_directory"], receipt["metadata"]["builddir"]
        )
        self.assertEqual(
            metadata["buildinfo"]["start_directory"], receipt["metadata"]["startdir"]
        )
        self.assertEqual(
            metadata["mtree"]["size_bytes"], receipt["metadata"][".MTREE"]["size_bytes"]
        )
        self.assertEqual(
            metadata["mtree"]["decoded_line_count"],
            receipt["metadata"][".MTREE"]["decoded_line_count"],
        )
        self.assertEqual(
            metadata["pkginfo"]["sha256"], receipt["metadata"][".PKGINFO"]["sha256"]
        )
        self.assertEqual(
            metadata["buildinfo"]["sha256"],
            receipt["metadata"][".BUILDINFO"]["sha256"],
        )
        self.assertEqual(
            metadata["mtree"]["sha256"], receipt["metadata"][".MTREE"]["sha256"]
        )
        self.assertEqual(
            metadata["mtree"]["decoded_sha256"],
            receipt["metadata"][".MTREE"]["decoded_sha256"],
        )
        self.assertEqual(
            receipt["metadata"][".BUILDINFO"]["fields"],
            {
                "architecture": self.record["source_subject"]["architecture"],
                "package_version": self.record["source_subject"]["package_version"],
                "pkgbuild_sha256": self.record["source_subject"]["pkgbuild_sha256"],
            },
        )
        self.assertEqual(
            receipt["metadata"][".PKGINFO"]["fields"]["package_version"],
            self.record["source_subject"]["package_version"],
        )
        self.assertEqual(
            receipt["metadata"][".PKGINFO"]["fields"]["architecture"],
            self.record["source_subject"]["architecture"],
        )

        inspected = self.record["payload_inspection"]
        self.assertTrue(inspected["provider_boundary_passed"])
        self.assertTrue(receipt["payload"]["server_provider_boundary"]["passed"])
        self.assertEqual(len(inspected["server_private_distributions_absent"]), 21)
        self.assertEqual(
            inspected["server_private_distributions_absent"],
            receipt["payload"]["server_provider_boundary"]["providers_absent"],
        )
        self.assertEqual(
            inspected["server_private_distributions_absent"],
            (PACKAGE_DIR / "open-webui-system-providers.txt")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
        self.assertEqual(inspected["unexpected_build_material"], [])
        self.assertTrue(receipt["payload"]["installer_metadata_absent"])
        self.assertTrue(receipt["residue"]["passed"])
        self.assertEqual(receipt["residue"]["all_matches"], [])
        self.assertEqual(inspected["critical_files"], receipt["critical_files"])
        self.assertIn("uv install lock", inspected["absence_checks"])
        self.assertIn("dist-info uv cache metadata", inspected["absence_checks"])
        self.assertIn("usr/bin/open-webui", inspected["critical_files"])
        self.assertIn(
            "usr/lib/systemd/system/open-webui.service",
            inspected["critical_files"],
        )
        self.assertIn(
            "usr/lib/open-webui/open-webui-session-epoch-ledger",
            inspected["critical_files"],
        )

    def test_record_keeps_runtime_publication_and_deployment_gates_closed(self):
        disposition = self.record["disposition"]
        self.assertEqual(
            disposition["state"],
            "offline-package-built-inspected-provider-pending",
        )
        self.assertTrue(disposition["offline_package_subgate_passed"])
        self.assertFalse(disposition["integrated_provider_ready"])
        self.assertFalse(disposition["integrated_measurement_complete"])
        self.assertFalse(disposition["publication_eligible"])
        self.assertFalse(disposition["production_deployable"])
        self.assertTrue(
            all(value is False for value in disposition["live_actions"].values())
        )
        self.assertEqual(
            self.record["provider_frontier"]["blocking_issues"],
            [
                "https://github.com/nisavid/arch-strix-halo-pkgs/issues/105",
                "https://github.com/nisavid/arch-strix-halo-pkgs/issues/112",
                "https://github.com/nisavid/arch-strix-halo-pkgs/issues/113",
            ],
        )
        self.assertFalse(self.record["provider_frontier"]["integrated_trial_executed"])

    def test_record_and_notes_are_public_safe_and_digest_bound(self):
        self.tool.assert_public_safe(self.record)
        serialized = json.dumps(self.record, sort_keys=True)
        for forbidden in ("/tmp/", "/home/", "/root/", ".codex", "raw_build_log"):
            self.assertNotIn(forbidden, serialized)

        evidence_digest = sha256(EVIDENCE)
        note = MAINTAINER_NOTE.read_text(encoding="utf-8")
        self.assertIn(evidence_digest, note)
        self.assertIn(EVIDENCE.name, note)
        self.assertIn("not a clean-chroot build", note)
        self.assertIn("not publicly retained", note)
        self.assertIn("integrated measurement was not run", note)

        package_readme = (PACKAGE_DIR / "README.md").read_text(encoding="utf-8")
        catalog = CATALOG.read_text(encoding="utf-8")
        household = HOUSEHOLD_NOTE.read_text(encoding="utf-8")
        self.assertIn(MAINTAINER_NOTE.name, package_readme)
        self.assertIn(MAINTAINER_NOTE.name, catalog)
        self.assertIn(MAINTAINER_NOTE.name, household)
        self.assertIn("deferred", catalog)
        self.assertIn("integrated provider", catalog)


if __name__ == "__main__":
    unittest.main()
