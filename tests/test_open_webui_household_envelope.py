import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_TOOL = REPO_ROOT / "tools" / "measure_open_webui_household.py"
OPEN_WEBUI_011_INIT = (
    REPO_ROOT
    / "tools"
    / "fixtures"
    / "open-webui-household"
    / "open-webui-0.11.0-pristine-init.py"
)
OPEN_WEBUI_011_UDS_PATCH = (
    REPO_ROOT
    / "tools"
    / "fixtures"
    / "open-webui-household"
    / "0001-open-webui-0.11-measurement-uds.patch"
)
EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "maintainers"
    / "evidence"
    / "open-webui-household-envelope-2026-08-18.json"
)
MAINTAINER_NOTE = REPO_ROOT / "docs" / "maintainers" / "open-webui-household-envelope.md"
PROVIDER_FIXTURE = (
    REPO_ROOT / "tools" / "fixtures" / "open-webui-household" / "provider.py"
)


def load_measurement_tool():
    spec = importlib.util.spec_from_file_location(
        "measure_open_webui_household", MEASUREMENT_TOOL
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Open WebUI measurement tool")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class OpenWebUIHouseholdEnvelopeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_measurement_tool()

    def complete_measurement_manifest(self):
        manifest = self.tool.new_evidence_manifest()
        manifest["subject"]["integrated_provider"] = True
        manifest["subject"]["artifacts"] = {
            name: {"size_bytes": 1, "sha256": "a" * 64}
            for name in self.tool.MEASURED_REQUIRED_ARTIFACTS
        }
        for name in self.tool.MEASURED_CONTRACT_OWNED_ARTIFACTS:
            manifest["subject"]["artifacts"][name] = {
                "size_bytes": self.tool.REQUIRED_INPUTS[name]["size_bytes"],
                "sha256": self.tool.REQUIRED_INPUTS[name]["sha256"],
            }
        manifest["subject"]["configs"] = {
            **self.tool.MEASURED_REQUIRED_CONFIG,
            "manifest_sha256": "b" * 64,
        }
        manifest["public_safety"] = dict(self.tool.MEASURED_PUBLIC_SAFETY)
        manifest["evidence_files"] = [
            {
                "role": role,
                "path": f"docs/maintainers/evidence/{role}.json",
                "size_bytes": 1,
                "sha256": "c" * 64,
            }
            for role in sorted(self.tool.MEASURED_REQUIRED_EVIDENCE_ROLES)
        ]
        for obligation in manifest["obligations"]:
            obligation["status"] = "pass"
        manifest["observations"] = self.tool.minimum_complete_observations()
        return manifest

    def test_contract_binds_the_accepted_fresh_native_rag_subject(self):
        contract = self.tool.CONTRACT

        self.assertEqual(contract["schema"], "open-webui-household-envelope-contract/v1")
        self.assertEqual(contract["open_webui"]["version"], "0.11.0")
        self.assertEqual(
            contract["open_webui"]["commit"],
            "f9590b8017199e56d5e953657e6498e3cef1d246",
        )
        self.assertEqual(contract["qdrant"]["version"], "1.19.0")
        self.assertEqual(contract["qdrant"]["dimensions"], 2560)
        self.assertEqual(contract["qdrant"]["distance"], "Cosine")
        self.assertEqual(
            contract["qdrant"]["collections"],
            [
                "open-webui-rag-v1_memories",
                "open-webui-rag-v1_knowledge",
                "open-webui-rag-v1_files",
                "open-webui-rag-v1_web-search",
                "open-webui-rag-v1_hash-based",
            ],
        )
        self.assertEqual(
            contract["providers"]["embedding_model"],
            "zembed-1-Q4_K_M-GGUF-Q4_K_M",
        )
        self.assertEqual(
            contract["providers"]["embedding_artifact"],
            {
                "repository": "Abiray/zembed-1-Q4_K_M-GGUF",
                "revision": "c1fed1b47f407fdf5ceb25d6919ac7e5237151c9",
                "filename": "zembed-1-Q4_K_M.gguf",
                "size_bytes": 2497280960,
                "sha256": "3098f7963ca0563e8b39a55ee09a53697e57e49be5b9082892739bf24e075836",
            },
        )
        self.assertEqual(
            contract["providers"]["embedding_pooling"],
            {
                "strategy": "last-token",
                "llama_cpp_value": "last",
                "gguf_metadata": {"key": "qwen3.pooling_type", "value": 3},
                "required_arguments": ["--embedding", "--pooling", "last"],
            },
        )
        self.assertEqual(
            contract["providers"]["embedding_canary"],
            {
                "dimensions": 2560,
                "minimum_cosine_margin": 0.20,
                "unit_norm_absolute_tolerance": 0.001,
            },
        )
        self.assertEqual(
            contract["providers"]["reranking_model"],
            "zerank-2-GGUF-Q8_0",
        )
        self.assertEqual(
            contract["providers"]["reranking_artifact"],
            {
                "repository": "mradermacher/zerank-2-GGUF",
                "revision": "c3c0d69a75b8dad9f56e99aec416d6aff12b85c7",
                "filename": "zerank-2.Q8_0.gguf",
                "size_bytes": 4280405664,
                "sha256": "7b9ba05a0509151c911582a4d62b14003f6a4fafa0e7ccdf572c7598cde1c100",
            },
        )
        self.assertFalse(
            contract["providers"]["measured_llama_cpp_runtime"][
                "complete_dynamic_closure_bound"
            ]
        )
        self.assertEqual(
            set(self.tool.REQUIRED_INPUTS),
            {
                "open_webui_sdist",
                "open_webui_wheel",
                "qdrant_package",
                "caddy_package",
                "valkey_package",
                "zembed_gguf",
                "zerank_gguf",
                "llama_server_executable",
                "llama_server_impl",
                "provider_fixture",
                "open_webui_pristine_init",
                "open_webui_uds_patch",
            },
        )
        upload_limits = contract["accepted_inputs_not_policy_outputs"]
        self.assertEqual(upload_limits["maximum_file_mib"], 250)
        self.assertNotIn("maximum_file_bytes", upload_limits)
        serialized = json.dumps(contract, sort_keys=True)
        self.assertNotIn("0.9.5", serialized)
        self.assertNotIn("Haystack", serialized)
        self.assertNotIn("Hayhooks", serialized)

    def test_uds_patch_applies_atomically_and_forwards_the_socket_to_uvicorn(self):
        self.assertEqual(
            hashlib.sha256(OPEN_WEBUI_011_INIT.read_bytes()).hexdigest(),
            "11cd2fad929db12c687795239ab3b6af1b5ea6f3ad7363deedfabf9651dd22d4",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            module_path = source_root / "open_webui" / "__init__.py"
            module_path.parent.mkdir()
            shutil.copyfile(OPEN_WEBUI_011_INIT, module_path)

            checked = subprocess.run(
                ["git", "apply", "--check", str(OPEN_WEBUI_011_UDS_PATCH)],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            applied = subprocess.run(
                ["git", "apply", str(OPEN_WEBUI_011_UDS_PATCH)],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            spec = importlib.util.spec_from_file_location(
                "patched_open_webui_init", module_path
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            patched = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(patched)

            package = types.ModuleType("open_webui")
            package.__path__ = []
            main_module = types.ModuleType("open_webui.main")
            env_module = types.ModuleType("open_webui.env")
            env_module.UVICORN_WORKERS = 1
            socket = source_root / "open-webui.sock"
            with (
                mock.patch.dict(
                    sys.modules,
                    {
                        "open_webui": package,
                        "open_webui.main": main_module,
                        "open_webui.env": env_module,
                    },
                ),
                mock.patch.dict(os.environ, {"WEBUI_SECRET_KEY": "fixture-key"}),
                mock.patch.object(patched.uvicorn, "run") as run,
            ):
                patched.serve(uds=socket)

            run.assert_called_once_with(
                "open_webui.main:app",
                forwarded_allow_ips="*",
                workers=1,
                loop="auto",
                uds=str(socket),
            )

    def test_fixture_is_reproducible_and_declares_every_boundary_file(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = self.tool.generate_fixture(Path(first_dir), materialize_heavy=False)
            second = self.tool.generate_fixture(Path(second_dir), materialize_heavy=False)

        self.assertEqual(first, second)
        self.assertEqual(first["schema"], "open-webui-household-fixture/v1")
        self.assertEqual(first["corpus_id"], "open-webui-household-measurement-v1")
        self.assertEqual(first["small_file_count"], 25)
        self.assertEqual(first["accepted_file"]["size"], 250 * 1024 * 1024)
        self.assertEqual(first["rejected_file"]["size"], 250 * 1024 * 1024 + 1)
        self.assertEqual(first["accepted_batch_count"], 25)
        self.assertEqual(first["rejected_batch_count"], 26)
        self.assertEqual(
            first["canonical_fact"], "The brass key opens the seed cabinet."
        )
        self.assertEqual(
            first["canonical_citation"], "Winter Garden Handbook § 3"
        )
        self.assertEqual(len(first["files"]), 29)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in first["files"]))
        self.assertFalse(any(Path(item["name"]).is_absolute() for item in first["files"]))

    def test_provider_canaries_are_dimensioned_finite_and_semantic(self):
        query = self.tool.deterministic_embedding(
            "Which key opens the seed cabinet?", input_type="query"
        )
        matching = self.tool.deterministic_embedding(
            "The brass key opens the seed cabinet.", input_type="document"
        )
        unrelated = self.tool.deterministic_embedding(
            "A tide table lists moon phases.", input_type="document"
        )

        self.assertEqual(len(query), 2560)
        self.assertEqual(len(matching), 2560)
        self.assertEqual(len(unrelated), 2560)
        self.assertTrue(self.tool.embedding_canary_passes(query, matching, unrelated))
        ranking = self.tool.deterministic_rerank(
            "capital of France",
            ["Berlin is in Germany.", "Paris is the capital of France.", "A seed catalog."],
        )
        self.assertEqual([item["index"] for item in ranking], [1, 0, 2])
        self.assertTrue(all(item["score"] == item["score"] for item in ranking))

    def test_embedding_canary_accepts_last_pooling_and_rejects_mean_pooling(self):
        query = [1.0] + [0.0] * 2559
        last_matching = [0.679498783, (1 - 0.679498783**2) ** 0.5] + [0.0] * 2558
        last_unrelated = [0.334305462, (1 - 0.334305462**2) ** 0.5] + [0.0] * 2558
        mean_matching = [0.87017, (1 - 0.87017**2) ** 0.5] + [0.0] * 2558
        mean_unrelated = [0.73245, (1 - 0.73245**2) ** 0.5] + [0.0] * 2558

        self.assertTrue(
            self.tool.embedding_canary_passes(query, last_matching, last_unrelated)
        )
        self.assertFalse(
            self.tool.embedding_canary_passes(query, mean_matching, mean_unrelated)
        )

    def test_plan_only_tool_cannot_emit_a_measured_disposition(self):
        complete = self.complete_measurement_manifest()
        finalized = self.tool.finalize_evidence(complete)
        self.assertEqual(finalized["disposition"], "incomplete")
        self.assertIn(
            "measured finalization is unavailable in plan-only mode",
            finalized["limitations"],
        )

        missing = self.tool.new_evidence_manifest()
        for obligation in missing["obligations"]:
            obligation["status"] = "pass"
        missing["subject"]["integrated_provider"] = False
        missing["observations"] = self.tool.minimum_complete_observations()
        finalized_missing = self.tool.finalize_evidence(missing)
        self.assertEqual(finalized_missing["disposition"], "incomplete")
        self.assertIn("integrated provider", " ".join(finalized_missing["limitations"]))

    def test_measured_disposition_rejects_incomplete_or_malformed_evidence(self):
        missing_obligations = self.complete_measurement_manifest()
        missing_obligations["obligations"] = []
        finalized_missing = self.tool.finalize_evidence(missing_obligations)
        self.assertEqual(finalized_missing["disposition"], "incomplete")
        self.assertIn(
            "obligation contract does not match",
            " ".join(finalized_missing["limitations"]),
        )

        malformed_sample = self.complete_measurement_manifest()
        malformed_sample["observations"]["fresh_start"][0]["duration_seconds"] = -1
        finalized_malformed = self.tool.finalize_evidence(malformed_sample)
        self.assertEqual(finalized_malformed["disposition"], "incomplete")
        self.assertIn(
            "sample contract not met for fresh_start",
            " ".join(finalized_malformed["limitations"]),
        )

        boolean_concurrency = self.complete_measurement_manifest()
        boolean_concurrency["observations"]["query_concurrency_1"][0][
            "concurrency"
        ] = True
        finalized_concurrency = self.tool.finalize_evidence(boolean_concurrency)
        self.assertIn(
            "sample contract not met for query_concurrency_1",
            " ".join(finalized_concurrency["limitations"]),
        )

        wrong_artifact = self.complete_measurement_manifest()
        wrong_artifact["subject"]["artifacts"]["zembed_gguf"]["sha256"] = "d" * 64
        finalized_artifact = self.tool.finalize_evidence(wrong_artifact)
        self.assertEqual(finalized_artifact["disposition"], "incomplete")
        self.assertIn(
            "artifacts differ from the contract-owned inputs",
            " ".join(finalized_artifact["limitations"]),
        )

        malformed_structure = self.complete_measurement_manifest()
        malformed_structure["subject"] = []
        malformed_structure["limitations"] = None
        malformed_structure["evidence_files"] = 3
        finalized_structure = self.tool.finalize_evidence(malformed_structure)
        self.assertEqual(finalized_structure["disposition"], "incomplete")
        self.assertIn(
            "manifest structure is malformed",
            " ".join(finalized_structure["limitations"]),
        )

        malformed_obligation = self.complete_measurement_manifest()
        malformed_obligation["obligations"].append(None)
        finalized_obligation = self.tool.finalize_evidence(malformed_obligation)
        self.assertEqual(finalized_obligation["disposition"], "incomplete")
        self.assertIn(
            "obligation contract does not match",
            " ".join(finalized_obligation["limitations"]),
        )

        for malformed_role in ([], {}):
            with self.subTest(malformed_role=malformed_role):
                malformed_evidence = self.complete_measurement_manifest()
                malformed_evidence["evidence_files"][0]["role"] = malformed_role
                finalized_evidence = self.tool.finalize_evidence(malformed_evidence)
                self.assertEqual(finalized_evidence["disposition"], "incomplete")
                self.assertIn(
                    "digest-bound execution evidence is incomplete",
                    " ".join(finalized_evidence["limitations"]),
                )

    def test_incomplete_input_set_refuses_before_work_root_or_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            subject = temp / "subject.bin"
            subject.write_bytes(b"exact subject bytes")
            work_root = temp / "work"
            result = subprocess.run(
                [
                    sys.executable,
                    str(MEASUREMENT_TOOL),
                    "--plan",
                    "--input",
                    f"subject={subject}",
                    "--work-root",
                    str(work_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contract-owned required set", result.stderr)
        self.assertFalse(work_root.exists())

    def test_contract_owned_digest_and_size_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            subject = Path(temp_dir) / "subject.bin"
            subject.write_bytes(b"exact subject bytes")
            with mock.patch.object(
                self.tool,
                "REQUIRED_INPUTS",
                {
                    "subject": {
                        "size_bytes": subject.stat().st_size,
                        "sha256": "0" * 64,
                    }
                },
            ):
                with self.assertRaisesRegex(ValueError, "digest mismatch"):
                    self.tool._validate_inputs({"subject": str(subject)})

            with mock.patch.object(
                self.tool,
                "REQUIRED_INPUTS",
                {
                    "subject": {
                        "size_bytes": subject.stat().st_size + 1,
                        "sha256": hashlib.sha256(subject.read_bytes()).hexdigest(),
                    }
                },
            ):
                with self.assertRaisesRegex(ValueError, "size mismatch"):
                    self.tool._validate_inputs({"subject": str(subject)})

    def test_provider_fixture_required_input_matches_checked_in_bytes(self):
        provider_record = self.tool.REQUIRED_INPUTS["provider_fixture"]
        self.assertEqual(provider_record["size_bytes"], PROVIDER_FIXTURE.stat().st_size)
        self.assertEqual(
            provider_record["sha256"],
            hashlib.sha256(PROVIDER_FIXTURE.read_bytes()).hexdigest(),
        )

    def test_unimplemented_execute_mode_is_not_exposed_or_mutating(self):
        help_result = subprocess.run(
            [sys.executable, str(MEASUREMENT_TOOL), "--help"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertNotIn("--execute", help_result.stdout)
        self.assertNotIn("--execution-marker", help_result.stdout)
        self.assertNotIn("--expect-sha256", help_result.stdout)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            subject = temp / "subject.bin"
            subject.write_bytes(b"exact subject bytes")
            work_root = temp / "work"
            result = subprocess.run(
                [
                    sys.executable,
                    str(MEASUREMENT_TOOL),
                    "--plan",
                    "--execute",
                    "--input",
                    f"subject={subject}",
                    "--work-root",
                    str(work_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments: --execute", result.stderr)
        self.assertFalse(work_root.exists())

    def test_public_evidence_rejects_paths_addresses_and_secret_material(self):
        safe = {
            "identity": "admin@household.invalid",
            "topology": "loopback provider and Unix socket",
            "fingerprint": hashlib.sha256(b"not-a-secret-value").hexdigest(),
        }
        self.tool.assert_public_safe(safe)

        for value in (
            "/home/example/private",
            "/root/private",
            "192.168.1.50",
            "fd12:3456:789a::1",
            "::1",
            "desktop-ivan.lan",
            "Bearer abc",
            "Bearer secret",
            "bearer session remains valid",
            "Bearer super-secret",
            "-----BEGIN PRIVATE KEY-----",
            "Cookie: session=secret",
            "token=plain-text-secret",
            "person@example.com",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.tool.assert_public_safe({"value": value})

        with self.assertRaises(ValueError):
            self.tool.assert_public_safe({"api_key": "plain-text-secret"})
        with self.assertRaises(ValueError):
            self.tool.assert_public_safe({"access_token": "plain-text-secret"})
        with self.assertRaises(ValueError):
            self.tool.assert_public_safe({"cookie": "session=plain-text-secret"})
        with self.assertRaises(ValueError):
            self.tool.assert_public_safe({"set_cookie": "session=plain-text-secret"})

    def test_dated_evidence_is_public_safe_truthful_and_incomplete(self):
        evidence = json.loads(EVIDENCE.read_text())

        self.assertEqual(evidence["schema"], "open-webui-household-envelope/v1")
        self.assertEqual(evidence["disposition"], "incomplete")
        self.assertFalse(evidence["subject"]["integrated_provider"])
        self.assertFalse(evidence["subject"]["publication_eligible"])
        self.assertFalse(evidence["subject"]["production_deployable"])
        self.tool.assert_public_safe(evidence)
        serialized = json.dumps(evidence, separators=(",", ":"))
        for forbidden in (
            "Bearer ",
            "BEGIN PRIVATE KEY",
            "BEGIN CERTIFICATE",
            ".codex",
            "worktrees",
            "fd00:",
            "fe80:",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

        pooling = evidence["protocol"]["embedding_pooling"]
        self.assertEqual(pooling["llama_cpp_value"], "last")
        self.assertEqual(pooling["gguf_metadata"], {"key": "qwen3.pooling_type", "value": 3})
        self.assertNotIn('"pooling":"mean"', serialized)
        self.assertEqual(
            evidence["subject"]["artifacts"]["zembed"]["sha256"],
            "3098f7963ca0563e8b39a55ee09a53697e57e49be5b9082892739bf24e075836",
        )

        query = evidence["observations"]["query_concurrency_1"]
        self.assertTrue(query["aggregate_only"])
        self.assertEqual(query["count"], 30)
        self.assertNotIn("samples", query)
        obligations = evidence["obligations"]
        by_id = {item["id"]: item for item in obligations}
        self.assertEqual(len(by_id), len(obligations))
        self.assertEqual(set(by_id), set(self.tool.REQUIRED_OBLIGATIONS))
        self.assertEqual(by_id["reranker_failure_isolates_rag"]["status"], "fail")
        self.assertEqual(by_id["old_session_rejection"]["status"], "fail")
        self.assertEqual(by_id["runtime_quiescence_cleanup"]["status"], "pass")
        for obligation in (
            "scoped_qdrant_runtime_authority",
            "reranking_semantic_canary",
            "private_owner_retrieval",
            "explicit_sharing_and_revocation",
            "anonymous_denial_before_lookup",
        ):
            with self.subTest(obligation=obligation):
                self.assertEqual(by_id[obligation]["status"], "inconclusive")
        self.assertFalse(evidence["provenance"]["durable_execution_recipe"])
        self.assertFalse(evidence["provenance"]["digest_bound_raw_samples"])
        self.assertFalse(evidence["cleanup"]["disposable_data_removed"])
        self.assertFalse(
            evidence["observations"]["quiesced_backup"][
                "complete_credential_sources_included"
            ]
        )
        self.assertFalse(
            evidence["subject"]["artifacts"]["llama_cpp_observed_runtime"][
                "complete_dynamic_closure_bound"
            ]
        )
        self.assertEqual(
            evidence["observations"]["file_count_boundary"]["enforcement"],
            "frontend-only",
        )
        for item in evidence["evidence_files"]:
            path = REPO_ROOT / item["path"]
            self.assertEqual(path.stat().st_size, item["size_bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])

    def test_maintainer_note_binds_the_dated_evidence_digest(self):
        digest = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
        note = MAINTAINER_NOTE.read_text()

        self.assertIn(digest, note)
        self.assertIn(
            "docs/maintainers/open-webui-household-envelope.md",
            (REPO_ROOT / "packages" / "open-webui" / "README.md").read_text(),
        )


if __name__ == "__main__":
    unittest.main()
