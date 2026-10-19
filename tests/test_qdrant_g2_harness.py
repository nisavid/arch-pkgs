import hashlib
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "maintainers" / "evidence" / "qdrant-1.19.1-1"
HARNESS_ROOT = REPO_ROOT / "tools" / "qdrant_g2_harness"
HISTORICAL_ROOT = REPO_ROOT / "tests" / "fixtures" / "qdrant-g2-accepted"
REVISED_BROWSER_SCRIPTS = {"run-browser.zsh", "browser-namespace.sh", "browser_acceptance.py"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((EVIDENCE_ROOT / name).read_text(encoding="utf-8"))


class QdrantG2HarnessTests(unittest.TestCase):
    """Accepted records still bind retained bytes, not a later harness revision."""

    def test_committed_scripts_match_the_recorded_digests(self):
        browser = load("g2-browser.json")["harness"]
        unit = load("g2-unit.json")["harness"]
        recorded = {
            "run-browser.zsh": browser["hostLauncherSha256"],
            "browser-namespace.sh": browser["namespaceHarnessSha256"],
            "browser_acceptance.py": browser["browserControllerSha256"],
            "browser_seed.py": browser["seedAndTokenGeneratorSha256"],
            "run-unit.zsh": unit["runnerSha256"],
            "unit_api_checks.py": unit["unitApiSha256"],
        }

        self.assertEqual(
            {
                path.name
                for path in HARNESS_ROOT.iterdir()
                if path.name != "__pycache__"
            },
            {*recorded, "grpc_stubs", "browser_payload.py"},
        )
        for name, digest in recorded.items():
            with self.subTest(script=name):
                path = (HISTORICAL_ROOT / (name + ".txt")
                        if name in REVISED_BROWSER_SCRIPTS else HARNESS_ROOT / name)
                self.assertEqual(sha256(path), digest)
        self.assertEqual(
            {path.name for path in HISTORICAL_ROOT.iterdir()},
            {name + ".txt" for name in REVISED_BROWSER_SCRIPTS},
        )

    def test_committed_grpc_stubs_match_the_recorded_listing_digest(self):
        # The unit record binds the stubs as the SHA-256 of their sorted
        # sha256sum-style listing.
        stubs = sorted((HARNESS_ROOT / "grpc_stubs").glob("*.py"))
        listing = "".join(f"{sha256(path)}  {path.name}\n" for path in stubs)

        self.assertEqual(
            hashlib.sha256(listing.encode()).hexdigest(),
            load("g2-unit.json")["harness"]["grpcStubsSha256"],
        )

    def test_maintainer_docs_name_both_launchers(self):
        cutover = (
            REPO_ROOT / "docs" / "maintainers" / "qdrant-production-cutover.md"
        ).read_text(encoding="utf-8")
        for launcher in ("run-unit.zsh", "run-browser.zsh"):
            with self.subTest(launcher=launcher):
                self.assertIn(f"tools/qdrant_g2_harness/{launcher}", cutover)

    def test_revalidation_binds_current_runtime_and_successful_semantic_results(self):
        record = json.loads((EVIDENCE_ROOT.parent / "qdrant-g2-runtime-isolation"
                             / "g2-revalidation.json").read_text())
        self.assertEqual(record["disposition"], "accepted")
        self.assertEqual(record["failedChecks"], [])
        self.assertEqual(set(record["harnessSha256"]), {
            "run-browser.zsh", "browser-namespace.sh", "browser_acceptance.py",
            "browser_seed.py", "browser_payload.py", "run-unit.zsh", "unit_api_checks.py",
        })
        for name, digest in record["harnessSha256"].items():
            with self.subTest(script=name):
                self.assertEqual(sha256(HARNESS_ROOT / name), digest)
        browser = record["browser"]
        self.assertEqual(browser["seed"]["points_upserted"], 200)
        self.assertEqual(browser["result"]["graph"], {"done": True, "ids": 6, "positions": 6})
        self.assertTrue(browser["result"]["cspExact"])
        self.assertTrue(browser["hostAndNamespaceManifestsMatch"])
        self.assertEqual(browser["webUiTreeSha256"], record["unit"]["webUiTreeSha256"])
        self.assertEqual(browser["webUiTreeSha256"],
                         load("g2-browser.json")["artifacts"]["qdrantWebUi"]["installedTree"]["sha256"])
        self.assertEqual(record["unit"]["apiPostRestart"]["collections_listed"], 64)
        self.assertEqual(record["unit"]["cleanupOutside"]["container_exists"], "no")


if __name__ == "__main__":
    unittest.main()
