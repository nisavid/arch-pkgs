import hashlib
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "maintainers" / "evidence" / "qdrant-1.19.1-1"
HARNESS_ROOT = REPO_ROOT / "tools" / "qdrant_g2_harness"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((EVIDENCE_ROOT / name).read_text(encoding="utf-8"))


class QdrantG2HarnessTests(unittest.TestCase):
    """The committed G2 harness is the exact one the accepted G2 records bind."""

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
            {*recorded, "grpc_stubs"},
        )
        for name, digest in recorded.items():
            with self.subTest(script=name):
                self.assertEqual(sha256(HARNESS_ROOT / name), digest)

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


if __name__ == "__main__":
    unittest.main()
