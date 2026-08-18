import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "tools" / "check_repo_consistency.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "repository-consistency.yml"
CHATGPT_RETIREMENT_EVIDENCE_RELATIVE = (
    "docs/maintainers/evidence/chatgpt-fallback-baseline-2026-08-16.json"
)
CHATGPT_RETIREMENT_EVIDENCE = REPO_ROOT / CHATGPT_RETIREMENT_EVIDENCE_RELATIVE


class RepositoryConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name) / "repo"
        self.bin_dir = Path(self.tempdir.name) / "bin"
        self.repo.mkdir()
        self.bin_dir.mkdir()

        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.write(
            "packages/example/PKGBUILD",
            "pkgname=example\npkgver=1.2.3\npkgrel=4\narch=('any')\n",
        )
        srcinfo = textwrap.dedent(
            """\
            pkgbase = example
            \tpkgver = 1.2.3
            \tpkgrel = 4
            \tarch = any

            pkgname = example
            """
        )
        self.write("packages/example/.SRCINFO", srcinfo)
        self.write("packages/example/.generated-srcinfo", srcinfo)
        self.write(
            "packages/example/README.md",
            textwrap.dedent(
                """\
                # example

                ## Maintenance Baseline

                - `authoritative_reference`: upstream example release
                - `advisory_references`: Arch package guidelines
                - `divergence_notes`: packages the upstream source without patches
                - `update_notes`: verify the source and regenerate `.SRCINFO`
                """
            ),
        )
        self.write(
            "packages/README.md",
            textwrap.dedent(
                """\
                # Package Catalog

                | Directory | Package | Packaged version | Disposition | Reviewed target or cursor | Review date | Acceptance state or next gate | Publication eligible |
                | --- | --- | --- | --- | --- | --- | --- | --- |
                | [`example`](example/) | `example` | 1.2.3-4 | accepted-current | 1.2.3 | 2026-08-17 | Fixture acceptance passed | yes |
                """
            ),
        )
        self.write("tools/example.zsh", "#!/usr/bin/env zsh\nprint -r -- ok\n")
        self.write(
            CHATGPT_RETIREMENT_EVIDENCE_RELATIVE,
            CHATGPT_RETIREMENT_EVIDENCE.read_text(encoding="utf-8"),
        )
        self.write("tests/__init__.py", "")
        self.write("tests/test_fixture.py", "import unittest\n")
        self.write(
            ".github/workflows/example.yml",
            textwrap.dedent(
                """\
                name: Example
                jobs:
                  example:
                    steps:
                      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd
                """
            ),
        )
        makepkg = self.bin_dir / "makepkg"
        makepkg.write_text(
            "#!/bin/sh\n"
            "test \"$1\" = --printsrcinfo || exit 64\n"
            "cat .generated-srcinfo\n",
            encoding="utf-8",
        )
        makepkg.chmod(0o755)
        subprocess.run(
            [
                "git",
                "add",
                "packages/example/PKGBUILD",
                "packages/example/.SRCINFO",
                "packages/example/README.md",
                "packages/README.md",
                "tools/example.zsh",
                "tests/__init__.py",
                "tests/test_fixture.py",
                ".github/workflows/example.yml",
            ],
            cwd=self.repo,
            check=True,
        )

    def write(self, relative_path: str, content: str) -> None:
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_checker(
        self, *arguments: str, skip_tests: bool = True
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin_dir}:{environment['PATH']}"
        command = [sys.executable, str(CHECKER), "--repo", str(self.repo)]
        if skip_tests:
            command.append("--skip-tests")
        command.extend(arguments)
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_conforming_repository_passes(self):
        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repository consistency: passed", result.stdout)

    def test_package_lane_requires_srcinfo(self):
        (self.repo / "packages/example/.SRCINFO").unlink()

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/example: PKGBUILD and .SRCINFO must both exist",
            result.stderr,
        )

    def test_srcinfo_must_match_makepkg_output(self):
        srcinfo = self.repo / "packages/example/.SRCINFO"
        srcinfo.write_text(
            srcinfo.read_text(encoding="utf-8").replace("pkgver = 1.2.3", "pkgver = 9.9.9"),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/example/.SRCINFO does not match makepkg --printsrcinfo",
            result.stderr,
        )

    def test_srcinfo_identity_requires_named_version_fields(self):
        for name in (".SRCINFO", ".generated-srcinfo"):
            srcinfo = self.repo / "packages/example" / name
            srcinfo.write_text(
                srcinfo.read_text(encoding="utf-8").replace(
                    "\tpkgver = 1.2.3\n", ""
                ),
                encoding="utf-8",
            )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/example/.SRCINFO: required field pkgver must appear exactly once and be nonempty",
            result.stderr,
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_retired_chatgpt_package_lane_cannot_be_reintroduced(self):
        self.write("packages/chatgpt/README.md", "# retired lane\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/chatgpt: retired package lane must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_package_lane_cannot_hide_as_a_directory_symlink(self):
        external_lane = Path(self.tempdir.name) / "retired-package"
        external_lane.mkdir()
        retired_lanes = {
            "chatgpt": "retired package lane must remain absent",
            "codex-app": "retired ChatGPT producer lane must remain absent",
            "codex-desktop": "retired ChatGPT producer lane must remain absent",
            "chatgpt-desktop-bin": "local ChatGPT package lane must remain absent",
        }
        for name in retired_lanes:
            lane_path = self.repo / f"packages/{name}"
            lane_path.parent.mkdir(parents=True, exist_ok=True)
            lane_path.symlink_to(external_lane, target_is_directory=True)

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        for name, message in retired_lanes.items():
            self.assertIn(f"packages/{name}: {message}", result.stderr)

    def test_retired_legacy_producer_lane_cannot_be_reintroduced(self):
        self.write("packages/codex-app/PKGBUILD", "pkgname=codex-app\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/codex-app: retired ChatGPT producer lane must remain absent",
            result.stderr,
        )

    def test_official_chatgpt_package_lane_cannot_be_reintroduced(self):
        self.write(
            "packages/chatgpt-desktop-bin/PKGBUILD",
            "pkgname=chatgpt-desktop-bin\n",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/chatgpt-desktop-bin: local ChatGPT package lane must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_catalog_row_cannot_be_reintroduced(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            + "| [`chatgpt`](chatgpt/) | `chatgpt` | 1.0-1 | retired | historical | 2026-08-18 | Retired | no |\n",
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: retired ChatGPT catalog row must remain absent: chatgpt",
            result.stderr,
        )

    def test_official_chatgpt_catalog_row_cannot_be_reintroduced(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            + "| [`chatgpt-desktop-bin`](chatgpt-desktop-bin/) | `chatgpt-desktop-bin` | 1.0-1 | retired | external | 2026-08-18 | Settled external producer | no |\n",
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: local ChatGPT package catalog row must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_package_identity_cannot_hide_behind_an_alias(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            + "| [`desktop-app`](desktop-app/) | `chatgpt` | 1.0-1 | accepted-current | current | 2026-08-18 | Accepted | yes |\n",
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: retired ChatGPT producer identity must remain absent: chatgpt",
            result.stderr,
        )

    def test_retired_chatgpt_ingest_helper_cannot_be_reintroduced(self):
        self.write("tools/ingest_chatgpt.zsh", "#!/usr/bin/env zsh\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/ingest_chatgpt.zsh: retired ingest helper must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_ingest_helper_cannot_be_renamed(self):
        self.write("tools/ingest_chatgpt_linux.zsh", "#!/usr/bin/env zsh\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/ingest_chatgpt_linux.zsh: retired ChatGPT ingest helper must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_ingest_helper_cannot_change_language(self):
        self.write("tools/ingest_chatgpt.py", "print('retired')\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/ingest_chatgpt.py: retired ChatGPT ingest helper must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_ingest_helper_cannot_reverse_reserved_words(self):
        self.write("tools/chatgpt_ingest.zsh", "#!/usr/bin/env zsh\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/chatgpt_ingest.zsh: retired ChatGPT ingest helper must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_ingest_helper_cannot_hide_in_nested_paths(self):
        retired_helpers = (
            "tools/chatgpt-ingest/main.py",
            "tools/chatgpt/ingest.zsh",
            "tools/codex/desktop/ingest.py",
        )
        for relative in retired_helpers:
            self.write(relative, "print('retired')\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        for relative in retired_helpers:
            self.assertIn(
                f"{relative}: retired ChatGPT ingest helper must remain absent",
                result.stderr,
            )

    def test_retired_chatgpt_ingest_helper_cannot_hide_as_a_directory_symlink(self):
        external_helper = Path(self.tempdir.name) / "retired-helper"
        external_helper.mkdir()
        (external_helper / "main.py").write_text("print('retired')\n", encoding="utf-8")
        helper_path = self.repo / "tools/chatgpt-ingest"
        helper_path.parent.mkdir(parents=True, exist_ok=True)
        helper_path.symlink_to(external_helper, target_is_directory=True)

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/chatgpt-ingest: retired ChatGPT ingest helper must remain absent",
            result.stderr,
        )

    def test_retired_chatgpt_ingest_helper_cannot_hide_behind_identity_symlink(self):
        external_helper = Path(self.tempdir.name) / "retired-helper"
        external_helper.mkdir()
        (external_helper / "ingest.zsh").write_text(
            "#!/usr/bin/env zsh\n", encoding="utf-8"
        )
        helper_path = self.repo / "tools/chatgpt"
        helper_path.parent.mkdir(parents=True, exist_ok=True)
        helper_path.symlink_to(external_helper, target_is_directory=True)

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/chatgpt: retired ChatGPT ingest helper must remain absent",
            result.stderr,
        )

    def test_retired_codex_app_ingest_helper_cannot_be_reintroduced(self):
        self.write("tools/codex-app-ingest.py", "print('retired')\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/codex-app-ingest.py: retired ChatGPT ingest helper must remain absent",
            result.stderr,
        )

    def test_retired_codex_desktop_ingest_helper_cannot_be_reintroduced(self):
        self.write("tools/ingest-codex-desktop.sh", "#!/bin/sh\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "tools/ingest-codex-desktop.sh: retired ChatGPT ingest helper must remain absent",
            result.stderr,
        )

    def test_chatgpt_retirement_evidence_must_remain_present(self):
        (self.repo / CHATGPT_RETIREMENT_EVIDENCE_RELATIVE).unlink()

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            f"{CHATGPT_RETIREMENT_EVIDENCE_RELATIVE}: exact historical evidence is missing",
            result.stderr,
        )

    def test_chatgpt_retirement_evidence_must_not_be_a_symlink(self):
        evidence = self.repo / CHATGPT_RETIREMENT_EVIDENCE_RELATIVE
        external_evidence = Path(self.tempdir.name) / "retirement-evidence.json"
        external_evidence.write_bytes(evidence.read_bytes())
        evidence.unlink()
        evidence.symlink_to(external_evidence)

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            f"{CHATGPT_RETIREMENT_EVIDENCE_RELATIVE}: "
            "historical evidence must be a regular file",
            result.stderr,
        )

    def test_chatgpt_retirement_evidence_parent_must_not_be_a_symlink(self):
        evidence = self.repo / CHATGPT_RETIREMENT_EVIDENCE_RELATIVE
        external_parent = Path(self.tempdir.name) / "retirement-evidence-parent"
        evidence.parent.rename(external_parent)
        evidence.parent.symlink_to(external_parent, target_is_directory=True)

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            f"{CHATGPT_RETIREMENT_EVIDENCE_RELATIVE}: "
            "historical evidence must be a regular file inside the checkout",
            result.stderr,
        )

    def test_chatgpt_retirement_evidence_digest_must_remain_exact(self):
        evidence = self.repo / CHATGPT_RETIREMENT_EVIDENCE_RELATIVE
        evidence.write_text(
            evidence.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            f"{CHATGPT_RETIREMENT_EVIDENCE_RELATIVE}: "
            "historical evidence digest does not match the retained baseline",
            result.stderr,
        )

    def test_catalog_must_cover_each_package_lane_once(self):
        self.write(
            "packages/README.md",
            "# Package Catalog\n\nNo package rows are present.\n",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: package lane example must appear exactly once; found 0",
            result.stderr,
        )

    def test_empty_legacy_directory_is_not_a_package_lane(self):
        (self.repo / "packages/codex-app").mkdir()

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_catalog_rejects_duplicate_package_lane(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            + "| [`example`](example/) | `example` | 1.2.3-4 | accepted-current | 1.2.3 | 2026-08-17 | Fixture acceptance passed | yes |\n",
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: package lane example must appear exactly once; found 2",
            result.stderr,
        )

    def test_catalog_version_must_match_srcinfo(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                "| `example` | 1.2.3-4 |", "| `example` | 9.9.9-1 |"
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: example packaged version 9.9.9-1 does not match 1.2.3-4",
            result.stderr,
        )

    def test_catalog_package_names_must_match_srcinfo(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                "| `example` | 1.2.3-4 |", "| `wrong-name` | 1.2.3-4 |"
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: example package names ['wrong-name'] do not match ['example']",
            result.stderr,
        )

    def test_catalog_rejects_unknown_disposition(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                "| accepted-current |", "| current |"
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: example has invalid disposition current",
            result.stderr,
        )

    def test_catalog_requires_iso_review_date(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                "| 2026-08-17 |", "| 20260817 |"
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: example review date must be ISO YYYY-MM-DD",
            result.stderr,
        )

    def test_catalog_requires_publication_eligibility(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                "| yes |", "| maybe |"
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: example publication eligibility must be yes or no",
            result.stderr,
        )

    def test_catalog_requires_accepted_lane_to_be_publication_eligible(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace("| yes |", "| no |"),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: example accepted-current lane must be publication eligible",
            result.stderr,
        )

    def test_catalog_requires_retired_lane_to_be_excluded(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                "| accepted-current |", "| retired |"
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/README.md: example retired lane must not be publication eligible",
            result.stderr,
        )

    def test_catalog_allows_deferred_lane_with_previous_publishable_version(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            .replace("| accepted-current |", "| deferred |")
            .replace(
                "| Fixture acceptance passed |",
                "| Previously accepted 1.2.3 remains publishable |",
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_retained_lane_requires_complete_baseline(self):
        readme = self.repo / "packages/example/README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "- `update_notes`: verify the source and regenerate `.SRCINFO`\n", ""
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/example/README.md: required baseline field update_notes must appear exactly once and be nonempty",
            result.stderr,
        )

    def test_retained_lane_requires_one_exact_baseline_section(self):
        readme = self.repo / "packages/example/README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "## Maintenance Baseline", "## Maintenance baseline"
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/example/README.md: required section ## Maintenance Baseline must appear exactly once",
            result.stderr,
        )

    def test_blank_baseline_field_does_not_borrow_a_later_nested_bullet(self):
        readme = self.repo / "packages/example/README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "- `authoritative_reference`: upstream example release\n",
                "- `authoritative_reference`:\n"
                "- unrelated note\n"
                "  nested continuation\n",
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/example/README.md: required baseline field authoritative_reference must appear exactly once and be nonempty",
            result.stderr,
        )

    def test_blank_baseline_field_does_not_borrow_an_alternate_list(self):
        readme = self.repo / "packages/example/README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "- `authoritative_reference`: upstream example release\n",
                "- `authoritative_reference`:\n"
                "* unrelated note\n"
                "  nested continuation\n",
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/example/README.md: required baseline field authoritative_reference must appear exactly once and be nonempty",
            result.stderr,
        )

    def test_retired_lane_is_exempt_from_baseline_fields(self):
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            .replace("| accepted-current |", "| retired |")
            .replace("| yes |", "| no |"),
            encoding="utf-8",
        )
        (self.repo / "packages/example/README.md").unlink()

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_catalog_supports_split_packages_and_epoch(self):
        srcinfo = textwrap.dedent(
            """\
            pkgbase = example
            \tepoch = 2
            \tpkgver = 1.2.3
            \tpkgrel = 4
            \tarch = any

            pkgname = example

            pkgname = example-extra
            """
        )
        self.write("packages/example/.SRCINFO", srcinfo)
        self.write("packages/example/.generated-srcinfo", srcinfo)
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            .replace("| `example` |", "| `example`, `example-extra` |")
            .replace("| 1.2.3-4 |", "| 2:1.2.3-4 |"),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tracked_zsh_must_parse(self):
        self.write("tools/example.zsh", "#!/usr/bin/env zsh\nif true; then\n")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn("tools/example.zsh: zsh syntax check failed", result.stderr)
        self.assertNotIn(str(self.repo), result.stderr)

    def test_workflow_actions_must_use_full_commit_shas(self):
        workflow = self.repo / ".github/workflows/example.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace(
                "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
                "actions/checkout@v4",
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            ".github/workflows/example.yml: action must use a full commit SHA: actions/checkout@v4",
            result.stderr,
        )

    def test_workflow_action_pin_check_parses_valid_yaml_forms(self):
        workflow = self.repo / ".github/workflows/example.yml"
        cases = {
            "inline mapping": "steps:\n      - { uses: actions/checkout@v4 }\n",
            "quoted key": 'steps:\n      - "uses": actions/checkout@v4\n',
            "spaced separator": "steps:\n      - uses : actions/checkout@v4\n",
            "reusable workflow": "uses: owner/repository/.github/workflows/reuse.yml@main\n",
        }
        for label, job_body in cases.items():
            with self.subTest(label=label):
                workflow.write_text(
                    "name: Example\njobs:\n  example:\n    " + job_body,
                    encoding="utf-8",
                )

                result = self.run_checker()

                self.assertEqual(result.returncode, 1)
                self.assertIn("action must use a full commit SHA", result.stderr)

    def test_workflow_accepts_quoted_full_commit_sha(self):
        workflow = self.repo / ".github/workflows/example.yml"
        workflow.write_text(
            textwrap.dedent(
                """\
                name: Example
                jobs:
                  example:
                    steps:
                      - uses: "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
                """
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_workflow_accepts_checkout_local_action(self):
        workflow = self.repo / ".github/workflows/example.yml"
        workflow.write_text(
            "name: Example\njobs:\n  example:\n    steps:\n      - uses: ./actions/local\n",
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_workflow_yaml_fails_closed(self):
        workflow = self.repo / ".github/workflows/example.yml"
        workflow.write_text("name: [unterminated\n", encoding="utf-8")

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            ".github/workflows/example.yml: workflow YAML is invalid",
            result.stderr,
        )

    def test_workflow_action_pin_check_preserves_yaml_boolean_like_job_ids(self):
        workflow = self.repo / ".github/workflows/example.yml"
        workflow.write_text(
            textwrap.dedent(
                """\
                name: Example
                jobs:
                  yes:
                    steps:
                      - uses: actions/checkout@v4
                  true:
                    steps:
                      - run: echo safe
                """
            ),
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn("action must use a full commit SHA", result.stderr)

    def test_default_gate_runs_unit_tests_discovered_in_the_checkout(self):
        self.write(
            "tests/test_failure.py",
            textwrap.dedent(
                """\
                import unittest

                class FailureTest(unittest.TestCase):
                    def test_failure(self):
                        self.fail("fixture unit-test failure")
                """
            ),
        )

        result = self.run_checker(skip_tests=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture unit-test failure", result.stderr)
        self.assertNotIn("repository consistency: passed", result.stdout)


class RepositoryConsistencyWorkflowTests(unittest.TestCase):
    def dependency_install_script(self):
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["consistency"]["steps"]
        return next(
            step["run"]
            for step in steps
            if step.get("name") == "Install test dependencies"
        )

    def run_dependency_install_script(self, pacman_body):
        with tempfile.TemporaryDirectory(dir="/tmp") as tempdir:
            root = Path(tempdir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            count_file = root / "pacman-attempts"
            argument_file = root / "pacman-arguments"
            pacman = bin_dir / "pacman"
            pacman.write_text(
                "#!/usr/bin/bash\n"
                'arguments=("$@")\n'
                'printf \'%q\' "${arguments[0]}" >> "${PACMAN_ARGUMENT_FILE}"\n'
                'for argument in "${arguments[@]:1}"; do\n'
                '  printf \' %q\' "${argument}" >> "${PACMAN_ARGUMENT_FILE}"\n'
                "done\n"
                'printf \'\\n\' >> "${PACMAN_ARGUMENT_FILE}"\n'
                "count=0\n"
                'if [[ -f "${PACMAN_ATTEMPT_FILE}" ]]; then\n'
                '  IFS= read -r count < "${PACMAN_ATTEMPT_FILE}"\n'
                "fi\n"
                "((count += 1))\n"
                'printf \'%s\\n\' "${count}" > "${PACMAN_ATTEMPT_FILE}"\n'
                + pacman_body,
                encoding="utf-8",
            )
            pacman.chmod(0o755)
            sleep = bin_dir / "sleep"
            sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            sleep.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{bin_dir}:/usr/bin"
            environment["PACMAN_ATTEMPT_FILE"] = str(count_file)
            environment["PACMAN_ARGUMENT_FILE"] = str(argument_file)

            result = subprocess.run(
                ["/usr/bin/bash", "-c", self.dependency_install_script()],
                capture_output=True,
                text=True,
                env=environment,
                timeout=5,
                check=False,
            )

            return (
                result,
                int(count_file.read_text(encoding="utf-8")),
                argument_file.read_text(encoding="utf-8").splitlines(),
            )

    def test_workflow_retries_transient_dependency_sync_failures(self):
        result, attempts, arguments = self.run_dependency_install_script(
            '[[ "${count}" -ge 2 ]]\n'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(attempts, 2)
        self.assertEqual(
            arguments,
            ["-Syyu --noconfirm git jq python python-yaml rsync zsh"] * attempts,
        )

    def test_workflow_dependency_sync_retry_is_bounded(self):
        result, attempts, arguments = self.run_dependency_install_script("exit 1\n")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(attempts, 4)
        self.assertEqual(
            arguments,
            ["-Syyu --noconfirm git jq python python-yaml rsync zsh"] * attempts,
        )

    def test_workflow_runs_stable_unprivileged_gate_on_prs_and_main(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("pull_request:\n", text)
        self.assertIn("push:\n    branches:\n      - main\n", text)
        self.assertNotIn("paths:", text)
        self.assertIn("permissions:\n  contents: read\n", text)
        self.assertIn("name: Repository consistency\n", text)
        self.assertIn("image: archlinux:base-devel\n", text)
        self.assertIn(
            "uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
            text,
        )
        self.assertIn("persist-credentials: false", text)
        self.assertIn("runuser -u consistency", text)
        self.assertIn("python-yaml", text)
        self.assertIn("python3 tools/check_repo_consistency.py", text)
        self.assertNotIn("--skip-tests", text)
        self.assertLess(
            text.index("- name: Install test dependencies"),
            text.index("- name: Check out repository"),
        )


if __name__ == "__main__":
    unittest.main()
