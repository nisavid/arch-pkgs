import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "tools" / "check_repo_consistency.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "repository-consistency.yml"


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

    def test_chatgpt_identity_requires_object_package_metadata(self):
        baseline_readme = (self.repo / "packages/example/README.md").read_text(
            encoding="utf-8"
        )
        for name in ("PKGBUILD", ".SRCINFO", ".generated-srcinfo", "README.md"):
            (self.repo / "packages/example" / name).unlink()
        catalog = self.repo / "packages/README.md"
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            .replace("[`example`](example/)", "[`chatgpt`](chatgpt/)")
            .replace("| `example` | 1.2.3-4 |", "| `chatgpt` | 1.0-1 |"),
            encoding="utf-8",
        )
        self.write("packages/chatgpt/README.md", baseline_readme)
        self.write(
            "packages/chatgpt/fallback-baseline-fixture.json",
            '{"package": []}\n',
        )

        result = self.run_checker()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "packages/chatgpt/fallback-baseline-fixture.json: package must be an object",
            result.stderr,
        )
        self.assertNotIn("Traceback", result.stderr)

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

    def test_default_gate_runs_committed_unit_tests(self):
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
