import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "maintainers" / "evidence" / "qdrant-1.19.0-1"
RECORD_FILES = {
    "g0_g1": "g0-g1.json",
    "g2_browser": "g2-browser.json",
    "g2_unit": "g2-unit.json",
    "g3_accepted": "manifest.json",
    "g3_interrupt_int": "interrupt-INT.json",
    "g3_interrupt_term": "interrupt-TERM.json",
    "g3_runtime_candidate": "manifest.runtime-validated.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nested_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested_value in value.items():
            yield from nested_strings(key)
            yield from nested_strings(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from nested_strings(nested_value)


class QdrantEvidenceContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(EVIDENCE_ROOT.is_dir())
        self.documents = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in EVIDENCE_ROOT.glob("*.json")
        }

    def test_durable_evidence_collection_is_complete(self):
        self.assertEqual(
            {path.name for path in EVIDENCE_ROOT.iterdir()},
            {"acceptance.json", *RECORD_FILES.values()},
        )

        acceptance = self.documents["acceptance.json"]
        self.assertEqual(acceptance["schema"], "arch-pkgs.qdrant.acceptance.final3.v1")
        self.assertEqual(set(acceptance["authoritative_records"]), set(RECORD_FILES))
        self.assertNotIn("acceptance.json", json.dumps(acceptance))

        for record_name, file_name in RECORD_FILES.items():
            with self.subTest(record=record_name):
                path = EVIDENCE_ROOT / file_name
                contract = acceptance["authoritative_records"][record_name]
                document = self.documents[file_name]
                self.assertEqual(contract["name"], file_name)
                self.assertEqual(path.stat().st_size, contract["size"])
                self.assertEqual(sha256(path), contract["sha256"])
                self.assertEqual(document["schema"], contract["schema"])
                if "disposition" in contract:
                    self.assertEqual(document["disposition"], contract["disposition"])

    def test_artifact_and_source_cross_bindings_are_exact(self):
        acceptance = self.documents["acceptance.json"]
        g0_g1 = self.documents["g0-g1.json"]
        g2_unit = self.documents["g2-unit.json"]
        g2_browser = self.documents["g2-browser.json"]
        g3 = self.documents["manifest.json"]

        lane_names = {
            "qdrant": "qdrant",
            "qdrant_migration": "qdrant-migration",
            "qdrant_web_ui": "qdrant-web-ui",
        }
        for lane, package_name in lane_names.items():
            with self.subTest(lane=lane):
                expected = acceptance["exact_artifact_tuple"][lane]["package"]
                artifact = g0_g1["artifacts"][lane]
                self.assertEqual(artifact["archive"]["sha256"], expected["sha256"])
                self.assertEqual(artifact["archive"]["size"], expected["size"])
                self.assertEqual(artifact["package_metadata"]["pkgname"], package_name)
                self.assertEqual(
                    artifact["package_metadata"]["pkgver"], expected["version"]
                )
                self.assertEqual(
                    artifact["package_metadata"]["arch"], expected["architecture"]
                )

        expected_qdrant = acceptance["exact_artifact_tuple"]["qdrant"]
        expected_web_ui = acceptance["exact_artifact_tuple"]["qdrant_web_ui"]
        for g2 in (g2_unit, g2_browser):
            for field, value in expected_qdrant["package"].items():
                self.assertEqual(g2["artifacts"]["qdrant"]["package"][field], value)
            for field, value in expected_web_ui["package"].items():
                self.assertEqual(
                    g2["artifacts"]["qdrantWebUi"]["package"][field], value
                )

        self.assertEqual(
            g2_unit["artifacts"]["qdrant"]["installed"]["binarySha256"],
            expected_qdrant["binary"]["sha256"],
        )
        self.assertEqual(
            g2_unit["artifacts"]["qdrant"]["installed"]["sbomSha256"],
            expected_qdrant["sbom"]["sha256"],
        )
        self.assertEqual(
            g2_browser["artifacts"]["qdrant"]["binarySha256"],
            expected_qdrant["binary"]["sha256"],
        )
        self.assertEqual(
            g2_browser["artifacts"]["qdrant"]["sbomSha256"],
            expected_qdrant["sbom"]["sha256"],
        )

        g3_binaries = {
            binary["version"]: binary["binary_sha256"] for binary in g3["binaries"]
        }
        self.assertEqual(
            g3_binaries,
            {
                "1.17.1": acceptance["retained_g3_input"]["binary"]["sha256"],
                "1.18.3": acceptance["exact_artifact_tuple"]["qdrant_migration"][
                    "binary"
                ]["sha256"],
                "1.19.0": expected_qdrant["binary"]["sha256"],
            },
        )
        self.assertEqual(
            g3["inputs"]["retained_baseline"]["package_archive_sha256"],
            acceptance["retained_g3_input"]["package"]["sha256"],
        )
        self.assertEqual(
            g3["inputs"]["retained_baseline"]["package_config_sha256"],
            acceptance["retained_g3_input"]["configuration"]["sha256"],
        )

        for relative_path, contract in acceptance["repository_source"][
            "frozen_files"
        ].items():
            with self.subTest(source=relative_path):
                path = REPO_ROOT / relative_path
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, contract["size"])
                self.assertEqual(sha256(path), contract["sha256"])

    def test_complete_source_inventory_and_review_control_are_current(self):
        acceptance = self.documents["acceptance.json"]
        g0_g1_path = EVIDENCE_ROOT / "g0-g1.json"
        g0_g1 = self.documents["g0-g1.json"]

        self.assertEqual(
            acceptance["repository_source"]["complete_source_inventory_bound_by"],
            sha256(g0_g1_path),
        )
        discovered_files = set()
        for relative_root in g0_g1["repository_source_tree"]["owned_paths"]:
            owned_root = REPO_ROOT / relative_root
            self.assertTrue(owned_root.is_dir())
            for path in owned_root.rglob("*"):
                with self.subTest(owned_entry=str(path.relative_to(REPO_ROOT))):
                    self.assertFalse(path.is_symlink())
                    self.assertTrue(path.is_file() or path.is_dir())
                if path.is_file():
                    discovered_files.add(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(
            set(g0_g1["repository_source_tree"]["owned_files"]),
            discovered_files,
        )
        for relative_path, contract in g0_g1["repository_source_tree"][
            "owned_files"
        ].items():
            with self.subTest(source_inventory=relative_path):
                path = REPO_ROOT / relative_path
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, contract["size"])
                self.assertEqual(sha256(path), contract["sha256"])

        verifier_path = REPO_ROOT / "packages/qdrant-web-ui/verify-package.py"
        verifier_sha256 = sha256(verifier_path)
        review_control = acceptance["repository_source"]["review_control_hardening"]
        web_ui_verification = g0_g1["artifacts"]["qdrant_web_ui"]["verification"]
        self.assertEqual(review_control["web_ui_verifier_sha256"], verifier_sha256)
        self.assertEqual(web_ui_verification["verifier_sha256"], verifier_sha256)
        self.assertTrue(review_control["exact_accepted_artifact_reverified"])
        self.assertTrue(review_control["crafted_symlink_archive_rejected"])
        self.assertTrue(review_control["noncanonical_archive_aliases_rejected"])
        self.assertTrue(review_control["logical_path_collisions_rejected"])
        self.assertTrue(review_control["numeric_root_ownership_enforced"])
        self.assertTrue(review_control["out_of_root_hidden_payload_rejected"])
        self.assertTrue(review_control["hostile_package_metadata_rejected"])
        self.assertTrue(review_control["required_package_metadata_enforced"])
        self.assertTrue(review_control["end_to_end_archive_regressions_passed"])
        self.assertTrue(
            web_ui_verification["exact_artifact_reverified_with_bound_verifier"]
        )
        self.assertTrue(web_ui_verification["crafted_symlink_regression_rejected"])
        self.assertTrue(
            web_ui_verification["noncanonical_archive_alias_regressions_rejected"]
        )
        self.assertTrue(
            web_ui_verification["logical_path_collision_regression_rejected"]
        )
        self.assertTrue(
            web_ui_verification["numeric_root_ownership_regression_rejected"]
        )
        self.assertTrue(
            web_ui_verification["out_of_root_hidden_payload_regression_rejected"]
        )
        self.assertTrue(
            web_ui_verification["hostile_package_metadata_regressions_rejected"]
        )
        self.assertTrue(
            web_ui_verification["required_package_metadata_regressions_passed"]
        )
        self.assertTrue(web_ui_verification["end_to_end_archive_regressions_passed"])

    def test_accepted_build_boundary_and_future_reconstruction_are_distinct(self):
        g0_g1 = self.documents["g0-g1.json"]
        cargo_boundary = g0_g1["source_and_cache_boundary"]["native_locked_cargo_cache"]
        integrity = cargo_boundary["read_only_integrity_check"]
        build = g0_g1["final_builds"]["common"]

        self.assertFalse(cargo_boundary["historical_population_command_retained"])
        self.assertIn(
            "does not claim cache-population reproducibility",
            cargo_boundary["acceptance_scope"],
        )
        self.assertTrue(
            cargo_boundary["source_locks"]["all_match_pinned_source_archives"]
        )
        self.assertEqual(integrity["locked_archives_missing"], 0)
        self.assertEqual(integrity["locked_archive_checksum_mismatches"], 0)
        self.assertTrue(
            all(
                dependency["checkout_head_matches"]
                and dependency["tracked_content_clean"]
                for dependency in integrity["locked_git_dependencies"]
            )
        )
        self.assertEqual(build["network_mode"], "none")
        self.assertFalse(build["outer_cargo_net_offline_environment_set"])
        self.assertFalse(build["cleanbuild_option_used"])

        runbook = (
            REPO_ROOT / "docs/maintainers/qdrant-migration-acceptance.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "The accepted final3 artifact set predates the reconstruction procedure",
            runbook,
        )
        self.assertIn(
            "It does not claim clean-cache replayability",
            runbook,
        )
        self.assertIn(
            "Every reconstruction and future candidate must use the stricter procedure",
            runbook,
        )

    def test_g2_and_g3_promotion_records_reconcile_exactly(self):
        acceptance = self.documents["acceptance.json"]
        browser_path = EVIDENCE_ROOT / "g2-browser.json"
        unit = self.documents["g2-unit.json"]
        candidate = self.documents["manifest.runtime-validated.json"]
        accepted = self.documents["manifest.json"]

        self.assertEqual(unit["browserComplement"]["sha256"], sha256(browser_path))
        self.assertEqual(unit["browserComplement"]["size"], browser_path.stat().st_size)
        self.assertEqual(
            accepted["runtime_candidate_sha256"],
            sha256(EVIDENCE_ROOT / "manifest.runtime-validated.json"),
        )

        normalized = copy.deepcopy(accepted)
        normalized["cleanup"].pop("transient_unit")
        normalized.pop("promotion_delta")
        normalized.pop("runtime_candidate_sha256")
        normalized["disposition"] = "runtime_validated"
        self.assertEqual(normalized, candidate)
        self.assertEqual(
            acceptance["g3_promotion"]["candidate_sha256"],
            sha256(EVIDENCE_ROOT / "manifest.runtime-validated.json"),
        )
        self.assertEqual(
            acceptance["g3_promotion"]["accepted_sha256"],
            sha256(EVIDENCE_ROOT / "manifest.json"),
        )

        embedded_receipts = {
            receipt["signal"]: receipt
            for receipt in accepted["inputs"]["interrupt_receipts"]
        }
        for signal in ("INT", "TERM"):
            with self.subTest(signal=signal):
                file_name = f"interrupt-{signal}.json"
                path = EVIDENCE_ROOT / file_name
                embedded = copy.deepcopy(embedded_receipts[signal])
                self.assertEqual(embedded.pop("receipt_sha256"), sha256(path))
                self.assertEqual(embedded.pop("receipt_name"), file_name)
                self.assertEqual(embedded, self.documents[file_name])

    def test_disposition_stays_deferred_until_g4(self):
        acceptance = self.documents["acceptance.json"]
        disposition = acceptance["disposition"]
        self.assertEqual(disposition["state"], "g0-g3-accepted-g4-pending")
        self.assertFalse(disposition["publication_eligible"])
        self.assertEqual(
            disposition["catalog_lanes"],
            {
                "qdrant": "deferred",
                "qdrant-migration": "deferred",
                "qdrant-web-ui": "deferred",
            },
        )
        self.assertTrue(disposition["fail_closed"])
        self.assertTrue(
            all(not authorized for authorized in disposition["live_actions"].values())
        )
        self.assertEqual(acceptance["gate_results"]["G4"]["status"], "pending")

        catalog = (REPO_ROOT / "packages" / "README.md").read_text(encoding="utf-8")
        for lane in disposition["catalog_lanes"]:
            with self.subTest(catalog_lane=lane):
                pattern = rf"^\| \[`{re.escape(lane)}`\]\({re.escape(lane)}/\).*\| deferred \|.*\| no \|$"
                self.assertRegex(catalog, re.compile(pattern, re.MULTILINE))

    def test_public_records_exclude_private_runtime_material(self):
        acceptance = self.documents["acceptance.json"]
        self.assertTrue(acceptance["privacy"]["public_copy_safe"])
        self.assertEqual(
            acceptance["privacy"]["status"], "passed recursive strict scan"
        )

        forbidden_substrings = (
            "/home/",
            "/root/",
            "/var/cache/pacman/",
            ".codex/",
            "worktrees/",
        )
        private_network = re.compile(
            r"(?<![0-9])(?:10(?:\.[0-9]{1,3}){3}|192\.168(?:\.[0-9]{1,3}){2}|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2})(?![0-9])"
        )
        jwt = re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        )
        api_key_assignment = re.compile(
            r"(?i)(?:api[_ -]?key|QDRANT__SERVICE__API_KEY)\s*[:=]\s*[0-9a-f]{32,}"
        )

        for file_name, document in self.documents.items():
            for value in nested_strings(document):
                with self.subTest(file=file_name, value=value[:80]):
                    self.assertFalse(
                        any(item in value for item in forbidden_substrings)
                    )
                    self.assertIsNone(private_network.search(value))
                    self.assertIsNone(jwt.search(value))
                    self.assertIsNone(api_key_assignment.search(value))
                    for temporary_path in re.findall(r"/tmp/[^\s\"']+", value):
                        self.assertIn("<", temporary_path)


if __name__ == "__main__":
    unittest.main()
