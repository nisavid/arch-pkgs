import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "docs" / "maintainers" / "evidence"
MANIFEST = EVIDENCE_DIR / "open-webui-household-candidate-set-2026-10-02.json"
QDRANT_G0_G1 = EVIDENCE_DIR / "qdrant-1.19.1-1" / "g0-g1.json"
SPEECH_G0_G2 = EVIDENCE_DIR / "speech-providers-4.8.2-1.2.1" / "g0-g2.json"
FASTER_WHISPER_DIR = EVIDENCE_DIR / "python-faster-whisper-1.2.1-2"
FASTER_WHISPER_G0_G2 = FASTER_WHISPER_DIR / "g0-g2.json"
MAINTAINER_NOTE = (
    REPO_ROOT / "docs" / "maintainers" / "open-webui-household-candidate-set.md"
)
TOOLS = REPO_ROOT / "tools"

COMMIT = re.compile(r"^[0-9a-f]{40}$")
TOP_LEVEL_KEYS = {
    "schema",
    "candidate_set",
    "recorded",
    "binding_ticket",
    "adoption_main_commit",
    "archives",
    "external_inputs",
}
ENTRY_KEYS = {
    "archive",
    "source_commit_basis",
    "role",
    "package_directory",
    "package_tree",
    "main_tree_delta",
    "evidence",
}
OPTIONAL_ENTRY_KEYS = {"build_inputs"}
EXPECTED_IDENTITIES = {
    ("open-webui", "0.11.4-2", "deployed"),
    ("python-rapidocr", "3.9.2-1", "deployed"),
    ("qdrant", "1.19.1-1", "deployed"),
    ("qdrant-migration", "1.18.3-1", "deployed"),
    ("qdrant-web-ui", "0.2.18-1", "deployed"),
    ("python-faster-whisper", "1.2.1-2", "deployed"),
    ("ctranslate2", "4.8.2-1", "publication-identity-only"),
    ("python-ctranslate2", "4.8.2-1", "publication-identity-only"),
}
SOURCE_COMMIT_BASES = {"recorded-build-commit", "derived-tree-equal"}
DERIVED_SOURCE_COMMITS: set[str] = set()
ABSOLUTE_PATH = re.compile(r"(^|[\s\"'(=,;:])(/(?!/)|~/)|file:")
HOUSEHOLD_LANES = {
    "ctranslate2",
    "open-webui",
    "python-faster-whisper",
    "python-rapidocr",
    "qdrant",
    "qdrant-migration",
    "qdrant-web-ui",
}


