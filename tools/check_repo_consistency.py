#!/usr/bin/env python3

import argparse
import hashlib
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode


def package_lane_names(repo: Path) -> set[str]:
    names: set[str] = set()
    for path in repository_paths(repo):
        relative = path.relative_to(repo)
        if len(relative.parts) >= 3 and relative.parts[0] == "packages":
            names.add(relative.parts[1])
    return names


def check_package_pairs(repo: Path) -> list[str]:
    errors: list[str] = []
    packages_dir = repo / "packages"
    for package_name in sorted(package_lane_names(repo)):
        package_dir = packages_dir / package_name
        has_pkgbuild = (package_dir / "PKGBUILD").is_file()
        has_srcinfo = (package_dir / ".SRCINFO").is_file()
        relative = package_dir.relative_to(repo).as_posix()
        if not (has_pkgbuild and has_srcinfo):
            errors.append(f"{relative}: PKGBUILD and .SRCINFO must both exist")
    return errors


def check_srcinfo(repo: Path) -> list[str]:
    errors: list[str] = []
    for package_dir in sorted((repo / "packages").iterdir()):
        if not package_dir.is_dir():
            continue
        pkgbuild = package_dir / "PKGBUILD"
        srcinfo = package_dir / ".SRCINFO"
        if not (pkgbuild.is_file() and srcinfo.is_file()):
            continue
        result = subprocess.run(
            ["makepkg", "--printsrcinfo"],
            cwd=package_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        relative = srcinfo.relative_to(repo).as_posix()
        if result.returncode != 0:
            detail = result.stderr.strip() or f"makepkg exited {result.returncode}"
            errors.append(f"{relative}: {detail}")
            continue
        if srcinfo.read_text(encoding="utf-8") != result.stdout:
            errors.append(f"{relative} does not match makepkg --printsrcinfo")
    return errors


CATALOG_DIRECTORY = re.compile(r"^\[`(?P<name>[^`]+)`\]\((?P=name)/\)$")
BASELINE_FIELDS = (
    "authoritative_reference",
    "advisory_references",
    "divergence_notes",
    "update_notes",
)
CHATGPT_RETIREMENT_EVIDENCE = Path(
    "docs/maintainers/evidence/chatgpt-fallback-baseline-2026-08-16.json"
)
CHATGPT_RETIREMENT_EVIDENCE_SHA256 = (
    "9002ee0c06f45c64f3fe08bd85fc4f7d74f962a8246f4ece9c6753477028f220"
)
RETIRED_CHATGPT_PRODUCER_NAMES = {"chatgpt", "codex-app", "codex-desktop"}
FORBIDDEN_LOCAL_CHATGPT_LANE_NAMES = RETIRED_CHATGPT_PRODUCER_NAMES | {
    "chatgpt-desktop-bin"
}


def check_retired_chatgpt_sources(repo: Path) -> list[str]:
    errors: list[str] = []
    evidence = repo / CHATGPT_RETIREMENT_EVIDENCE
    if not evidence.is_file():
        errors.append(
            f"{CHATGPT_RETIREMENT_EVIDENCE.as_posix()}: "
            "exact historical evidence is missing"
        )
    elif hashlib.sha256(evidence.read_bytes()).hexdigest() != (
        CHATGPT_RETIREMENT_EVIDENCE_SHA256
    ):
        errors.append(
            f"{CHATGPT_RETIREMENT_EVIDENCE.as_posix()}: "
            "historical evidence digest does not match the retained baseline"
        )
    retired_lane_names: set[str] = set()
    for path in repository_paths(repo):
        relative = path.relative_to(repo)
        if (
            len(relative.parts) >= 3
            and relative.parts[0] == "packages"
            and relative.parts[1] in FORBIDDEN_LOCAL_CHATGPT_LANE_NAMES
        ):
            retired_lane_names.add(relative.parts[1])
    for name in sorted(retired_lane_names):
        if name == "chatgpt":
            errors.append("packages/chatgpt: retired package lane must remain absent")
        elif name == "chatgpt-desktop-bin":
            errors.append(
                "packages/chatgpt-desktop-bin: "
                "local ChatGPT package lane must remain absent"
            )
        else:
            errors.append(
                f"packages/{name}: retired ChatGPT producer lane must remain absent"
            )
    rows = catalog_rows(repo)
    for name in sorted(rows.keys() & FORBIDDEN_LOCAL_CHATGPT_LANE_NAMES):
        if name == "chatgpt-desktop-bin":
            errors.append(
                "packages/README.md: local ChatGPT package catalog row "
                "must remain absent"
            )
        else:
            errors.append(
                f"packages/README.md: retired ChatGPT catalog row must remain absent: {name}"
            )
    catalog_identities = {
        identity
        for matching_rows in rows.values()
        for row in matching_rows
        if len(row) >= 2
        for identity in re.findall(r"`([^`]+)`", row[1])
    }
    for identity in sorted(catalog_identities & FORBIDDEN_LOCAL_CHATGPT_LANE_NAMES):
        if identity == "chatgpt-desktop-bin":
            errors.append(
                "packages/README.md: local ChatGPT package identity "
                f"must remain absent: {identity}"
            )
        else:
            errors.append(
                "packages/README.md: retired ChatGPT producer identity "
                f"must remain absent: {identity}"
            )
    retired_ingest_helpers = sorted(
        path.relative_to(repo).as_posix()
        for path in repository_paths(repo)
        if re.fullmatch(r"tools/ingest_chatgpt[^/]*", path.relative_to(repo).as_posix())
    )
    for relative in retired_ingest_helpers:
        if relative == "tools/ingest_chatgpt.zsh":
            errors.append(f"{relative}: retired ingest helper must remain absent")
        else:
            errors.append(
                f"{relative}: retired ChatGPT ingest helper must remain absent"
            )
    return errors


def repository_paths(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    return sorted(
        repo / relative_path
        for relative_path in result.stdout.split("\0")
        if relative_path and (repo / relative_path).is_file()
    )


def check_zsh_syntax(repo: Path) -> list[str]:
    errors: list[str] = []
    for path in repository_paths(repo):
        if path.suffix != ".zsh":
            continue
        relative = path.relative_to(repo)
        result = subprocess.run(
            ["zsh", "-n", relative.as_posix()],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            suffix = f": {detail[-1]}" if detail else ""
            errors.append(f"{relative.as_posix()}: zsh syntax check failed{suffix}")
    return errors


PINNED_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def mapping_values(mapping: Node | None, key: str) -> list[Node]:
    if not isinstance(mapping, MappingNode):
        return []
    return [
        value
        for candidate, value in mapping.value
        if isinstance(candidate, ScalarNode) and candidate.value == key
    ]


def workflow_action_references(document: Node | None) -> list[Node]:
    references: list[Node] = []
    for jobs in mapping_values(document, "jobs"):
        if not isinstance(jobs, MappingNode):
            continue
        for _, job in jobs.value:
            if not isinstance(job, MappingNode):
                continue
            references.extend(mapping_values(job, "uses"))
            for steps in mapping_values(job, "steps"):
                if not isinstance(steps, SequenceNode):
                    continue
                for step in steps.value:
                    references.extend(mapping_values(step, "uses"))
    return references


def check_workflow_action_pins(repo: Path) -> list[str]:
    errors: list[str] = []
    workflows = repo / ".github/workflows"
    if not workflows.is_dir():
        return errors
    for path in sorted(workflows.iterdir()):
        if path.suffix not in {".yml", ".yaml"} or not path.is_file():
            continue
        relative = path.relative_to(repo).as_posix()
        try:
            document = yaml.compose(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            errors.append(f"{relative}: workflow YAML is invalid")
            continue
        for action_node in workflow_action_references(document):
            if not isinstance(action_node, ScalarNode):
                errors.append(f"{relative}: action reference must be a string")
                continue
            action = action_node.value
            if action.startswith("./") or PINNED_ACTION.fullmatch(action):
                continue
            errors.append(
                f"{relative}: action must use a full commit SHA: {action}"
            )
    return errors


def catalog_rows(repo: Path) -> dict[str, list[list[str]]]:
    rows: dict[str, list[list[str]]] = {}
    catalog = (repo / "packages/README.md").read_text(encoding="utf-8")
    for line in catalog.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells:
            continue
        match = CATALOG_DIRECTORY.fullmatch(cells[0])
        if match:
            rows.setdefault(match.group("name"), []).append(cells)
    return rows


def check_catalog_coverage(repo: Path) -> list[str]:
    errors: list[str] = []
    rows = catalog_rows(repo)
    package_names = package_lane_names(repo)
    for package_name in sorted(package_names):
        count = len(rows.get(package_name, []))
        if count != 1:
            errors.append(
                "packages/README.md: "
                f"package lane {package_name} must appear exactly once; found {count}"
            )
    for package_name in sorted(rows.keys() - package_names):
        errors.append(
            f"packages/README.md: catalog references missing package lane {package_name}"
        )
    return errors


def srcinfo_identity(repo: Path, srcinfo: Path) -> tuple[list[str], str]:
    values: dict[str, list[str]] = {}
    for line in srcinfo.read_text(encoding="utf-8").splitlines():
        if " = " not in line:
            continue
        key, value = line.strip().split(" = ", 1)
        values.setdefault(key, []).append(value)
    relative = srcinfo.relative_to(repo).as_posix()

    def required_single_value(key: str) -> str:
        matching = values.get(key, [])
        if len(matching) != 1 or not matching[0].strip():
            raise ValueError(
                f"{relative}: required field {key} must appear exactly once and be nonempty"
            )
        return matching[0]

    package_names = values.get("pkgname", [])
    if not package_names or any(not name.strip() for name in package_names):
        raise ValueError(
            f"{relative}: required field pkgname must appear and be nonempty"
        )
    version = required_single_value("pkgver")
    if "epoch" in values:
        version = f"{required_single_value('epoch')}:{version}"
    version = f"{version}-{required_single_value('pkgrel')}"
    return sorted(package_names), version


def package_identity(repo: Path, package_name: str) -> tuple[list[str], str]:
    return srcinfo_identity(repo, repo / "packages" / package_name / ".SRCINFO")


def check_catalog_identity(repo: Path) -> list[str]:
    errors: list[str] = []
    for package_name, matching_rows in sorted(catalog_rows(repo).items()):
        if len(matching_rows) != 1 or not (repo / "packages" / package_name).is_dir():
            continue
        if not (repo / "packages" / package_name / ".SRCINFO").is_file():
            continue
        row = matching_rows[0]
        if len(row) < 3:
            continue
        try:
            expected_names, expected_version = package_identity(repo, package_name)
        except (KeyError, ValueError) as error:
            errors.append(str(error))
            continue
        catalog_names = sorted(re.findall(r"`([^`]+)`", row[1]))
        if catalog_names != expected_names:
            errors.append(
                "packages/README.md: "
                f"{package_name} package names {catalog_names} do not match {expected_names}"
            )
        if row[2] != expected_version:
            errors.append(
                "packages/README.md: "
                f"{package_name} packaged version {row[2]} does not match {expected_version}"
            )
    return errors


def check_catalog_shape(repo: Path) -> list[str]:
    errors: list[str] = []
    for package_name, matching_rows in sorted(catalog_rows(repo).items()):
        if len(matching_rows) != 1:
            continue
        row = matching_rows[0]
        if len(row) != 8:
            errors.append(
                f"packages/README.md: {package_name} row must contain exactly 8 columns"
            )
            continue
        if any(not cell for cell in row):
            errors.append(
                f"packages/README.md: {package_name} row contains an empty required cell"
            )
        disposition = row[3]
        if disposition not in {"accepted-current", "deferred", "retired"}:
            errors.append(
                f"packages/README.md: {package_name} has invalid disposition {disposition}"
            )
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[5]):
                raise ValueError
            date.fromisoformat(row[5])
        except ValueError:
            errors.append(
                f"packages/README.md: {package_name} review date must be ISO YYYY-MM-DD"
            )
        if row[7] not in {"yes", "no"}:
            errors.append(
                f"packages/README.md: {package_name} publication eligibility must be yes or no"
            )
        if disposition == "accepted-current" and row[7] == "no":
            errors.append(
                f"packages/README.md: {package_name} accepted-current lane "
                "must be publication eligible"
            )
        if disposition == "retired" and row[7] == "yes":
            errors.append(
                f"packages/README.md: {package_name} retired lane "
                "must not be publication eligible"
            )
    return errors


def baseline_value_is_present(text: str, field: str) -> bool:
    pattern = re.compile(
        rf"(?m)^- `{re.escape(field)}`:[ \t]*(?P<value>[^\n]*)$"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return False
    match = matches[0]
    if match.group("value").strip():
        return True
    for line in text[match.end() :].splitlines():
        if not line.strip():
            continue
        return line.startswith((" ", "\t"))
    return False


def maintenance_baseline_section(text: str) -> str | None:
    headings = list(re.finditer(r"(?m)^## Maintenance Baseline\s*$", text))
    if len(headings) != 1:
        return None
    start = headings[0].end()
    following = text[start:]
    next_heading = re.search(r"(?m)^#{1,2}\s+", following)
    if next_heading:
        following = following[: next_heading.start()]
    return following


def check_package_baselines(repo: Path) -> list[str]:
    errors: list[str] = []
    for package_name, matching_rows in sorted(catalog_rows(repo).items()):
        if len(matching_rows) != 1 or len(matching_rows[0]) != 8:
            continue
        disposition = matching_rows[0][3]
        if disposition == "retired" or disposition not in {
            "accepted-current",
            "deferred",
        }:
            continue
        readme = repo / "packages" / package_name / "README.md"
        relative = readme.relative_to(repo).as_posix()
        if not readme.is_file():
            errors.append(f"{relative}: retained package lane requires a README")
            continue
        text = readme.read_text(encoding="utf-8")
        baseline = maintenance_baseline_section(text)
        if baseline is None:
            errors.append(
                f"{relative}: required section ## Maintenance Baseline "
                "must appear exactly once"
            )
            continue
        for field in BASELINE_FIELDS:
            if not baseline_value_is_present(baseline, field):
                errors.append(
                    f"{relative}: required baseline field {field} "
                    "must appear exactly once and be nonempty"
                )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate repository consistency")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to this checkout)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip the committed unit-test phase during focused checker development",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    if not (repo / ".git").exists():
        print(f"repository consistency: not a Git checkout: {repo}", file=sys.stderr)
        return 2

    if not args.skip_tests:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-v"],
            cwd=repo,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode

    errors = check_retired_chatgpt_sources(repo)
    errors.extend(check_package_pairs(repo))
    errors.extend(check_srcinfo(repo))
    errors.extend(check_catalog_coverage(repo))
    errors.extend(check_catalog_identity(repo))
    errors.extend(check_catalog_shape(repo))
    errors.extend(check_package_baselines(repo))
    errors.extend(check_zsh_syntax(repo))
    errors.extend(check_workflow_action_pins(repo))
    if errors:
        for error in errors:
            print(f"repository consistency: {error}", file=sys.stderr)
        return 1

    print("repository consistency: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