def load_tool(name: str):
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        f"{name}_for_candidate_set", TOOLS / f"{name}.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load tools/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def reject_duplicate_keys(pairs):
    keys = [key for key, _value in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate JSON keys {duplicates}")
    return dict(pairs)


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def has_commit(commit: str) -> bool:
    return git("cat-file", "-e", f"{commit}^{{commit}}").returncode == 0


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


class OpenWebUIHouseholdCandidateSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            MANIFEST.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
        cls.stager = load_tool("stage_accepted_repo")
        cls.consistency = load_tool("check_repo_consistency")
        cls.entries = {
            entry["archive"]["package"]: entry for entry in cls.manifest["archives"]
        }

    def test_manifest_shape(self):
        manifest = self.manifest
        self.assertEqual(set(manifest), TOP_LEVEL_KEYS)
        self.assertEqual(manifest["schema"], "arch-pkgs-candidate-set/v1")
        self.assertEqual(manifest["candidate_set"], "open-webui-household")
        self.assertEqual(
            manifest["binding_ticket"], "https://github.com/nisavid/arch-pkgs/issues/88"
        )
        self.assertRegex(manifest["adoption_main_commit"], COMMIT)
        self.assertNotIn("source_commit", manifest)
        self.assertEqual(len(self.entries), len(manifest["archives"]))
        self.assertEqual(
            {
                (entry["archive"]["package"], entry["archive"]["version"], entry["role"])
                for entry in manifest["archives"]
            },
            EXPECTED_IDENTITIES,
        )
        for entry in manifest["archives"]:
            package = entry["archive"]["package"]
            with self.subTest(package=package):
                self.assertLessEqual(ENTRY_KEYS, set(entry))
                self.assertLessEqual(set(entry), ENTRY_KEYS | OPTIONAL_ENTRY_KEYS)
                self.assertRegex(entry["package_tree"], COMMIT)
                self.assertIn(entry["source_commit_basis"], SOURCE_COMMIT_BASES)
                self.assertEqual(
                    entry["source_commit_basis"] == "derived-tree-equal",
                    package in DERIVED_SOURCE_COMMITS,
                )
                self.assertRegex(entry["package_directory"], r"^packages/[a-z0-9.+-]+$")
                self.assertTrue((REPO_ROOT / entry["package_directory"]).is_dir())
                self.assertIsInstance(entry["main_tree_delta"], list)
                self.assertTrue(entry["evidence"])
                self.assertEqual(
                    "build_inputs" in entry, package == "open-webui", package
                )

    def test_archive_records_are_stager_records_with_source_commits(self):
        archives = [entry["archive"] for entry in self.manifest["archives"]]
        for record in archives:
            with self.subTest(package=record["package"]):
                self.assertEqual(
                    set(record), self.stager.ARCHIVE_KEYS | {"source_commit"}
                )
                self.assertRegex(record["source_commit"], COMMIT)
        staging_manifest = {
            "schema": self.stager.MANIFEST_SCHEMA,
            "repository": {"name": "nisavid", "arch": "x86_64"},
            "archives": archives,
        }
        self.assertEqual(self.stager.manifest_errors(staging_manifest), [])

    def test_open_webui_record_binds_the_merged_main_build(self):
        entry = self.entries["open-webui"]
        self.assertEqual(
            entry["archive"],
            {
                "package": "open-webui",
                "version": "0.11.4-2",
                "arch": "x86_64",
                "filename": "open-webui-0.11.4-2-x86_64.pkg.tar.zst",
                "size": 186956865,
                "sha256": "31f3fbefc2ef3c4a6e8b8ee885372a1020de563c8845904d9a716fed5896d77a",
                "source": "open-webui/2059571",
                "source_commit": "2059571d63b02ee1d66b3dfed943c7554a643876",
            },
        )
        self.assertEqual(entry["package_tree"], "1ec719e07e43fdaea7fe1f24bb2d73f658da96d8")
        self.assertEqual(entry["main_tree_delta"], [])
        self.assertEqual(
            {(item["release"], item["sha256"]) for item in entry["build_inputs"]},
            {
                (
                    "open-webui-0.11.4-offline-closures-v1",
                    "617abc7d60da12f080faa690de989fff38eb4cd40b519256cce35a48086b9438",
                ),
                (
                    "open-webui-0.11.4-python-closure-185b40a6",
                    "65b62d21888830ae6d25a3077626b9e1a3faca2aaa192ebe2a468a86bc40e704",
                ),
            },
        )

    def test_rapidocr_record_binds_the_adopted_reference_build(self):
        entry = self.entries["python-rapidocr"]
        self.assertEqual(
            entry["archive"],
            {
                "package": "python-rapidocr",
                "version": "3.9.2-1",
                "arch": "any",
                "filename": "python-rapidocr-3.9.2-1-any.pkg.tar.zst",
                "size": 27198440,
                "sha256": "0e70fb599a535f9bb1c0c0b3a2f88abe9993f7632eba8e2c618826c7f01bf99b",
                "source": "open-webui/f25fd53",
                "source_commit": "f25fd53b2b059b278b68a9bb4f661bdc2a06dc34",
            },
        )
        self.assertEqual(entry["source_commit_basis"], "recorded-build-commit")
        self.assertEqual(entry["package_tree"], "3aca7d551b2dac91c62877c5e3c47a429714d3ee")
        self.assertEqual(entry["main_tree_delta"], [])

    def test_faster_whisper_record_binds_the_merged_main_build(self):
        entry = self.entries["python-faster-whisper"]
        self.assertEqual(
            entry["archive"],
            {
                "package": "python-faster-whisper",
                "version": "1.2.1-2",
                "arch": "any",
                "filename": "python-faster-whisper-1.2.1-2-any.pkg.tar.zst",
                "size": 1088665,
                "sha256": "9d8bdab118453c3a3cfded8a0430a526784e2ee4c9bce5038171f4de3a29f89b",
                "source": "python-faster-whisper/86549fa",
                "source_commit": "86549fa8062d792861d27d0f3faf722a733bcaaa",
            },
        )
        self.assertEqual(entry["source_commit_basis"], "recorded-build-commit")
        self.assertEqual(entry["package_tree"], "042e1f67990f6b834153b58fb8b98bd9329ffe7f")
        self.assertEqual(entry["main_tree_delta"], [])
        self.assertEqual(
            entry["evidence"],
            [
                "docs/maintainers/evidence/python-faster-whisper-1.2.1-2/",
                "https://github.com/nisavid/arch-pkgs/pull/125",
            ],
        )

    def test_adoption_commit_is_the_latest_merged_main_build(self):
        # The tree comparison runs against the newest main commit any record
        # was built from: python-faster-whisper 1.2.1-2's merged main build.
        # Every merged-main build must still be tree-equal there.
        self.assertEqual(
            self.manifest["adoption_main_commit"],
            self.entries["python-faster-whisper"]["archive"]["source_commit"],
        )
        for package in ("open-webui", "python-rapidocr", "python-faster-whisper"):
            with self.subTest(package=package):
                self.assertEqual(self.entries[package]["main_tree_delta"], [])

    def test_qdrant_records_match_the_g0_g1_candidate_set(self):
        candidates = json.loads(QDRANT_G0_G1.read_text(encoding="utf-8"))[
            "candidate_set"
        ]["candidates"]
        self.assertEqual(len(candidates), 3)
        for candidate in candidates:
            with self.subTest(lane=candidate["lane"]):
                record = self.entries[candidate["lane"]]["archive"]
                self.assertEqual(record["filename"], candidate["name"])
                self.assertEqual(record["size"], candidate["size"])
                self.assertEqual(record["sha256"], candidate["sha256"])

    def test_speech_records_match_the_g0_g2_archives(self):
        # The CTranslate2 pair comes from the speech-providers record, and
        # python-faster-whisper from its own 1.2.1-2 record, which supersedes
        # the speech-providers 1.2.1-1 archive.
        speech = json.loads(SPEECH_G0_G2.read_text(encoding="utf-8"))["gates"]["G1"][
            "archives"
        ]
        faster_whisper = json.loads(FASTER_WHISPER_G0_G2.read_text(encoding="utf-8"))
        superseded = faster_whisper["supersedes"]["archives"]
        self.assertEqual(len(speech), 3)
        self.assertLessEqual(set(superseded), set(speech))
        archives = {
            filename: archive
            for filename, archive in speech.items()
            if filename not in superseded
        }
        archives.update(faster_whisper["gates"]["G1"]["archives"])
        self.assertEqual(len(archives), 3)
        for filename, archive in archives.items():
            with self.subTest(filename=filename):
                record = self.entries[archive["name"]]["archive"]
                self.assertEqual(record["filename"], filename)
                self.assertEqual(record["version"], archive["version"])
                self.assertEqual(record["size"], archive["size"])
                self.assertEqual(record["sha256"], archive["sha256"])
        for filename, archive in superseded.items():
            with self.subTest(superseded=filename):
                self.assertEqual(archive["sha256"], speech[filename]["sha256"])
                self.assertNotIn(
                    archive["sha256"],
                    {entry["archive"]["sha256"] for entry in self.manifest["archives"]},
                )

    def test_faster_whisper_evidence_binds_its_recipe_and_harness(self):
        evidence = json.loads(FASTER_WHISPER_G0_G2.read_text(encoding="utf-8"))
        entry = self.entries["python-faster-whisper"]
        source = evidence["repository_source"]
        self.assertEqual(source["source_commit"], entry["archive"]["source_commit"])
        self.assertEqual(source["package_tree"], entry["package_tree"])
        (archive,) = evidence["gates"]["G1"]["archives"].values()
        pkgbuild = source["files"][f"{entry['package_directory']}/PKGBUILD"]
        self.assertEqual(archive["pkgbuild_sha256"], pkgbuild["sha256"])
        self.assertEqual(
            archive["key_payload_sha256"][
                "usr/lib/python3.14/site-packages/faster_whisper/assets/silero_vad_v6.onnx"
            ],
            "4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2",
        )
        fixture = evidence["gates"]["G2"]["fixture"]
        harness = (FASTER_WHISPER_DIR / fixture["harness"]).read_bytes()
        self.assertEqual(hashlib.sha256(harness).hexdigest(), fixture["harness_sha256"])
        g2 = evidence["gates"]["G2"]
        self.assertIs(g2["pass"], True)
        self.assertNotIn("status", g2)
        self.assertEqual(g2["versions"]["av"], "19.0.1")
        self.assertTrue(all(check["pass"] for check in g2["checks"].values()))
        self.assertTrue(g2["baseline_control"]["pass"])
        transcript = g2["checks"]["fw_int8_transcription_word_timestamps"]
        self.assertEqual(transcript["language"], "en")
        self.assertGreaterEqual(transcript["word_count"], 20)
        if not has_commit(source["source_commit"]):
            self.skipTest("source commit not present in this clone")
        for path, digest in source["files"].items():
            with self.subTest(path=path):
                shown = subprocess.run(
                    ["git", "show", f"{source['source_commit']}:{path}"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(shown.returncode, 0, shown.stderr)
                self.assertEqual(hashlib.sha256(shown.stdout).hexdigest(), digest["sha256"])
                self.assertEqual(len(shown.stdout), digest["size"])

    def test_external_inputs_are_evidence_not_candidates(self):
        external = {item["package"]: item for item in self.manifest["external_inputs"]}
        self.assertEqual(
            set(external), {"python-ctranslate2-gfx1151", "python-sentence-transformers"}
        )
        self.assertFalse(set(external) & set(self.entries))
        self.assertEqual(external["python-sentence-transformers"]["version"], "5.7.0-1")
        self.assertEqual(
            external["python-sentence-transformers"]["origin"],
            "https://aur.archlinux.org/packages/python-sentence-transformers",
        )
        self.assertEqual(external["python-ctranslate2-gfx1151"]["version"], "4.7.2-1")
        self.assertEqual(
            external["python-ctranslate2-gfx1151"]["origin"],
            "https://github.com/nisavid/arch-strix-halo-pkgs",
        )
        self.assertIn(
            "https://github.com/nisavid/arch-pkgs/issues/63#issuecomment-5789382398",
            external["python-sentence-transformers"]["evidence"],
        )
        for item in external.values():
            with self.subTest(package=item["package"]):
                self.assertEqual(
                    set(item), {"package", "version", "origin", "role", "evidence"}
                )
                self.assertTrue(item["evidence"])

    def test_manifest_carries_no_absolute_paths(self):
        for value in strings(self.manifest):
            with self.subTest(value=value):
                self.assertNotRegex(value, ABSOLUTE_PATH)

    def test_catalog_retires_sentence_transformers_and_defers_the_stack(self):
        """Pin the catalog state this binding leaves behind.

        These rows change on purpose later: #90's promotion PR moves the
        household rows out of deferred, and #62's cleanup changes or removes
        the python-sentence-transformers row. Each of those changes must update
        this test.
        """
        rows = self.consistency.catalog_rows(REPO_ROOT)
        (retired,) = rows["python-sentence-transformers"]
        self.assertEqual(retired[3], "retired")
        self.assertEqual(retired[7], "no")
        self.assertIn("https://github.com/nisavid/arch-pkgs/issues/62", retired[6])
        for lane in sorted(HOUSEHOLD_LANES):
            with self.subTest(lane=lane):
                (row,) = rows[lane]
                self.assertEqual(row[3], "deferred")
                self.assertEqual(row[7], "no")
        (open_webui,) = rows["open-webui"]
        self.assertIn("open-webui-household-candidate-set.md", open_webui[6])
        self.assertIn("do not rebuild it", open_webui[6])
        self.assertNotIn("still needs a new build", open_webui[6])

    def test_maintainer_note_links_the_manifest_and_tickets(self):
        note = MAINTAINER_NOTE.read_text(encoding="utf-8")
        self.assertIn(f"evidence/{MANIFEST.name}", note)
        for issue in (62, 88, 89, 90, 118):
            with self.subTest(issue=issue):
                self.assertIn(f"https://github.com/nisavid/arch-pkgs/issues/{issue}", note)

    def test_package_trees_match_their_source_commits(self):
        main_commit = self.manifest["adoption_main_commit"]
        for entry in self.manifest["archives"]:
            commit = entry["archive"]["source_commit"]
            directory = entry["package_directory"]
            with self.subTest(package=entry["archive"]["package"]):
                if not (has_commit(commit) and has_commit(main_commit)):
                    self.skipTest("source or adoption commit not present in this clone")
                tree = git("rev-parse", "--verify", f"{commit}:{directory}")
                self.assertEqual(tree.returncode, 0, tree.stderr)
                self.assertEqual(tree.stdout.strip(), entry["package_tree"])
                delta = git(
                    "diff", "--name-only", "--relative=" + directory,
                    commit, main_commit, "--", directory,
                )
                self.assertEqual(delta.returncode, 0, delta.stderr)
                self.assertEqual(sorted(delta.stdout.split()), entry["main_tree_delta"])

    def test_derived_source_commits_are_the_earliest_tree_equal_main_commit(self):
        main_commit = self.manifest["adoption_main_commit"]
        for entry in self.manifest["archives"]:
            if entry["source_commit_basis"] != "derived-tree-equal":
                continue
            commit = entry["archive"]["source_commit"]
            directory = entry["package_directory"]
            with self.subTest(package=entry["archive"]["package"]):
                if not (has_commit(commit) and has_commit(main_commit)):
                    self.skipTest("source or adoption commit not present in this clone")
                ancestry = git("merge-base", "--is-ancestor", commit, main_commit)
                self.assertEqual(ancestry.returncode, 0, "derived commit is not on main")
                history = git("rev-list", "--reverse", main_commit, "--", directory)
                self.assertEqual(history.returncode, 0, history.stderr)
                earliest = next(
                    candidate
                    for candidate in history.stdout.split()
                    if git("rev-parse", f"{candidate}:{directory}").stdout.strip()
                    == entry["package_tree"]
                )
                self.assertEqual(earliest, commit)

    def test_open_webui_pkgbuild_pins_the_build_inputs(self):
        entry = self.entries["open-webui"]
        commit = entry["archive"]["source_commit"]
        if not has_commit(commit):
            self.skipTest("open-webui source commit not present in this clone")
        pkgbuild = git("show", f"{commit}:{entry['package_directory']}/PKGBUILD")
        self.assertEqual(pkgbuild.returncode, 0, pkgbuild.stderr)
        pkgver = entry["archive"]["version"].rsplit("-", 1)[0]
        text = pkgbuild.stdout.replace("${pkgver}", pkgver)
        for item in entry["build_inputs"]:
            with self.subTest(release=item["release"]):
                self.assertIn(item["release"], text)
                self.assertIn(item["sha256"], text)
                self.assertIn(f'"{item["asset"]}::https://', text)
                self.assertIn(f'/{item["asset"]}"', text)


if __name__ == "__main__":
    unittest.main()
