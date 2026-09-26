import contextlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
KIT = REPO_ROOT / "tools" / "accept_open_webui_household.py"
# The trial candidate's open-webui.env, household profile example, and unit:
# exact copies of the 0.11.4-1 package files, which move the household
# settings out of open-webui.env.  The in-tree package predates that split.
CANDIDATE = REPO_ROOT / "tools" / "fixtures" / "open-webui-household-acceptance" / "open-webui-0.11.4-1"
PACKAGED_ENV = CANDIDATE / "open-webui.env"
PROFILE_EXAMPLE = CANDIDATE / "household.env.example"
OPEN_WEBUI_UNIT = CANDIDATE / "open-webui.service"
QDRANT_UNIT = REPO_ROOT / "packages" / "qdrant" / "qdrant.service"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


kit_module = load("accept_open_webui_household", KIT)
sc = kit_module.sc
v1 = kit_module.v1


def packaged_env():
    """The candidate's vanilla open-webui.env."""

    return sc.parse_env_file(PACKAGED_ENV.read_text(encoding="utf-8"))


def candidate_env(lemond_url=None):
    """The candidate's open-webui.env with its example profile, rendered for ``lemond_url``, over it."""

    example = PROFILE_EXAMPLE.read_text(encoding="utf-8")
    profile = sc.render_household_profile(example, lemond_url or sc.DEFAULT_LEMOND_URL)
    return {**packaged_env(), **sc.parse_env_file(profile)}


def write_candidate_tree(root):
    """Extract the candidate's env, example, and unit into ``<root>/tree/open-webui`` as stage would."""

    tree = Path(root) / "tree" / "open-webui"
    for source, target in ((PACKAGED_ENV, "etc/open-webui/open-webui.env"),
                           (PROFILE_EXAMPLE, sc.HOUSEHOLD_EXAMPLE),
                           (OPEN_WEBUI_UNIT, "usr/lib/systemd/system/open-webui.service")):
        (tree / target).parent.mkdir(parents=True, exist_ok=True)
        (tree / target).write_bytes(source.read_bytes())
    return tree


def make_kit(root, *, rehearsal=False, route=None):
    root = Path(root)
    if route is not None:
        (root / "kit.json").write_text(json.dumps({"credential_route": route}))
    return kit_module.Kit(
        root=root,
        manifest_path=None,
        provider="stub" if rehearsal else "lemond",
        rehearsal=rehearsal,
        lemond_url=kit_module.STUB_URL if rehearsal else sc.DEFAULT_LEMOND_URL,
        chat_model="household-chat-stub-v1" if rehearsal else "resident-chat",
        embedding_model=None,
        reranking_model=None,
        whisper_model="base",
        candidate_store=root / "store",
        runtime_dir=root / "run",
    )


def write_archive(directory, name, data=b"candidate"):
    Path(directory).mkdir(parents=True, exist_ok=True)
    path = Path(directory) / name
    path.write_bytes(data)
    return {"name": name, "size": len(data), "sha256": v1._sha256_bytes(data)}


# The six deployed candidates of the 0.11.4 re-baseline, in DEPLOYED_PACKAGES order.
CANDIDATE_ARCHIVES = (
    "open-webui-0.11.4-1-x86_64.pkg.tar.zst",
    "python-rapidocr-3.9.2-1-any.pkg.tar.zst",
    "qdrant-1.19.1-1-x86_64.pkg.tar.zst",
    "qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst",
    "qdrant-web-ui-0.2.18-1-any.pkg.tar.zst",
    "python-faster-whisper-1.2.1-1-any.pkg.tar.zst",
)


def six_archives(directory):
    return [write_archive(directory, name, name.encode()) for name in CANDIDATE_ARCHIVES]


def write_manifest(directory, archives, **extra):
    path = Path(directory) / "manifest.json"
    path.write_text(json.dumps({"source_commit": "3647a6f", "archives": archives, **extra}))
    return path


class ArgumentTests(unittest.TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        patcher = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.runtime.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def kit(self, *argv):
        return kit_module.kit_from_args(kit_module.parser().parse_args(list(argv)))

    def test_every_subcommand_takes_the_documented_flags(self):
        common = [
            "--root", "/srv/build/owui", "--manifest", "m.json", "--lemond-url", "http://127.0.0.1:13305",
            "--chat-model", "chat", "--embedding-model", "e", "--reranking-model", "r",
            "--whisper-model", "tiny", "--provider", "lemond",
        ]
        for command in ("preflight", "stage", "up", "down", "trial", "resmoke", "teardown"):
            args = kit_module.parser().parse_args([command, *common])
            self.assertEqual(args.command, command)
            self.assertEqual(args.root, Path("/srv/build/owui"))
        self.assertTrue(kit_module.parser().parse_args(["preflight", "--probe-only"]).probe_only)
        self.assertTrue(kit_module.parser().parse_args(["teardown", "--keep-anchor"]).keep_anchor)
        self.assertEqual(
            kit_module.parser().parse_args(["trial", "--lemonade-receipt", "a", "--lemonade-receipt", "b"]).lemonade_receipt,
            ["a", "b"],
        )

    def test_defaults_come_from_the_contract(self):
        kit = self.kit("down")
        self.assertEqual(kit.root, kit_module.DEFAULT_ROOT)
        self.assertEqual(kit.lemond_url, sc.DEFAULT_LEMOND_URL)
        self.assertEqual(sc.DEFAULT_LEMOND_URL, "http://127.0.0.1:13305")
        self.assertEqual(kit.whisper_model, "base")
        self.assertEqual(kit.mode, "record")
        self.assertEqual(self.kit("down", "--whisper-model", "tiny").whisper_model, "tiny")

    def test_a_model_flag_that_differs_from_the_staged_pin_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / kit_module.KIT_STATE).parent.mkdir(parents=True, exist_ok=True)
            (Path(root) / kit_module.KIT_STATE).write_text(
                json.dumps({"whisper_model": "base", "chat_model": "chat"})
            )
            with self.assertRaisesRegex(ValueError, "--whisper-model differs from the staged base"):
                self.kit("trial", "--root", root, "--whisper-model", "tiny")
            with self.assertRaisesRegex(ValueError, "--chat-model differs from the staged chat"):
                self.kit("trial", "--root", root, "--chat-model", "other")
            kit = self.kit("trial", "--root", root, "--whisper-model", "base", "--chat-model", "chat")
            self.assertEqual((kit.whisper_model, kit.chat_model), ("base", "chat"))
            self.assertEqual(self.kit("trial", "--root", root).whisper_model, "base")

    def test_the_slice_defaults_to_the_kit_slice(self):
        self.assertEqual(self.kit("down").slice, "owui-acc.slice")

    def test_the_slice_must_be_a_plain_slice_unit_name(self):
        self.assertEqual(self.kit("up", "--slice", "builds-owui_acc.slice").slice, "builds-owui_acc.slice")
        for bad in ("builds", "builds.service", "-.slice", "-builds.slice", "builds-.slice", "a--b.slice",
                    "a@b.slice", "../x.slice", "a/b.slice", "a b.slice", ".slice"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit, msg=bad) as raised:
                kit_module.parser().parse_args(["up", "--slice", bad])
            self.assertEqual(raised.exception.code, 2, bad)

    def test_a_shared_parent_slice_is_refused(self):
        for shared in ("builds.slice", "app.slice", "user.slice", "owui_acc.slice", "-.slice"):
            with self.subTest(shared=shared), self.assertRaises(SystemExit), \
                    contextlib.redirect_stderr(io.StringIO()) as error:
                kit_module.parser().parse_args(["up", f"--slice={shared}"])
            self.assertIn(shared, error.getvalue())
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / kit_module.KIT_STATE).write_text(json.dumps({"slice": "builds.slice"}))
            with self.assertRaisesRegex(ValueError, "builds.slice"):
                self.kit("down", "--root", root)

    def test_the_staged_slice_is_read_back_and_a_different_one_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            staged = self.kit("stage", "--root", root, "--slice", "builds-owui_acc.slice")
            (Path(root) / kit_module.KIT_STATE).write_text(json.dumps(kit_module.staged_pins(staged)))
            for command in ("up", "down", "trial", "resmoke", "teardown"):
                self.assertEqual(self.kit(command, "--root", root).slice, "builds-owui_acc.slice")
            self.assertEqual(self.kit("up", "--root", root, "--slice", "builds-owui_acc.slice").slice,
                             "builds-owui_acc.slice")
            with self.assertRaisesRegex(ValueError, "--slice differs from the staged builds-owui_acc.slice"):
                self.kit("up", "--root", root, "--slice", "owui-acc.slice")

    def test_a_root_staged_before_the_slice_option_keeps_the_default(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / kit_module.KIT_STATE).write_text(json.dumps({"whisper_model": "base"}))
            self.assertEqual(self.kit("up", "--root", root).slice, "owui-acc.slice")

    def test_the_stub_and_the_rehearsal_go_together(self):
        with self.assertRaises(ValueError):
            self.kit("preflight", "--provider", "stub")
        with self.assertRaises(ValueError):
            self.kit("preflight", "--rehearsal")
        with self.assertRaises(ValueError):
            self.kit("preflight", "--provider", "stub", "--rehearsal", "--lemond-url", "http://127.0.0.1:13305")
        kit = self.kit("trial", "--provider", "stub", "--rehearsal")
        self.assertEqual(kit.mode, "rehearsal")
        self.assertEqual(kit.lemond_url, kit_module.STUB_URL)
        self.assertEqual(kit.chat_model, "household-chat-stub-v1")

    def test_the_chat_model_defaults_to_the_owner_pin_with_lemonade(self):
        for command in ("up", "trial", "resmoke"):
            self.assertEqual(self.kit(command).chat_model, "user.Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL")
        self.assertEqual(self.kit("trial", "--chat-model", "chat").chat_model, "chat")

    def test_a_bad_combination_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                kit_module.main(["preflight", "--provider", "stub"])
        self.assertEqual(raised.exception.code, 2)


class OverlayTests(unittest.TestCase):
    def test_overlay_stays_inside_the_allowlist_in_both_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            write_candidate_tree(directory)
            for rehearsal in (False, True):
                kit = make_kit(directory, rehearsal=rehearsal)
                env = kit.effective_env()
                overlay = kit.overlay()
                self.assertLessEqual(set(overlay), sc.overlay_allowlist(env))
                self.assertEqual(overlay["QDRANT_URI"], "http://127.0.0.1:16333")
                self.assertEqual(overlay["RAG_EXTERNAL_RERANKER_URL"], "http://127.0.0.1:13306/api/v1/rerank")
                # The provider connection is the rendered profile's, never the overlay's.
                for key in ("ENABLE_OLLAMA_API", "ENABLE_OPENAI_API", "OPENAI_API_BASE_URLS", "OPENAI_API_KEYS",
                            "RAG_OPENAI_API_BASE_URL"):
                    self.assertNotIn(key, overlay)
                self.assertEqual({**env, **overlay}["OPENAI_API_KEYS"], "")
                self.assertNotIn("HF_HUB_OFFLINE", overlay)
                self.assertNotIn("WHISPER_MODEL", overlay)
                state = str(Path(directory) / "state" / "open-webui")
                for key, value in overlay.items():
                    if "/" in value and not value.startswith("http"):
                        self.assertIn(state, value, key)
                        self.assertNotIn("/var/lib/open-webui", value, key)

    def test_the_rendered_profile_points_the_provider_at_lemonade_or_the_stub(self):
        with tempfile.TemporaryDirectory() as directory:
            write_candidate_tree(directory)
            for rehearsal, origin in ((False, "http://127.0.0.1:13305"), (True, "http://127.0.0.1:23305")):
                kit = make_kit(directory, rehearsal=rehearsal)
                env = {**kit.effective_env(), **kit.overlay()}
                with self.subTest(kit.mode):
                    self.assertEqual(
                        {key: env[key] for key in ("ENABLE_OLLAMA_API", "ENABLE_OPENAI_API", "OPENAI_API_BASE_URLS",
                                                   "OPENAI_API_KEYS", "RAG_OPENAI_API_BASE_URL")},
                        {"ENABLE_OLLAMA_API": "false", "ENABLE_OPENAI_API": "true",
                         "OPENAI_API_BASE_URLS": f"{origin}/api/v1", "OPENAI_API_KEYS": "",
                         "RAG_OPENAI_API_BASE_URL": f"{origin}/api/v1"},
                    )
                    # The profile names the reranker at the provider; the overlay relays it.
                    self.assertEqual(kit.profile_env()["RAG_EXTERNAL_RERANKER_URL"], f"{origin}/api/v1/rerank")
                    self.assertEqual(env["RAG_EXTERNAL_RERANKER_URL"], "http://127.0.0.1:13306/api/v1/rerank")
                    self.assertIsNone(kit_module.provider_mismatch(kit, kit.effective_env()))
            rehearsal, record = make_kit(directory, rehearsal=True), make_kit(directory)
            self.assertEqual((rehearsal.lemond_host, rehearsal.lemond_port), ("127.0.0.1", 23305))
            self.assertEqual((record.lemond_host, record.lemond_port), ("127.0.0.1", 13305))

    def test_the_vanilla_env_alone_has_no_model_peer_and_no_reranker(self):
        # Without a profile, as when the unit's "-" skips a missing one, Open
        # WebUI has no model connection and the RAG gate has no reranker to
        # qualify, so document RAG stays closed.  The kit never starts that way.
        env = packaged_env()
        self.assertEqual((env["ENABLE_OLLAMA_API"], env["ENABLE_OPENAI_API"]), ("false", "false"))
        self.assertEqual(env["RAG_RERANKING_ENGINE"], "external")
        for key in ("RAG_RERANKING_MODEL", "RAG_EXTERNAL_RERANKER_URL", "RAG_EMBEDDING_ENGINE",
                    "RAG_OPENAI_API_BASE_URL", "OPENAI_API_BASE_URLS"):
            self.assertNotIn(key, env)
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            self.assertIn("ENABLE_OPENAI_API", kit_module.provider_mismatch(kit, env) or "")


class HouseholdProfileTests(unittest.TestCase):
    """The trial's household profile: the candidate's example, rendered for the kit's provider."""

    def test_rendering_fills_only_the_provider_origin(self):
        example = PROFILE_EXAMPLE.read_text(encoding="utf-8")
        # The lines the operator's grep -nE '^[^#]*<[a-z]+>' prints for the example.
        self.assertEqual(sc.profile_placeholder_lines(example), [25, 32, 54])
        rendered = sc.render_household_profile(example, "http://lemond-host:13400/")
        self.assertEqual(sc.profile_placeholder_lines(rendered), [])
        self.assertNotIn("<lemond>", rendered)
        profile = sc.parse_env_file(rendered)
        self.assertEqual(profile["OPENAI_API_BASE_URLS"], "http://lemond-host:13400/api/v1")
        self.assertEqual(profile["RAG_EXTERNAL_RERANKER_URL"], "http://lemond-host:13400/api/v1/rerank")
        # The origin lines stay commented, and the zembed markers are not placeholders.
        self.assertNotIn("WEBUI_URL", profile)
        self.assertEqual(profile["RAG_EMBEDDING_QUERY_PREFIX"], sc.ZEMBED_QUERY_HEAD)
        self.assertEqual(profile["RAG_EMBEDDING_CONTENT_PREFIX"], sc.ZEMBED_DOCUMENT_HEAD)

    def test_a_placeholder_left_after_rendering_is_refused(self):
        example = PROFILE_EXAMPLE.read_text(encoding="utf-8") + "WEBUI_URL=https://<name>.<tailnet>.ts.net\n"
        with self.assertRaisesRegex(ValueError, "placeholders on lines 67$"):
            sc.render_household_profile(example, sc.DEFAULT_LEMOND_URL)
        self.assertEqual(sc.profile_placeholder_lines("# x=<lemond>\nA=<b>\nB=<|im_end|>\n"), [2])
        with self.assertRaises(ValueError):
            sc.render_household_profile("A=<lemond>\n", "lemond-host:13305")

    def rendered_root(self, directory):
        kit = make_kit(directory)
        write_candidate_tree(directory)
        kit.profile_path.parent.mkdir(parents=True, exist_ok=True)
        kit.profile_path.write_text(kit.rendered_profile())
        return kit

    def test_every_start_needs_the_rendered_profile(self):
        # The unit reads the profile with "-", so without this check a missing
        # profile would start vanilla and the first start would persist that.
        with tempfile.TemporaryDirectory() as directory:
            kit = self.rendered_root(directory)
            good = kit.profile_path.read_text()
            cases = {
                "missing": None,
                "placeholder": good + "WEBUI_URL=https://<name>.<tailnet>.ts.net\n",
                "drifted": good.replace("zerank-2-GGUF", "another-reranker"),
            }
            for name, text in cases.items():
                with self.subTest(name):
                    if text is None:
                        kit.profile_path.unlink()
                    else:
                        kit.profile_path.write_text(text)
                    with mock.patch.object(kit_module, "systemctl") as systemctl, \
                            mock.patch.object(kit_module, "require_lemond_ready") as ready, \
                            self.assertRaises(sc.Blocked):
                        kit_module.start_open_webui(kit)
                    systemctl.assert_not_called()
                    ready.assert_not_called()
            kit.profile_path.write_text(good)
            kit_module.require_rendered_profile(kit)

    def test_the_rehearsal_units_serve_the_profile_models_from_the_stub(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory, rehearsal=True)
            write_candidate_tree(directory)
            unit = kit.path("tree", "qdrant", "usr", "lib", "systemd", "system", "qdrant.service")
            unit.parent.mkdir(parents=True)
            unit.write_text(QDRANT_UNIT.read_text())
            units = kit_module.render_units(kit)
            stub = units[kit_module.UNITS["stub"]]
            self.assertIn("--embedding-model zembed-1-Q4_K_M-GGUF-Q4_K_M --reranking-model zerank-2-GGUF", stub)
            self.assertIn(f"EnvironmentFile=-{kit.root}/etc/household.env", units[kit_module.UNITS["open-webui"]])
            self.assertEqual(kit.profile_env()["OPENAI_API_BASE_URLS"], "http://127.0.0.1:23305/api/v1")

    def test_the_trial_refuses_a_missing_profile_before_it_spends_the_one_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = write_manifest(directory, six_archives(f"{directory}/inputs"))
            kit = make_kit(directory)
            kit.manifest_path = staged
            (kit.root / kit_module.MARKER).write_text("marker\n")
            kit.raw.mkdir(parents=True)
            (kit.raw / "first-start.json").write_text(json.dumps({"started_at": 1.0}))
            kit.save_state(mode="record", manifest={"sha256": kit_module.load_manifest(staged)["sha256"]})
            args = kit_module.parser().parse_args(["trial", "--lemonade-receipt", "r"])
            with mock.patch.object(kit_module, "unit_active", return_value=True), \
                    mock.patch.object(kit_module, "require_lemond_ready") as ready, \
                    self.assertRaisesRegex(sc.Blocked, "rendered household profile"):
                kit_module.cmd_trial(kit, args)
            ready.assert_not_called()
            self.assertNotIn("trial_started", kit.state())

    def test_the_production_expectation_comes_from_the_profile_example(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = self.rendered_root(directory)
            kit.save_state(archives=[{"name": "open-webui-0.11.4-1-x86_64.pkg.tar.zst", "sha256": "a" * 64}])
            expectation = kit_module.production_expectation_for(kit)
            assert expectation is not None
            self.assertEqual(expectation["entry"]["RAG_EMBEDDING_MODEL"], "zembed-1-Q4_K_M-GGUF-Q4_K_M")
            self.assertEqual(expectation["entry"]["RAG_RERANKING_MODEL"], "zerank-2-GGUF")
            self.assertEqual(expectation["entry"]["RAG_EMBEDDING_QUERY_PREFIX"], sc.ZEMBED_QUERY_HEAD)
            (kit.root / "tree" / "open-webui" / sc.HOUSEHOLD_EXAMPLE).unlink()
            self.assertIsNone(kit_module.production_expectation_for(kit))

    def test_the_candidate_fixture_is_the_0_11_4_package_files(self):
        # The digests the 0.11.4-1 PKGBUILD pins for these three sources.
        pinned = {
            "open-webui.env": "b039eb10d67a8f59e3749296e57b895d1a36ed4f769fb1b56bcaa2aeb55aaeb3",
            "household.env.example": "cc6f1e164e36e814778d1d0d441d2801b21f02401107ed0a875aa58cee308177",
            "open-webui.service": "634e7f16c6ccf1e0e994e48adb978e8235d194153742ed73493be5851bf1b9be",
        }
        self.assertEqual({name: kit_module.sha256_file(CANDIDATE / name) for name in pinned}, pinned)

    @unittest.skipUnless((REPO_ROOT / "packages" / "open-webui" / "household.env.example").is_file(),
                         "the in-tree open-webui package predates the household profile split")
    def test_the_candidate_fixture_matches_the_in_tree_package(self):
        for name in ("open-webui.env", "household.env.example", "open-webui.service"):
            with self.subTest(name):
                self.assertEqual((CANDIDATE / name).read_bytes(),
                                 (REPO_ROOT / "packages" / "open-webui" / name).read_bytes())


class UnitDerivationTests(unittest.TestCase):
    def test_every_packaged_service_property_is_classified(self):
        for path in (OPEN_WEBUI_UNIT, QDRANT_UNIT):
            for section, key, _ in kit_module.parse_unit(path.read_text()):
                status, _ = kit_module.classify_property(section, key)
                self.assertIn(
                    status,
                    {kit_module.KEEP, kit_module.REWRITTEN, kit_module.DROPPED, kit_module.UNENFORCED},
                    (section, key),
                )
        with self.assertRaises(ValueError):
            kit_module.classify_property("Service", "DynamicUser")

    def test_open_webui_unit_is_derived_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            text, rows = kit_module.open_webui_unit(kit, OPEN_WEBUI_UNIT.read_text())
            lines = kit_module.parse_unit(text)
            keys = [key for _, key, _ in lines]
            values = {(key, value) for _, key, value in lines}
            for dropped in ("User", "Group", "SupplementaryGroups", "StateDirectory", "RuntimeDirectory",
                            "ExecStartPre", "ReadWritePaths", "ProtectHome", "PrivateTmp", "RestrictRealtime"):
                self.assertNotIn(dropped, keys)
            self.assertIn(("Slice", "owui-acc.slice"), values)
            # The packaged env, then the optional profile (the kit's rendering,
            # still optional), then the overlay, which wins.
            files = [value for _, key, value in lines if key == "EnvironmentFile"]
            self.assertEqual(
                files,
                [str(kit.root / "tree/open-webui/etc/open-webui/open-webui.env"), f"-{kit.root}/etc/household.env",
                 str(kit.root / "etc/acceptance.env")],
            )
            environment_rows = [row for row in rows if row["property"] == "EnvironmentFile"]
            self.assertEqual([(row["packaged"], row["acceptance"]) for row in environment_rows], [
                ("/etc/open-webui/open-webui.env",
                 [f"EnvironmentFile={kit.root}/tree/open-webui/etc/open-webui/open-webui.env"]),
                ("-/etc/open-webui/household.env", [f"EnvironmentFile=-{kit.root}/etc/household.env"]),
            ])
            # The unit's profile read guard is dropped with the privileged
            # steps; the kit checks its rendered profile itself.
            guard = [row for row in rows if row["property"] == "ExecStartPre"
                     and "/etc/open-webui/household.env" in row["packaged"]]
            self.assertEqual([row["status"] for row in guard], [kit_module.DROPPED])
            self.assertNotIn("household.env exists but", text)
            encrypted = sorted(value.split(":", 1)[0] for _, key, value in lines if key == "LoadCredentialEncrypted")
            self.assertEqual(encrypted, sorted(kit_module.OPEN_WEBUI_SECRETS))
            self.assertIn(("LoadCredential", f"session-epoch:{kit.root}/ledger/current"), values)
            exec_start = next(value for _, key, value in lines if key == "ExecStart")
            self.assertIn(f"--ro-bind {kit.root}/tree/open-webui/opt/open-webui /opt/open-webui", exec_start)
            self.assertIn(f"serve --uds {kit.root}/run/owui-acc/open-webui.sock", exec_start)
            self.assertIn(("IPAddressDeny", "any"), values)
            self.assertIn(("Environment", "HF_HUB_OFFLINE=1"), values)
            self.assertIn(("Environment", "WHISPER_MODEL=base"), values)
            by_property = {}
            for row in rows:
                by_property.setdefault(row["property"], []).append(row["status"])
            self.assertEqual(set(by_property["User"]), {kit_module.DROPPED})
            self.assertEqual(set(by_property["ExecStartPre"]), {kit_module.DROPPED})
            self.assertEqual(set(by_property["IPAddressDeny"]), {kit_module.UNENFORCED})
            self.assertEqual(set(by_property["WorkingDirectory"]), {kit_module.REWRITTEN})
            self.assertNotIn("Restart", by_property)

    def test_qdrant_unit_keeps_the_packaged_config_and_moves_only_paths_and_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            text, rows = kit_module.qdrant_unit(kit, QDRANT_UNIT.read_text())
            lines = kit_module.parse_unit(text)
            values = {(key, value) for _, key, value in lines}
            exec_start = next(value for _, key, value in lines if key == "ExecStart")
            self.assertTrue(exec_start.endswith(f"--config-path {kit.root}/tree/qdrant/etc/qdrant/config.yaml"))
            self.assertIn(("Environment", "QDRANT__SERVICE__HTTP_PORT=16333"), values)
            self.assertIn(("Environment", "QDRANT__SERVICE__GRPC_PORT=16334"), values)
            self.assertIn(("Environment", f"QDRANT__STORAGE__TEMP_PATH={kit.root}/state/qdrant/tmp"), values)
            self.assertIn(("LoadCredentialEncrypted", f"qdrant-admin-key:{kit.root}/credstore/qdrant-admin-key.cred"), values)
            self.assertNotIn("EnvironmentFile", [key for _, key, _ in lines])
            self.assertIn(("MemoryMax", "90%"), values)
            dropped = {row["property"] for row in rows if row["status"] == kit_module.DROPPED}
            self.assertLessEqual({"ExecStartPre", "MemoryDenyWriteExecute", "ProtectProc", "SystemCallFilter"}, dropped)

    def test_the_plaintext_fallback_is_used_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory, route="plaintext-0400")
            text, _ = kit_module.open_webui_unit(kit, OPEN_WEBUI_UNIT.read_text())
            lines = kit_module.parse_unit(text)
            self.assertNotIn("LoadCredentialEncrypted", [key for _, key, _ in lines])
            self.assertIn(("LoadCredential", f"webui-secret-key:{kit.root}/credstore/webui-secret-key"),
                          {(key, value) for _, key, value in lines})

    def test_every_unit_and_the_stop_commands_use_the_chosen_slice(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory, rehearsal=True)
            kit.slice = "builds-owui_acc.slice"
            texts = [
                kit_module.open_webui_unit(kit, OPEN_WEBUI_UNIT.read_text())[0],
                kit_module.qdrant_unit(kit, QDRANT_UNIT.read_text())[0],
                kit_module.kit_unit(kit, "valkey", "valkey", "/usr/bin/valkey-server x"),
            ]
            for text in texts:
                slices = [value for _, key, value in kit_module.parse_unit(text) if key == "Slice"]
                self.assertEqual(slices, ["builds-owui_acc.slice"])
            (kit.root / kit_module.MARKER).write_text("marker\n")
            (kit.root / "kit.json").write_text(json.dumps({"mode": "rehearsal"}))
            for command in ("down", "teardown"):
                with mock.patch.object(kit_module, "systemctl") as systemctl, \
                        mock.patch.object(kit_module, "snapshot_resources"), \
                        contextlib.redirect_stdout(io.StringIO()):
                    kit_module.COMMANDS[command](kit, kit_module.parser().parse_args([command]))
                self.assertIn(mock.call("stop", "builds-owui_acc.slice", check=False), systemctl.call_args_list)
                self.assertNotIn(mock.call("stop", "owui-acc.slice", check=False), systemctl.call_args_list)
                stopped = [call.args[1] for call in systemctl.call_args_list if call.args[0] == "stop"]
                self.assertLessEqual(set(stopped), {"builds-owui_acc.slice", kit_module.UNITS["caddy"]})

    def test_every_transient_systemd_run_uses_the_chosen_slice(self):
        class Launched(Exception):
            pass

        launched = []

        def fake_run(command, **_kwargs):
            if command[0] == "systemd-run":
                launched.append(command)
                if len(launched) == 1:
                    raise Launched  # commissioning goes on to talk to Open WebUI
            return subprocess.CompletedProcess(command, 0, stdout=b"probe")

        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            kit.slice = "builds-owui_acc.slice"
            (kit.root / kit_module.MARKER).write_text("marker\n")
            with mock.patch.object(kit_module, "run", side_effect=fake_run):
                with self.assertRaises(Launched):
                    kit_module.Trial(kit).commission()
                self.assertTrue(kit_module.probe_systemd_creds(kit.slice))
            with mock.patch.object(kit_module.subprocess, "run", side_effect=fake_run):
                kit_module.cmd_resmoke(kit, kit_module.parser().parse_args(["resmoke"]))
        self.assertEqual(len(launched), 3)
        for command in launched:
            payload = next(index for index, arg in enumerate(command) if index and not arg.startswith("-"))
            self.assertIn("--slice=builds-owui_acc.slice", command[1:payload])

    def test_no_kit_unit_sets_an_oom_score(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory, rehearsal=True)
            texts = [
                kit_module.open_webui_unit(kit, OPEN_WEBUI_UNIT.read_text())[0],
                kit_module.qdrant_unit(kit, QDRANT_UNIT.read_text())[0],
                kit_module.kit_unit(kit, "valkey", "valkey", "/usr/bin/valkey-server x"),
            ]
            for text in texts:
                self.assertNotIn("OOMScoreAdjust", text)
            with self.assertRaisesRegex(ValueError, "OOMScoreAdjust"):
                kit_module.classify_property("Service", "OOMScoreAdjust")

    def test_every_unit_keeps_home_caches_and_temp_under_the_root(self):
        contained = ("HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "TORCH_HOME", "HF_HOME", "TMPDIR")
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory, rehearsal=True)
            texts = [
                kit_module.open_webui_unit(kit, OPEN_WEBUI_UNIT.read_text())[0],
                kit_module.qdrant_unit(kit, QDRANT_UNIT.read_text())[0],
                kit_module.kit_unit(kit, "valkey", "valkey", "/usr/bin/valkey-server x"),
            ]
            for text in texts:
                lines = kit_module.parse_unit(text)
                environment = dict(value.split("=", 1) for _, key, value in lines if key == "Environment")
                for key in contained:
                    self.assertTrue(environment[key].startswith(str(kit.root)), (key, environment[key]))
                self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
                working = next(value for _, key, value in lines if key == "WorkingDirectory")
                self.assertTrue(working.startswith(str(kit.root)))

    def test_public_rows_present_credentials_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            _, rows = kit_module.open_webui_unit(kit, OPEN_WEBUI_UNIT.read_text())
            public = kit_module.publicize(kit_module.public_credential_rows(rows), kit.replacements())
            v1.assert_public_safe(public)
            text = json.dumps(public)
            self.assertIn("qdrant-runtime-api-key <- <root>/credstore/qdrant-runtime-api-key.cred", text)
            self.assertNotIn(str(kit.root), text)


class PreflightTests(unittest.TestCase):
    def test_locate_archive_picks_the_store_file_with_the_pinned_bytes(self):
        name = CANDIDATE_ARCHIVES[0]
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            write_archive(kit.candidate_store / "3647a6f", name, b"superseded")
            record = write_archive(kit.candidate_store / "dd9a307", name, b"record bytes")
            self.assertEqual(kit_module.locate_archive(kit, record), kit.candidate_store / "dd9a307" / name)
            stale = {**record, "sha256": "0" * 64}
            self.assertEqual(kit_module.locate_archive(kit, stale), kit.candidate_store / "3647a6f" / name)

    def test_root_refusals(self):
        refuse = kit_module.root_refusals
        free = 400 * 1024**3
        self.assertEqual(refuse(Path("/srv/build/arch-pkgs-owui-acceptance"), 17, free), [])
        for root in ("/home/someone/acc", "/tmp/acc", "/var/tmp/acc", "/home"):
            self.assertTrue(refuse(Path(root), 10, free), root)
        self.assertTrue(refuse(Path("/data/acc"), 80, free))
        self.assertEqual(refuse(Path("/data/acc"), 79, free), [])
        self.assertTrue(refuse(Path("/srv/acc"), 10, 1024**3))
        # 50 GB at 79% passes the use check alone, but the ~6 GiB footprint
        # would take it to about 92%, past Qdrant's 85% quota.
        total, used = 50 * 10**9, 395 * 10**8
        use = kit_module.df_use_percent(total, used, total - used)
        self.assertEqual(use, 79)
        self.assertTrue(any("projected" in item for item in refuse(Path("/data/acc"), use, total - used, used)))
        self.assertEqual(refuse(Path("/data/acc"), 17, 400 * 1024**3, 80 * 1024**3), [])
        self.assertEqual(kit_module.df_use_percent(100, 79, 21), 79)
        self.assertEqual(kit_module.df_use_percent(100, 791, 209), 80)

    def test_manifest_must_pin_exactly_the_six_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            archives = six_archives(directory)
            bound = write_archive(directory, "python-ctranslate2-4.8.2-1-x86_64.pkg.tar.zst")
            manifest = kit_module.load_manifest(write_manifest(directory, archives + [{**bound, "deployed": False}]))
            self.assertEqual([item["package"] for item in manifest["deployed"]], list(kit_module.DEPLOYED_PACKAGES))
            self.assertEqual(manifest["bound_not_deployed"][0]["package"], "python-ctranslate2")
            for broken in (
                archives[:-1],
                archives + [archives[0]],
                archives + [{**write_archive(directory, "hayhooks-1.18.0-1-any.pkg.tar.zst"), "deployed": False}],
                archives[:-1] + [{**archives[-1], "sha256": "not-a-digest"}],
            ):
                with self.assertRaises(ValueError):
                    kit_module.load_manifest(write_manifest(directory, broken))
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"archives": archives}))
            with self.assertRaises(ValueError):
                kit_module.load_manifest(path)

    def test_archives_are_checked_by_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            record = write_archive(directory, "qdrant-1.19.1-1-x86_64.pkg.tar.zst", b"exact")
            path = Path(directory) / record["name"]
            self.assertEqual(kit_module.verify_archive(path, record)["sha256"], record["sha256"])
            with self.assertRaises(ValueError):
                kit_module.verify_archive(path, {**record, "size": 6})
            with self.assertRaises(ValueError):
                kit_module.verify_archive(path, {**record, "sha256": "0" * 64})
            link = Path(directory) / "link.pkg.tar.zst"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                kit_module.verify_archive(link, record)

    def test_sync_database_digests_parse(self):
        text = (
            "%FILENAME%\ncaddy-2.10.2-1-x86_64.pkg.tar.zst\n\n%NAME%\ncaddy\n\n%SHA256SUM%\n" + "a" * 64 + "\n\n"
            "%FILENAME%\npython-antlr4-4.13.2-1-any.pkg.tar.zst\n\n%SHA256SUM%\n" + "b" * 64 + "\n"
        )
        self.assertEqual(
            kit_module.sync_db_digests(text),
            {"caddy-2.10.2-1-x86_64.pkg.tar.zst": "a" * 64, "python-antlr4-4.13.2-1-any.pkg.tar.zst": "b" * 64},
        )

    def run_preflight(self, directory, *, health, models, legacy=True, store=True, lemond_url=None):
        kit = make_kit(directory)
        if lemond_url:
            kit.lemond_url = lemond_url
        archives = six_archives(kit.root / "store") if store else [
            {"name": name, "size": 1, "sha256": "0" * 64} for name in CANDIDATE_ARCHIVES
        ]
        kit.manifest_path = write_manifest(directory, archives)
        kit.root = Path("/srv/build/owui-acceptance-preflight-test")
        legacy_path = Path(directory) / ("opt-open-webui" if legacy else "absent")
        if legacy:
            legacy_path.mkdir()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(kit_module, "filesystem_usage",
                                                  return_value=(17, 400 * 1024**3, 80 * 1024**3)))
            stack.enter_context(mock.patch.object(kit_module.shutil, "which", return_value="/usr/bin/tool"))
            stack.enter_context(mock.patch.object(kit_module, "host_package_version", return_value="1-1"))
            stack.enter_context(mock.patch.object(kit_module, "port_in_use", return_value=False))
            stack.enter_context(mock.patch.object(kit_module, "LEGACY_OPT", legacy_path))
            stack.enter_context(mock.patch.object(kit_module, "candidate_env_from_archive",
                                                  side_effect=lambda _archive, url: candidate_env(url)))
            snapshot = stack.enter_context(mock.patch.object(sc, "lemond_snapshot", return_value=(health, models)))
            report, refusals = kit_module.preflight_facts(kit, probe_only=True)
        snapshot.assert_called_once()
        return report, refusals

    def served(self, *extra):
        env = candidate_env()
        ids = [env["RAG_EMBEDDING_MODEL"], env["RAG_RERANKING_MODEL"], "resident-chat", *extra]
        return {"data": [{"id": item} for item in ids]}, {"all_models_loaded": [{"model_name": item} for item in ids]}

    def test_preflight_passes_when_every_model_is_resident(self):
        models, health = self.served()
        with tempfile.TemporaryDirectory() as directory:
            report, refusals = self.run_preflight(directory, health=health, models=models)
        self.assertEqual(refusals, [])
        self.assertEqual(sorted(report["archives"].values()), ["ok"] * 6)

    def test_readiness_accepts_the_bare_listing_of_a_user_prefixed_chat_model(self):
        env = candidate_env()
        ids = [env["RAG_EMBEDDING_MODEL"], env["RAG_RERANKING_MODEL"], "Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL"]
        models = {"data": [{"id": item} for item in ids]}
        health = {"all_models_loaded": [{"model_name": item} for item in ids]}
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            kit.chat_model = sc.DEFAULT_CHAT_MODEL
            with mock.patch.object(kit_module.Kit, "effective_env", return_value=env), \
                    mock.patch.object(sc, "lemond_snapshot", return_value=(health, models)):
                kit_module.require_lemond_ready(kit)

    def test_preflight_refuses_instead_of_loading_a_model(self):
        models, _ = self.served()
        env = candidate_env()
        health = {"all_models_loaded": [{"model_name": env["RAG_EMBEDDING_MODEL"]}]}
        with tempfile.TemporaryDirectory() as directory:
            _, refusals = self.run_preflight(directory, health=health, models=models)
        self.assertTrue(any(item.startswith("NEEDS LEAD: Lemonade has not loaded") for item in refusals), refusals)

    def test_preflight_refuses_missing_pins_and_a_missing_mount_point(self):
        models, health = self.served()
        with tempfile.TemporaryDirectory() as directory:
            _, refusals = self.run_preflight(directory, health=health, models=models, legacy=False, store=False)
        self.assertTrue(any("missing pinned archive" in item for item in refusals), refusals)
        self.assertTrue(any("/opt/open-webui" in item or "absent" in item for item in refusals), refusals)

    def test_another_provider_origin_is_rendered_into_the_profile(self):
        models, health = self.served()
        with tempfile.TemporaryDirectory() as directory:
            report, refusals = self.run_preflight(directory, health=health, models=models,
                                                  lemond_url="http://127.0.0.1:13400")
        self.assertEqual(refusals, [])
        self.assertEqual(report["profile_models"], ["zembed-1-Q4_K_M-GGUF-Q4_K_M", "zerank-2-GGUF"])

    def test_a_profile_that_points_elsewhere_than_the_provider_is_refused(self):
        # A provider URL with a path is not the origin the profile renders, so
        # the kit would check one Lemonade while Open WebUI talks to another.
        models, health = self.served()
        with tempfile.TemporaryDirectory() as directory:
            _, refusals = self.run_preflight(directory, health=health, models=models,
                                             lemond_url="http://127.0.0.1:13305/lemonade")
        self.assertTrue(any("do not point Open WebUI at --lemond-url (OPENAI_API_BASE_URLS, RAG_OPENAI_API_BASE_URL)"
                            in item for item in refusals), refusals)
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            kit.lemond_url = "http://127.0.0.1:13400"
            elsewhere = candidate_env("http://127.0.0.1:13305")
            with mock.patch.object(kit_module.Kit, "effective_env", return_value=elsewhere), \
                    mock.patch.object(sc, "lemond_snapshot") as snapshot:
                with self.assertRaisesRegex(sc.Blocked, "RAG_EXTERNAL_RERANKER_URL"):
                    kit_module.require_lemond_ready(kit)
            snapshot.assert_not_called()
            write_candidate_tree(directory)
            kit.profile_path.parent.mkdir(parents=True)
            kit.profile_path.write_text(kit.rendered_profile())
            (kit.root / kit_module.MARKER).write_text("marker\n")
            (kit.root / "kit.json").write_text(json.dumps({"mode": "record", "credential_route": "systemd-creds",
                                                           "commissioned": False}))
            args = kit_module.parser().parse_args(["trial", "--root", directory, "--chat-model", "resident-chat",
                                                   "--lemond-url", "http://127.0.0.1:13400"])
            with mock.patch.object(kit_module, "kit_from_args", return_value=kit), \
                    mock.patch.object(kit_module.Kit, "effective_env", return_value=elsewhere), \
                    mock.patch.object(kit_module, "unit_active", return_value=True), \
                    contextlib.redirect_stderr(io.StringIO()):
                (kit.root / "evidence" / "raw").mkdir(parents=True)
                (kit.root / "evidence" / "raw" / "first-start.json").write_text("{}")
                kit.manifest_path = write_manifest(directory, six_archives(f"{directory}/inputs"))
                kit.save_state(manifest={"sha256": kit_module.load_manifest(kit.manifest_path)["sha256"]})
                code = kit_module.main(["trial", "--root", directory, "--chat-model", "resident-chat",
                                        "--lemonade-receipt", "r", "--lemond-url", "http://127.0.0.1:13400"])
            self.assertEqual(code, sc.EXIT_PRECONDITION)
            self.assertNotIn("trial_started", kit.state())
        self.assertEqual(args.lemond_url, "http://127.0.0.1:13400")

    def test_the_trial_checks_the_manifest_before_it_spends_the_one_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = write_manifest(directory, six_archives(f"{directory}/inputs"))
            kit = make_kit(directory)
            (kit.root / kit_module.MARKER).write_text("marker\n")
            kit.raw.mkdir(parents=True)
            (kit.raw / "first-start.json").write_text(json.dumps({"started_at": 1.0}))
            kit.save_state(mode="record", manifest={"sha256": kit_module.load_manifest(staged)["sha256"]})
            other = Path(directory) / "other"
            other.mkdir()
            different = write_manifest(other, six_archives(f"{directory}/other-inputs"), note="other")
            args = kit_module.parser().parse_args(["trial", "--lemonade-receipt", "r"])
            for manifest, pattern in ((None, "--manifest is required"), (different, "differs from the one staged")):
                kit.manifest_path = manifest
                with mock.patch.object(kit_module, "unit_active", return_value=True), \
                        mock.patch.object(kit_module, "require_lemond_ready") as ready, \
                        self.assertRaisesRegex(sc.Blocked, pattern):
                    kit_module.cmd_trial(kit, args)
                ready.assert_not_called()
                self.assertNotIn("trial_started", kit.state())

    def test_a_repeated_up_keeps_the_first_start_record(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            (kit.root / kit_module.MARKER).write_text("marker\n")
            kit.save_state(mode="record")
            kit.raw.mkdir(parents=True)
            storage = kit.path("state", "qdrant", "storage")
            storage.mkdir(parents=True)
            qdrant = mock.Mock()
            times = iter([1.0, 2.0, 3.0, 4.0])
            with mock.patch.object(kit_module, "install_units"), mock.patch.object(kit_module, "systemctl"), \
                    mock.patch.object(kit_module, "start_qdrant", return_value=qdrant), \
                    mock.patch.object(kit_module, "start_open_webui", return_value=7.5), \
                    mock.patch.object(kit_module, "snapshot_resources"), \
                    mock.patch.object(kit_module.time, "time", side_effect=lambda: next(times)), \
                    contextlib.redirect_stdout(io.StringIO()):
                kit_module.cmd_up(kit, kit_module.parser().parse_args(["up"]))
                first = (kit.raw / "first-start.json").read_text()
                (storage / "collection").mkdir()
                kit_module.cmd_up(kit, kit_module.parser().parse_args(["up"]))
            self.assertEqual((kit.raw / "first-start.json").read_text(), first)
            self.assertTrue(json.loads(first)["qdrant_fresh"])
            # Each pre-commission up asks Qdrant for missing collections.
            self.assertEqual(qdrant.create_collections.call_count, 2)

    def test_an_up_after_a_refused_first_up_still_records_fresh_qdrant(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            (kit.root / kit_module.MARKER).write_text("marker\n")
            kit.save_state(mode="record")
            kit.raw.mkdir(parents=True)
            storage = kit.path("state", "qdrant", "storage")
            storage.mkdir(parents=True)
            qdrant = mock.Mock()
            qdrant.create_collections.side_effect = lambda: (storage / "collection").mkdir(exist_ok=True)
            starts = iter([sc.Blocked("NEEDS LEAD: a model is not loaded"), 7.5])

            def start(*_args, **_kwargs):
                outcome = next(starts)
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

            with mock.patch.object(kit_module, "install_units"), mock.patch.object(kit_module, "systemctl"), \
                    mock.patch.object(kit_module, "start_qdrant", return_value=qdrant), \
                    mock.patch.object(kit_module, "start_open_webui", side_effect=start), \
                    mock.patch.object(kit_module, "snapshot_resources"), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(sc.Blocked):
                    kit_module.cmd_up(kit, kit_module.parser().parse_args(["up"]))
                self.assertFalse((kit.raw / "first-start.json").exists())
                kit_module.cmd_up(kit, kit_module.parser().parse_args(["up"]))
            self.assertTrue(json.loads((kit.raw / "first-start.json").read_text())["qdrant_fresh"])
            self.assertEqual(qdrant.create_collections.call_count, 2)

    def test_qdrant_creates_only_the_collections_and_indexes_it_does_not_report(self):
        qdrant = kit_module.Qdrant(16333, "admin")
        full, bare = kit_module.COLLECTIONS[0], kit_module.COLLECTIONS[1]
        schema = {index["field_name"]: {} for index in kit_module.PAYLOAD_INDEXES}

        def get(method, path, token=None, **_kw):
            self.assertEqual((method, token), ("GET", "admin"))
            name = path.split("/")[-1]
            if name == full:
                return mock.Mock(status=200, json=lambda: {"result": {"payload_schema": schema}})
            if name == bare:
                return mock.Mock(status=200, json=lambda: {"result": {"payload_schema": {}}})
            return mock.Mock(status=404, json=lambda: None)

        calls = []
        with mock.patch.object(qdrant.endpoint, "request", side_effect=get), \
                mock.patch.object(qdrant, "call", side_effect=lambda method, path, payload=None: calls.append(path)):
            qdrant.create_collections()
        created = [path.split("/")[2] for path in calls if path.count("/") == 2]
        self.assertEqual(created, list(kit_module.COLLECTIONS[2:]))
        indexed = [path.split("/")[2] for path in calls if "/index" in path]
        per_collection = len(kit_module.PAYLOAD_INDEXES)
        # The fully indexed collection is left alone; the bare one gets only its indexes.
        self.assertEqual(indexed, [bare] * per_collection + [name for name in created for _ in range(per_collection)])
        # A GET that is not 200 (such as 401 or 503) never counts as present.
        calls.clear()
        with mock.patch.object(qdrant.endpoint, "request", return_value=mock.Mock(status=503, json=lambda: None)), \
                mock.patch.object(qdrant, "call", side_effect=lambda method, path, payload=None: calls.append(path)):
            qdrant.create_collections()
        self.assertEqual(len([path for path in calls if path.count("/") == 2]), len(kit_module.COLLECTIONS))

    def test_unit_active_since_reads_the_user_managers_activation_time(self):
        with mock.patch.object(kit_module, "systemctl", return_value="@1789564995") as systemctl:
            self.assertEqual(kit_module.unit_active_since("owui-acc-open-webui.service"), 1789564995.0)
        self.assertIn("--timestamp=unix", systemctl.call_args.args)
        self.assertIn("--property=ActiveEnterTimestamp", systemctl.call_args.args)
        with mock.patch.object(kit_module, "systemctl", return_value=""):
            self.assertIsNone(kit_module.unit_active_since("owui-acc-open-webui.service"))

    def test_an_unset_runtime_dir_is_a_precondition(self):
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()) as error:
            code = kit_module.main(["preflight", "--root", "/nonexistent-owui-acc-root"])
        self.assertEqual(code, sc.EXIT_PRECONDITION)
        self.assertIn("XDG_RUNTIME_DIR", error.getvalue())

    def test_cli_preflight_exits_75_on_a_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            with mock.patch.object(kit_module, "preflight_facts", return_value=({}, ["NEEDS LEAD: x"])):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = kit_module.cmd_preflight(kit, kit_module.parser().parse_args(["preflight"]))
        self.assertEqual(code, sc.EXIT_PRECONDITION)

    def test_reentry_refuses_when_a_model_was_unloaded(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            models, health = self.served()
            health = {"all_models_loaded": health["all_models_loaded"][:2]}
            with mock.patch.object(sc, "lemond_snapshot", return_value=(health, models)), \
                    mock.patch.object(kit_module.Kit, "effective_env", return_value=candidate_env()), \
                    mock.patch.object(kit_module, "effective_models",
                                      return_value=(candidate_env()["RAG_EMBEDDING_MODEL"], candidate_env()["RAG_RERANKING_MODEL"])):
                with self.assertRaises(sc.Blocked):
                    kit_module.require_lemond_ready(kit)

    def test_a_damaged_anchor_stops_the_restore_before_live_state_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            anchor = kit.anchor
            (anchor / "data").mkdir(parents=True)
            (anchor / "data" / "webui.db").write_bytes(b"db")
            (anchor / "credstore").mkdir()
            (anchor / "credstore" / "webui-secret-key").write_bytes(b"k")
            (anchor / "dump.rdb").write_bytes(b"rdb")
            (anchor / "qdrant").mkdir()
            for name in kit_module.COLLECTIONS:
                (anchor / "qdrant" / f"{name}.snapshot").write_bytes(name.encode())
            record = {
                "data_digest": kit_module.tree_digest(anchor / "data"),
                "rdb_sha256": kit_module.sha256_file(anchor / "dump.rdb"),
                "credstore_digest": kit_module.tree_digest(anchor / "credstore"),
                "snapshot_bytes": {name: len(name.encode()) for name in kit_module.COLLECTIONS},
                "snapshot_sha256": {name: kit_module.sha256_file(anchor / "qdrant" / f"{name}.snapshot")
                                    for name in kit_module.COLLECTIONS},
            }
            (anchor / "anchor.json").write_text(json.dumps(record))
            kit_module.verify_anchor(kit)
            damaged = anchor / "qdrant" / f"{kit_module.COLLECTIONS[2]}.snapshot"
            damaged.write_bytes(damaged.read_bytes()[::-1])
            with self.assertRaisesRegex(sc.ScenarioFailure, "live state is unchanged"):
                kit_module.verify_anchor(kit)
            (anchor / "dump.rdb").write_bytes(b"other")
            with self.assertRaisesRegex(sc.ScenarioFailure, "dump.rdb"):
                kit_module.verify_anchor(kit)
            (anchor / "dump.rdb").write_bytes(b"rdb")
            damaged.write_bytes(damaged.read_bytes()[::-1])
            kit_module.verify_anchor(kit)
            # restore_tuple's copytree would follow a symlink that tree_digest skips.
            (anchor / "credstore" / "extra").symlink_to(anchor / "dump.rdb")
            with self.assertRaisesRegex(sc.ScenarioFailure, "credstore \\(symlink\\)"):
                kit_module.verify_anchor(kit)
            (anchor / "credstore" / "extra").unlink()
            # A symlinked tree root is refused too, not only symlinks below it.
            (anchor / "credstore").rename(anchor / "credstore.real")
            (anchor / "credstore").symlink_to(anchor / "credstore.real")
            with self.assertRaisesRegex(sc.ScenarioFailure, "credstore \\(symlink\\)"):
                kit_module.verify_anchor(kit)
            (anchor / "credstore").unlink()
            (anchor / "credstore.real").rename(anchor / "credstore")
            # A malformed anchor.json is a ScenarioFailure, so cleanup always runs.
            saved = (anchor / "anchor.json").read_text()
            (anchor / "anchor.json").write_text("{not json")
            with self.assertRaisesRegex(sc.ScenarioFailure, "cannot be read"):
                kit_module.verify_anchor(kit)
            (anchor / "anchor.json").write_text(saved)
            # An anchor without snapshot digests cannot prove its snapshots.
            del record["snapshot_sha256"]
            (anchor / "anchor.json").write_text(json.dumps(record))
            with self.assertRaisesRegex(sc.ScenarioFailure, "snapshot"):
                kit_module.verify_anchor(kit)
        # Both drills and a revive verify before they change or remove anything.
        source = KIT.read_text(encoding="utf-8")
        restore = source[source.index("    def restore_drill"):source.index("    def rollback_drill")]
        self.assertLess(restore.index("backup_anchor(kit, qdrant)"), restore.index("verify_anchor(kit)"))
        self.assertLess(restore.index("verify_anchor(kit)"), restore.index('"DELETE"'))
        rollback = source[source.index("    def rollback_drill"):]
        self.assertLess(rollback.index("verify_anchor(kit)"), rollback.index("remove_tree(kit.tree)"))

    def test_a_failed_anchor_check_restarts_what_the_restore_drill_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            trial = kit_module.Trial(kit, {})
            with mock.patch.object(kit_module, "systemctl") as systemctl, \
                    mock.patch.object(kit_module, "admin_token", return_value="t"), \
                    mock.patch.object(kit_module, "valkey_command"), \
                    mock.patch.object(kit_module, "valkey_password", return_value="p"), \
                    mock.patch.object(kit_module.Kit, "qdrant"), \
                    mock.patch.object(kit_module, "backup_anchor", return_value={}), \
                    mock.patch.object(kit_module, "verify_anchor", side_effect=sc.ScenarioFailure("damaged")), \
                    mock.patch.object(kit_module, "start_open_webui") as start_webui, \
                    mock.patch.object(kit_module, "start_caddy") as start_caddy, \
                    mock.patch.object(kit_module.Kit, "uds") as uds:
                with self.assertRaisesRegex(sc.ScenarioFailure, "damaged"):
                    trial.restore_drill()
            start_webui.assert_called_once()
            start_caddy.assert_called_once()
            self.assertIn(mock.call("start", kit_module.UNITS["valkey"]), systemctl.call_args_list)
            uds.return_value.request.assert_not_called()

    def test_keep_anchor_teardown_then_up_rerenders_every_etc_file(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            root = kit.root
            state = {"mode": "record", "credential_route": "systemd-creds", "commissioned": True}
            (root / kit_module.MARKER).write_text("marker\n")
            (root / "kit.json").write_text(json.dumps(state))
            for name in ("etc", "tree", "credstore", "state", "evidence/raw", "ledger", "inputs",
                         "backups/anchor/credstore"):
                (root / name).mkdir(parents=True, exist_ok=True)
            (root / "backups" / "anchor" / "anchor.json").write_text(json.dumps({"archives": []}))
            (root / "etc" / "Caddyfile").write_text("old")

            def fake_tree(_kit, _archives):
                write_candidate_tree(root)
                unit = root / "tree" / "qdrant" / "usr" / "lib" / "systemd" / "system" / QDRANT_UNIT.name
                unit.parent.mkdir(parents=True)
                unit.write_text(QDRANT_UNIT.read_text())

            args = kit_module.parser().parse_args(["teardown", "--keep-anchor", "--evidence-out", f"{directory}/out"])
            with mock.patch.object(kit_module, "systemctl"), contextlib.redirect_stdout(io.StringIO()):
                kit_module.cmd_teardown(kit, args)
            self.assertEqual(
                sorted(item.name for item in root.iterdir()),
                sorted([kit_module.MARKER, "backups", "inputs", "kit.json", "ledger"]),
            )
            with mock.patch.object(kit_module, "restage_trees", side_effect=fake_tree), \
                    mock.patch.object(kit_module, "place_whisper"), \
                    mock.patch.object(kit_module, "valkey_password", return_value="valkey-password"):
                kit_module.revive_from_anchor(kit)
                units = kit_module.render_units(kit)
            referenced = set()
            for text in units.values():
                referenced.update(re.findall(re.escape(str(root / "etc")) + r"/[\w.-]+", text))
            self.assertEqual(
                {Path(item).name for item in referenced},
                {"household.env", "acceptance.env", "Caddyfile", "valkey-open-webui.conf", "qdrant-credential-shim"},
            )
            for item in referenced:
                self.assertTrue(Path(item).is_file(), item)
            self.assertEqual((root / "etc" / "household.env").read_text(), kit.rendered_profile())
            kit_module.require_rendered_profile(kit)
            acl = (root / "etc" / "valkey-open-webui.acl").read_text()
            self.assertIn(sc.valkey_password_hash("valkey-password"), acl)
            self.assertNotIn("valkey-password", acl)
            self.assertEqual((root / "etc" / "valkey-open-webui.acl").stat().st_mode & 0o777, 0o600)

    def plaintext_root(self, directory, mode="record"):
        kit = make_kit(directory, rehearsal=mode == "rehearsal")
        root = kit.root
        (root / kit_module.MARKER).write_text("marker\n")
        (root / "kit.json").write_text(json.dumps({"mode": mode, "credential_route": "plaintext-0400"}))
        for name in ("etc", "tree", "state", "ledger", "inputs", "backups/anchor"):
            (root / name).mkdir(parents=True, exist_ok=True)
        (root / "backups" / "anchor" / "anchor.json").write_text(json.dumps({"archives": []}))
        (root / "credstore").mkdir(mode=0o700)
        kit.store_credential("webui-secret-key", "test-only")
        kit_module.shutil.copytree(root / "credstore", root / "backups" / "anchor" / "credstore")
        return kit

    def teardown(self, kit, *flags):
        args = kit_module.parser().parse_args(["teardown", *flags, "--evidence-out", f"{kit.root}/out"])
        with mock.patch.object(kit_module, "systemctl"), contextlib.redirect_stdout(io.StringIO()):
            return kit_module.cmd_teardown(kit, args)

    def test_keep_anchor_refuses_plaintext_credentials_without_the_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = self.plaintext_root(directory)
            with self.assertRaisesRegex(sc.Blocked, "--keep-plaintext-credentials"):
                self.teardown(kit, "--keep-anchor")
            self.assertTrue((kit.root / "state").is_dir())

    def test_the_opt_in_keeps_test_only_0400_credentials_and_up_restores_them_in_the_same_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = self.plaintext_root(directory)
            os.chmod(kit.anchor / "credstore", 0o755)
            self.assertEqual(self.teardown(kit, "--keep-anchor", "--keep-plaintext-credentials"), sc.EXIT_PASS)
            kept = kit.anchor / "credstore"
            self.assertFalse(kit.credstore.exists())
            self.assertEqual(kept.stat().st_mode & 0o777, 0o700)
            self.assertEqual(kept.stat().st_uid, os.getuid())
            self.assertEqual((kept / "webui-secret-key").stat().st_mode & 0o777, 0o400)
            with mock.patch.object(kit_module, "restage_trees"), mock.patch.object(kit_module, "place_whisper"), \
                    mock.patch.object(kit_module, "render_etc"), mock.patch.object(kit_module, "create_state_directories"):
                kit_module.revive_from_anchor(kit)
            self.assertEqual(kit.credential_route(), "plaintext-0400")
            self.assertEqual(kit.credential_directive("webui-secret-key"),
                             ("LoadCredential", f"webui-secret-key:{kit.credstore}/webui-secret-key"))
            self.assertEqual(kit.read_credential("webui-secret-key"), "test-only")
            self.assertEqual(kit.credstore.stat().st_mode & 0o777, 0o700)
            self.assertEqual((kit.credstore / "webui-secret-key").stat().st_mode & 0o777, 0o400)

    def test_the_opt_in_without_keep_anchor_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as runtime, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}), \
                contextlib.redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit) as raised:
            kit_module.main(["teardown", "--root", runtime, "--keep-plaintext-credentials"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--keep-anchor", error.getvalue())

    def test_a_rehearsal_ignores_the_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = self.plaintext_root(directory, mode="rehearsal")
            self.assertEqual(self.teardown(kit, "--keep-anchor", "--keep-plaintext-credentials"), sc.EXIT_PASS)
            self.assertFalse(kit.root.exists())

    def test_a_rehearsal_root_refuses_resmoke(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory, rehearsal=True)
            (kit.root / kit_module.MARKER).write_text("marker\n")
            (kit.root / "kit.json").write_text(json.dumps({"mode": "rehearsal"}))
            with mock.patch.object(kit_module.subprocess, "run") as run:
                with self.assertRaises(sc.Blocked):
                    kit_module.cmd_resmoke(kit, kit_module.parser().parse_args(["resmoke"]))
            run.assert_not_called()
            self.assertFalse((kit.root / "evidence").exists())

    def test_teardown_removes_only_marked_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            args = kit_module.parser().parse_args(["teardown", "--keep-anchor"])
            with self.assertRaises(sc.Blocked):
                kit_module.cmd_teardown(kit, args)
            (kit.root / kit_module.MARKER).write_text("marker\n")
            (kit.root / "kit.json").write_text(json.dumps({"mode": "record", "credential_route": "plaintext-0400"}))
            with self.assertRaises(sc.Blocked):
                kit_module.cmd_teardown(kit, args)
            self.assertTrue(kit.root.is_dir())


class InputTests(unittest.TestCase):
    FILES = {"config.json": b"{}", "model.bin": b"weights", "tokenizer.json": b"tok", "vocabulary.txt": b"voc"}

    def pinned(self, kit):
        source = kit.root / "inputs" / "faster-whisper-base"
        source.mkdir(parents=True)
        for name, data in self.FILES.items():
            (source / name).write_bytes(data)
        (source / "README.md").write_text("not pinned")
        pin = {
            "repository": "Systran/faster-whisper-base",
            "revision": "f" * 40,
            "files": {name: v1._sha256_bytes(data) for name, data in self.FILES.items()},
        }
        return source, {"base": pin}

    def test_the_whisper_snapshot_is_placed_offline_from_its_pinned_files_only(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            _, pins = self.pinned(kit)
            cache = Path(directory) / "whisper"
            with mock.patch.object(sc, "WHISPER_PINS", pins), \
                    mock.patch.object(kit_module, "whisper_dir", return_value=cache):
                kit_module.place_whisper(kit)
            base = cache / "models--Systran--faster-whisper-base"
            snapshot = base / "snapshots" / ("f" * 40)
            self.assertEqual(sorted(item.name for item in snapshot.iterdir()), sorted(self.FILES))
            self.assertEqual((base / "refs" / "main").read_text(), "f" * 40)

    def test_any_pinned_whisper_file_that_differs_or_is_missing_is_refused(self):
        for damage in ("tamper", "remove"):
            with tempfile.TemporaryDirectory() as directory:
                kit = make_kit(directory)
                source, pins = self.pinned(kit)
                if damage == "tamper":
                    (source / "tokenizer.json").write_bytes(b"other")
                else:
                    (source / "tokenizer.json").unlink()
                with mock.patch.object(sc, "WHISPER_PINS", pins), \
                        mock.patch.object(kit_module, "whisper_dir", return_value=Path(directory) / "whisper"):
                    with self.assertRaisesRegex(sc.Blocked, "tokenizer.json"):
                        kit_module.place_whisper(kit)
                self.assertFalse((Path(directory) / "whisper").exists())

    def test_the_host_providers_of_record_are_identified_with_their_foreign_flag(self):
        listing = {
            ("pacman", "-Qq"): b"python-sentence-transformers\npython-pytorch-opt-rocm-gfx1151\n"
                               b"python-onnxruntime-opt-rocm\npython-pytorch\nzsh\n",
            ("pacman", "-Qqm"): b"python-sentence-transformers\n",
        }

        def fake_run(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, stdout=listing[tuple(command)])

        def identity(name):
            return {"package": name, "source": "host", "version": "5.7.0-1"}

        with mock.patch.object(kit_module, "run", side_effect=fake_run), \
                mock.patch.object(kit_module, "host_package_identity", side_effect=identity):
            record = kit_module.providers_of_record()
        by_name = {item["package"]: item for item in record["packages"]}
        self.assertEqual(
            sorted(by_name),
            ["python-onnxruntime-opt-rocm", "python-pytorch-opt-rocm-gfx1151", "python-sentence-transformers"],
        )
        self.assertTrue(by_name["python-sentence-transformers"]["foreign"])
        self.assertFalse(by_name["python-pytorch-opt-rocm-gfx1151"]["foreign"])
        self.assertIn("python-faster-whisper", record["absent"])
        self.assertIn("knowingly-foreign providers of record", record["note"])
        v1.assert_public_safe(record)

    def test_host_installed_supporting_packages_are_preferred_and_identified(self):
        info = (
            "Name            : caddy\nVersion         : 2.10.2-1\nArchitecture    : x86_64\n"
            "Packager        : Someone <someone@example.org>\nBuild Date      : Mon 01 Sep 2026\n"
            "Install Reason  : Installed as a dependency for another package\n"
        ).encode()
        with mock.patch.object(kit_module, "run",
                               return_value=subprocess.CompletedProcess([], 0, stdout=info)):
            identity = kit_module.host_package_identity("caddy")
        self.assertEqual(identity, {
            "package": "caddy", "source": "host", "version": "2.10.2-1", "architecture": "x86_64",
            "build_date": "Mon 01 Sep 2026", "install_reason": "Installed as a dependency for another package",
        })
        with mock.patch.object(kit_module, "run", return_value=subprocess.CompletedProcess([], 1, stdout=b"")):
            self.assertIsNone(kit_module.host_package_identity("caddy"))
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            host = {package: {"package": package, "source": "host", "version": "1-1"}
                    for package in kit_module.SUPPORTING_PACKAGES}
            with mock.patch.object(kit_module, "host_package_identity", side_effect=host.get), \
                    mock.patch.object(kit_module, "extract") as extract:
                records = kit_module.verify_supporting(kit)
            extract.assert_not_called()
            self.assertEqual(records, [host[package] for package in kit_module.SUPPORTING_PACKAGES])
            self.assertEqual(kit.caddy_binary(), Path("/usr/bin/caddy"))


class ProductionDocTests(unittest.TestCase):
    doc = (REPO_ROOT / "docs" / "maintainers" / "open-webui-household-production-install.md").read_text()

    def test_the_production_acl_is_the_kit_template(self):
        printf = re.search(r"printf '(user default off\\nuser open-webui [^']*)'", self.doc)
        assert printf is not None
        rendered = sc.render_valkey_acl("0" * 64).replace("0" * 64, "%s")
        self.assertEqual(printf.group(1).replace("\\n", "\n"), rendered)

    def test_the_production_drop_in_carries_the_speech_settings(self):
        for key, value in sc.speech_environment().items():
            self.assertIn(f"Environment={key}={value}", self.doc)
        self.assertNotIn("inputs/whisper/", self.doc)

    def test_both_runbooks_carry_the_base_whisper_pin(self):
        pin = sc.whisper_pin_record(sc.DEFAULT_WHISPER_MODEL)
        self.assertIn(f"rev={pin['revision']}", self.doc)
        for name, digest in pin["files"].items():
            self.assertIn(f"| `{name}` | `{digest}` |", self.doc)
            self.assertIn(f'"$src/{name}"', self.doc)
        acceptance = (REPO_ROOT / "docs" / "maintainers" / "open-webui-household-acceptance.md").read_text(encoding="utf-8")
        self.assertIn(f"`{pin['revision']}`", acceptance)
        for name, digest in pin["files"].items():
            self.assertIn(f"| `{name}` | `{digest}` |", acceptance)
        self.assertIn(f"`{sc.JFK_FLAC_SHA256}`", acceptance)

    def test_the_acceptance_runbook_quotes_the_kit_conditions_and_reads_lemonade_state(self):
        acceptance = (REPO_ROOT / "docs" / "maintainers" / "open-webui-household-acceptance.md").read_text(encoding="utf-8")
        flat = " ".join(acceptance.split())
        for condition in (kit_module.CREDENTIAL_FALLBACK_CONDITION, kit_module.LEMONADE_RESTART_CONDITION):
            self.assertIn(condition, flat)
        reads = re.findall(r"^systemctl show (.*)$", acceptance, re.MULTILINE)
        self.assertEqual(len(reads), 2)
        for read in reads:
            for prop in ("-p LoadState", "-p ActiveState", "-p ActiveEnterTimestamp", "--timestamp=unix"):
                self.assertIn(prop, read)

    def test_both_runbooks_name_the_0_11_4_candidate_set(self):
        acceptance = (REPO_ROOT / "docs" / "maintainers" / "open-webui-household-acceptance.md").read_text(encoding="utf-8")
        named = re.findall(r"^   \| `([^`]+\.pkg\.tar\.zst)` \|", acceptance, re.MULTILINE)
        self.assertEqual(sorted(named), sorted(CANDIDATE_ARCHIVES))
        for text in (acceptance, self.doc):
            self.assertNotIn("0.11.0-7", text)
            self.assertNotIn("1.19.0-1", text)
        self.assertIn("`HAND-BACK: open-webui P2 installed 0.11.4-1`", self.doc)
        self.assertIn("`HAND-BACK: qdrant verify PASSED on 1.19.1-1; …`", self.doc)

    def test_the_production_qdrant_loops_name_the_kit_collections(self):
        loops = re.findall(r"for s in ([^;]+); do\n\s*(?:c=|test -s \"\$1/qdrant/)([\w-]+)_\$s", self.doc)
        self.assertEqual(len(loops), 3)
        for suffixes, prefix in loops:
            self.assertEqual(tuple(f"{prefix}_{suffix}" for suffix in suffixes.split()), kit_module.COLLECTIONS)


class LemonadeSafetyTests(unittest.TestCase):
    def test_the_kit_has_no_lemonade_mutation_route(self):
        source = KIT.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"/api/v1/(load|unload|pull|delete|pin|params|install)\b", source))
        self.assertIsNone(re.search(r"(?i)systemctl[^\n]*lemon", source))
        uses = re.findall(r"[^\n]*kit\.lemond\(\)[^\n]*", source)
        self.assertTrue(uses)
        for line in uses:
            self.assertTrue(
                "sc.lemond_snapshot(kit.lemond())" in line or "lemond=kit.lemond()" in line, line
            )
        self.assertEqual(
            set(sc.LEMOND_API.values()),
            {"/api/v1/health", "/api/v1/models", "/api/v1/embeddings", "/api/v1/rerank"},
        )

    def test_a_lemonade_restart_voids_the_run(self):
        restarted = kit_module.lemond_restarted
        self.assertTrue(restarted({"start_time": "a"}, {"start_time": "b"}))
        self.assertFalse(restarted({"start_time": "a"}, {"start_time": "a"}))
        self.assertTrue(restarted({"uptime": 900}, {"uptime": 3}))
        self.assertFalse(restarted({"uptime": 900}, {"uptime": 1200}))
        self.assertIsNone(restarted(None, {"uptime": 1}))
        # A health document with no start time or uptime cannot show a
        # restart, so the result is unknown rather than "no restart".
        self.assertIsNone(restarted({"status": "ok"}, {"status": "ok"}))


class PeerTests(unittest.TestCase):
    listen = {"owui-acc-qdrant.service": frozenset({16333, 16334})}

    def violations(self, samples, allowed):
        return kit_module.peer_violations(samples, allowed_ports=frozenset(allowed), listen_ports=self.listen)

    def test_open_webui_may_reach_only_the_allowed_loopback_peers(self):
        owui = "owui-acc-open-webui.service"
        samples = [
            {"unit": owui, "state": "ESTAB", "local": "127.0.0.1:41000", "peer": "127.0.0.1:13305"},
            {"unit": owui, "state": "ESTAB", "local": "[::1]:41001", "peer": "[::1]:16379"},
            {"unit": "owui-acc-qdrant.service", "state": "ESTAB", "local": "127.0.0.1:16333", "peer": "127.0.0.1:52000"},
            {"unit": owui, "state": "LISTEN", "local": "0.0.0.0:8080", "peer": "0.0.0.0:*"},
        ]
        allowed = {13305, 13306, 16333, 16379}
        self.assertEqual(self.violations(samples, allowed), [])
        ollama = {"unit": owui, "state": "SYN-SENT", "local": "127.0.0.1:41002", "peer": "127.0.0.1:11434"}
        hosted = {"unit": owui, "state": "SYN-SENT", "local": "192.0.2.10:41003", "peer": "203.0.113.5:443"}
        self.assertEqual(self.violations(samples + [ollama, hosted], allowed), [ollama, hosted])
        rehearsal = {23305, 13306, 16333, 16379}
        self.assertEqual(len(self.violations(samples, rehearsal)), 1)

    def test_listener_findings(self):
        lines = [
            'LISTEN 0 4096 127.0.0.1:18443 0.0.0.0:* users:(("caddy",pid=10,fd=3))',
            'LISTEN 0 4096 *:18443 *:* users:(("caddy",pid=10,fd=4))',
            'LISTEN 0 2048 127.0.0.1:8080 0.0.0.0:* users:(("python",pid=20,fd=5))',
        ]
        findings = kit_module.listener_findings(lines, {20}, 18443)
        self.assertEqual(len(findings), 2)
        self.assertEqual(kit_module.listener_findings(lines[:1], {20}, 18443), [])


class CredentialTests(unittest.TestCase):
    def test_ported_qdrant_constants_match_the_merged_cutover_route(self):
        script = (REPO_ROOT / "tools" / "qdrant_production_cutover.zsh").read_text(encoding="utf-8")

        def compact(value):
            return json.dumps(value, separators=(",", ":"))

        def found(pattern, flags=re.MULTILINE):
            match = re.search(pattern, script, flags)
            self.assertIsNotNone(match, pattern)
            assert match is not None
            return match.group(1)

        self.assertIn(f"local body='{compact(dict(kit_module.COLLECTION_BODY))}'", script)
        self.assertIn(f"'{compact(kit_module.PAYLOAD_INDEXES[0])}'", script)
        keyword = compact(kit_module.PAYLOAD_INDEXES[1]["field_schema"]).replace('"', '\\"')
        self.assertIn(f'\\"field_schema\\":{keyword}', script)
        fields = [index["field_name"] for index in kit_module.PAYLOAD_INDEXES[1:]]
        self.assertIn(f"for field in {' '.join(fields)}; do", script)
        self.assertEqual(kit_module.PAYLOAD_INDEXES[1]["field_schema"], kit_module.PAYLOAD_INDEXES[2]["field_schema"])
        prefix = found(r"^collection_prefix=(\S+)$")
        suffixes = found(r"^collection_suffixes=\((.*)\)$").split()
        self.assertEqual(kit_module.COLLECTIONS, tuple(f"{prefix}_{suffix}" for suffix in suffixes))
        # The route's own mint, run on a synthetic key, yields the kit's token byte for byte.
        mint = found(r"^mint_jwt\(\) \{.*?<<'PY'\n(.*?)^PY$", re.MULTILINE | re.DOTALL)
        key = "0123456789abcdef" * 4
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / "qdrant.env"
            env.write_text(f"QDRANT__SERVICE__API_KEY={key}\n")
            token = subprocess.run(
                [sys.executable, "-", str(env), "prw", "0", prefix, *suffixes],
                input=mint, capture_output=True, text=True, check=True,
            ).stdout
        self.assertEqual(token, kit_module.mint_jwt(key, "prw"))

    def test_runtime_jwt_is_prw_on_every_collection(self):
        token = kit_module.mint_jwt("a" * 64, "prw")
        claims = kit_module.jwt_claims(token)
        self.assertEqual(
            claims,
            {"access": [{"collection": name, "access": "prw"} for name in kit_module.COLLECTIONS]},
        )
        head, body, signature = token.split(".")
        import base64, hashlib, hmac

        expected = base64.urlsafe_b64encode(
            hmac.new(b"a" * 64, f"{head}.{body}".encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        self.assertEqual(signature, expected)
        self.assertEqual(kit_module.jwt_claims(kit_module.mint_jwt("k", "r", 300, now=1000))["exp"], 1300)

    def test_stored_secret_check_ignores_toggles_and_flags_key_material_in_admin_exports(self):
        env = candidate_env()
        self.assertEqual(kit_module.nonempty_key_paths(env, {"OPENAI_API_KEYS": ""}), [])
        # The nested shapes of Open WebUI 0.11's GET /openai/config and /api/v1/retrieval/config.
        openai = {"ENABLE_OPENAI_API": True, "OPENAI_API_KEYS": [""], "OPENAI_API_CONFIGS": {"0": {}}}
        rag = {"status": True, "ENABLE_RAG_HYBRID_SEARCH": True, "MINERU_API_KEY": "",
               "web": {"ENABLE_WEB_SEARCH": False, "TAVILY_API_KEY": ""}}
        self.assertEqual(kit_module.nonempty_key_paths(openai, rag), [])
        self.assertEqual(
            kit_module.nonempty_key_paths({**rag, "web": {"TAVILY_API_KEY": "tvly-x"}},
                                          {**openai, "OPENAI_API_KEYS": ["", "k"]}),
            ["OPENAI_API_KEYS", "web.TAVILY_API_KEY"],
        )

    def no_stored_secret(self, directory, config):
        """Run the stored-secret check on an Open WebUI 0.11 database holding ``config``.

        Migration 3ff2c63645b8 renames the old ``config(id, data)`` blob table to
        ``config_old`` and creates one ``config`` row per dotted key, the
        ``value`` column holding that key's JSON.
        """

        kit = make_kit(directory)
        if not kit.path("tree").is_dir():
            write_candidate_tree(directory)
        kit.unit_dir.mkdir(parents=True)
        unit, _ = kit_module.open_webui_unit(kit, OPEN_WEBUI_UNIT.read_text())
        (kit.unit_dir / kit_module.UNITS["open-webui"]).write_text(unit)
        data = kit_module.data_dir(kit)
        data.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(data / "webui.db")) as db:
            db.execute("CREATE TABLE config_old (id INTEGER PRIMARY KEY, data JSON NOT NULL, version INTEGER NOT NULL, "
                       "created_at DATETIME NOT NULL, updated_at DATETIME)")
            db.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value JSON NOT NULL, updated_at BIGINT)")
            db.executemany("INSERT INTO config VALUES (?, ?, 0)",
                           [(key, json.dumps(value)) for key, value in config.items()])
            db.commit()
        trial = kit_module.Trial(kit)
        with mock.patch.object(kit_module.Kit, "uds") as uds:
            uds.return_value.json.return_value = {"status": True}
            return trial.no_stored_secret()

    def test_stored_secret_check_passes_on_empty_per_key_config_rows(self):
        config = {
            "openai.enable": True,
            "openai.api_base_urls": [sc.DEFAULT_LEMOND_URL + "/api/v1"],
            "openai.api_keys": [""],
            "openai.api_configs": {"0": {}},
            "rag.openai.api_key": "",
            "rag.external_reranker_api_key": "",
            "auth.enable_api_keys": False,
            "auth.api_key.endpoint_restrictions": False,
            # SQLite stores a JSON number in this column as an INTEGER or REAL.
            "rag.top_k": 3,
            "rag.relevance_threshold": 0.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            values = self.no_stored_secret(directory, config)
        self.assertEqual(values["nonempty_key_fields"], [])

    def test_stored_secret_check_flags_a_secret_in_a_per_key_config_row(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(sc.ScenarioFailure) as raised:
                self.no_stored_secret(directory, {"rag.openai.api_key": "sk-x", "openai.api_keys": [""]})
        self.assertEqual(json.loads(str(raised.exception))["nonempty_key_fields"], ["rag.openai.api_key"])

    def test_stored_secret_check_flags_a_key_in_the_rendered_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            example = write_candidate_tree(directory) / sc.HOUSEHOLD_EXAMPLE
            example.write_text(example.read_text().replace("OPENAI_API_KEYS=\n", "OPENAI_API_KEYS=sk-x\n"))
            with self.assertRaises(sc.ScenarioFailure) as raised:
                self.no_stored_secret(directory, {"openai.api_keys": [""]})
        self.assertEqual(json.loads(str(raised.exception))["nonempty_key_fields"], ["OPENAI_API_KEYS"])


class ProfilePersistedTests(unittest.TestCase):
    """open-webui.acceptance.profile.persisted: the first start stored the profile, not the vanilla values."""

    # What Open WebUI 0.11.4 persists for the rendered example under the
    # acceptance overlay, as JSON config rows: the profile's values parsed as
    # config.py parses them, and the relay's reranker URL.
    PROFILE_ROWS = {
        "openai.enable": True,
        "openai.api_base_urls": ["http://127.0.0.1:13305/api/v1"],
        "openai.api_keys": [""],
        "rag.embedding_engine": "openai",
        "rag.openai.api_base_url": "http://127.0.0.1:13305/api/v1",
        "rag.embedding_model": "zembed-1-Q4_K_M-GGUF-Q4_K_M",
        "rag.embedding_batch_size": 1,
        "rag.embedding_concurrent_requests": 1,
        "rag.reranking_model": "zerank-2-GGUF",
        "rag.external_reranker_url": "http://127.0.0.1:13306/api/v1/rerank",
        "rag.reranking_batch_size": 3,
        "calendar.enable": False,
        "evaluation.arena.enable": False,
        "task.query.retrieval.enable": False,
    }
    # Open WebUI 0.11.4's defaults for the same keys (open_webui/config.py) with
    # the vanilla open-webui.env and the overlay: what a first start without the
    # profile persists.
    VANILLA_ROWS = {
        "openai.enable": False,
        "openai.api_base_urls": ["https://api.openai.com/v1"],
        "openai.api_keys": [""],
        "rag.embedding_engine": "",
        "rag.openai.api_base_url": "https://api.openai.com/v1",
        "rag.embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "rag.embedding_batch_size": 1,
        "rag.embedding_concurrent_requests": 0,
        "rag.reranking_model": "",
        "rag.external_reranker_url": "http://127.0.0.1:13306/api/v1/rerank",
        "rag.reranking_batch_size": 32,
        "calendar.enable": True,
        "evaluation.arena.enable": True,
        "task.query.retrieval.enable": True,
    }

    def persisted(self, directory, rows):
        kit = make_kit(directory)
        if not kit.path("tree").is_dir():
            write_candidate_tree(directory)
        with mock.patch.object(kit_module, "valkey_password", return_value="valkey-password"):
            kit_module.render_etc(kit)
        data = kit_module.data_dir(kit)
        data.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(data / "webui.db")) as db:
            db.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value JSON NOT NULL, updated_at BIGINT)")
            db.executemany("INSERT INTO config VALUES (?, ?, 0)", [(key, json.dumps(value)) for key, value in rows.items()])
            db.commit()
        return kit_module.Trial(kit).profile_persisted()

    def test_a_first_start_with_the_profile_persists_its_values(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.persisted(directory, {**self.PROFILE_ROWS, "ui.default_models": ""})
        self.assertEqual(values["persisted_keys"], sorted([
            "ENABLE_OPENAI_API", "OPENAI_API_BASE_URLS", "OPENAI_API_KEYS", "RAG_EMBEDDING_ENGINE",
            "RAG_OPENAI_API_BASE_URL", "RAG_EMBEDDING_MODEL", "RAG_EMBEDDING_BATCH_SIZE",
            "RAG_EMBEDDING_CONCURRENT_REQUESTS", "RAG_RERANKING_MODEL", "RAG_EXTERNAL_RERANKER_URL",
            "RAG_RERANKING_BATCH_SIZE", "ENABLE_CALENDAR", "ENABLE_EVALUATION_ARENA_MODELS",
            "ENABLE_RETRIEVAL_QUERY_GENERATION",
        ]))
        self.assertEqual(values["overlay_keys"], ["RAG_EXTERNAL_RERANKER_URL"])
        self.assertEqual(values["environment_keys"], ["RAG_EMBEDDING_CONTENT_PREFIX", "RAG_EMBEDDING_QUERY_PREFIX"])
        self.assertEqual((values["absent"], values["mismatched"], values["unclassified"]), ([], [], []))

    def test_vanilla_values_persisted_before_the_profile_existed_fail_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(sc.ScenarioFailure) as raised:
                self.persisted(directory, self.VANILLA_ROWS)
        detail = str(raised.exception)
        recorded = json.loads(detail)
        self.assertEqual(recorded["mismatched"], [
            "ENABLE_CALENDAR", "ENABLE_EVALUATION_ARENA_MODELS", "ENABLE_OPENAI_API",
            "ENABLE_RETRIEVAL_QUERY_GENERATION", "OPENAI_API_BASE_URLS", "RAG_EMBEDDING_CONCURRENT_REQUESTS",
            "RAG_EMBEDDING_ENGINE", "RAG_EMBEDDING_MODEL", "RAG_OPENAI_API_BASE_URL", "RAG_RERANKING_BATCH_SIZE",
            "RAG_RERANKING_MODEL",
        ])
        self.assertEqual(recorded["absent"], [])
        # Names only: no value, persisted or expected, reaches the record,
        # and the record passes the evidence's public-safety check.
        for value in ("zembed", "zerank", "MiniLM", "api.openai.com", "13305", "13306", "true", "false"):
            self.assertNotIn(value, detail.lower())
        v1.assert_public_safe({"detail": detail, "values": recorded})

    def test_a_missing_row_and_an_unknown_profile_key_fail(self):
        rows = {key: value for key, value in self.PROFILE_ROWS.items() if key != "rag.reranking_model"}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(sc.ScenarioFailure) as raised:
                self.persisted(directory, rows)
        self.assertEqual(json.loads(str(raised.exception))["absent"], ["RAG_RERANKING_MODEL"])
        with tempfile.TemporaryDirectory() as directory:
            example = write_candidate_tree(directory) / sc.HOUSEHOLD_EXAMPLE
            example.write_text(example.read_text() + "RAG_TOP_K=5\n")
            with self.assertRaises(sc.ScenarioFailure) as raised:
                self.persisted(directory, self.PROFILE_ROWS)
        self.assertEqual(json.loads(str(raised.exception))["unclassified"], ["RAG_TOP_K"])

    def test_user_credentials_need_the_units_to_load_them_too(self):
        def fake_run(command, **_kwargs):
            if command[0] == "systemd-run":
                raise kit_module.KitError("systemd-run exited 243: Failed to set up credentials")
            return subprocess.CompletedProcess(command, 0, stdout=b"probe" if "decrypt" in command else b"")

        with mock.patch.object(kit_module, "run", side_effect=fake_run):
            self.assertFalse(kit_module.probe_systemd_creds(kit_module.SLICE))
        with mock.patch.object(kit_module, "run",
                               side_effect=lambda command, **_: subprocess.CompletedProcess(command, 0, stdout=b"probe")):
            self.assertTrue(kit_module.probe_systemd_creds(kit_module.SLICE))


class HandbookTests(unittest.TestCase):
    def test_a_failed_handbook_reports_the_error_open_webui_stored_and_is_deleted(self):
        stored = "Unexpected Response: 400 (Bad Request) Limit exceeded 999999999 > 1000 for \"limit\""
        responses = {
            ("POST", sc.API["files"]): {"id": "f1"},
            ("GET", sc.API["file_status"].format(id="f1")): {"status": "failed"},
            ("GET", sc.API["file"].format(id="f1")): {"id": "f1", "data": {"status": "failed", "error": stored}},
            ("DELETE", sc.API["file"].format(id="f1")): {},
        }
        requested = []

        def request(method, path, **_kw):
            requested.append((method, path))
            return sc.Response(200, "application/json", json.dumps(responses[(method, path)]).encode())

        webui = mock.Mock(request=mock.Mock(side_effect=request))
        with self.assertRaises(sc.ScenarioFailure) as raised:
            kit_module.upload_handbook(webui, "t")
        self.assertIn("handbook processing failed", str(raised.exception))
        self.assertIn(stored, str(raised.exception))
        # The error is read before the file goes.
        self.assertEqual(requested[-2:], [("GET", sc.API["file"].format(id="f1")),
                                          ("DELETE", sc.API["file"].format(id="f1"))])
        self.assertTrue(str(raised.exception).endswith("; cleanup: file f1 DELETE returned 200"))

    def test_a_failed_cleanup_delete_is_reported_after_the_processing_error(self):
        # The caller never gets the id, so the failure itself must name the
        # file and say whether the cleanup DELETE removed it.
        for outcome, reported in ((500, "500"), (ConnectionRefusedError(), "ConnectionRefusedError")):
            def request(method, path, _outcome=outcome, **_kw):
                if method == "DELETE":
                    if isinstance(_outcome, BaseException):
                        raise _outcome
                    return sc.Response(_outcome, "application/json", b"{}")
                body = {"id": "f1"} if method == "POST" else {"status": "failed"}
                if path == sc.API["file"].format(id="f1"):
                    body = {"id": "f1", "data": {"status": "failed", "error": "embedding failed"}}
                return sc.Response(200, "application/json", json.dumps(body).encode())

            with self.subTest(reported), self.assertRaises(sc.ScenarioFailure) as raised:
                kit_module.upload_handbook(mock.Mock(request=mock.Mock(side_effect=request)), "t")
            self.assertEqual(str(raised.exception),
                             f"handbook processing failed: embedding failed; cleanup: file f1 DELETE returned {reported}")
            self.assertIsInstance(raised.exception.__cause__, sc.ScenarioFailure)

    def test_a_transport_error_while_waiting_keeps_its_type_in_the_record(self):
        def request(method, path, **_kw):
            if method == "POST":
                return sc.Response(200, "application/json", b'{"id": "f1"}')
            if method == "GET":
                raise TimeoutError("socket read timed out")
            return sc.Response(200, "application/json", b"{}")

        with self.assertRaises(sc.ScenarioFailure) as raised:
            kit_module.upload_handbook(mock.Mock(request=mock.Mock(side_effect=request)), "t")
        self.assertEqual(str(raised.exception),
                         "TimeoutError: socket read timed out; cleanup: file f1 DELETE returned 200")


class GateCheckTests(unittest.TestCase):
    """The closed-gate bypass checks and their qualified counterpart."""

    HANDBOOK = sc.handbook_bytes().decode("utf-8")
    GATE_ERROR = json.dumps({"error": kit_module._rag_unavailable_detail(), "status": 503})

    class FakeOpenWebUI:
        """Open WebUI 0.11.4 as the gate checks see it, with the gate ``closed`` or ``qualified``.

        ``legacy`` maps "mixed" and "all-full" to how their chat answers:
        "refuse" (the gate's 503), "answer" (200 with the whole handbook),
        "wrong-detail" (503 with another detail), or "leak" (the gate's 503
        whose body quotes the handbook).  ``tool_name`` None makes the
        native chat call no tool; ``done_after`` None never finishes it.
        ``tool_name`` and ``answer`` may be lists, one entry per native chat
        completion in order, the last repeating.
        """

        json = sc.Endpoint.json

        def __init__(self, gate="closed", *, health=None, legacy=None,
                     tool_name: str | None | list[str | None] = "view_knowledge_file",
                     tool_output=None, answer=None, delete_status=200, done_after: int | None = 2):
            closed = gate == "closed"
            self.health = list(health or [503 if closed else 200])
            self.legacy = {"mixed": "refuse" if closed else "answer", "all-full": "refuse" if closed else "answer",
                           **(legacy or {})}
            self.tool_name = tool_name
            self.tool_output = tool_output if tool_output is not None else (
                GateCheckTests.GATE_ERROR if closed
                else json.dumps({"id": "f1", "filename": sc.HANDBOOK_NAME, "content": GateCheckTests.HANDBOOK}))
            self.answer = answer if answer is not None else (
                kit_module._rag_unavailable_detail() if closed else sc.CANONICAL_FACT)
            self.delete_status, self.done_after = delete_status, done_after
            self.legacy_chats, self.created, self.completions, self.deleted = [], [], [], []
            self.polls = 0

        def request(self, method, path, *, payload: Any = None, body=None, content_type=None, token=None):
            def reply(value, status=200, kind="application/json"):
                return sc.Response(status, kind, value if isinstance(value, bytes) else json.dumps(value).encode())

            if (method, path) == ("GET", sc.API["rag_health"]):
                status = self.health.pop(0) if len(self.health) > 1 else self.health[0]
                return reply({"status": "qualified"} if status == 200 else {"detail": "closed"}, status)
            if (method, path) == ("POST", sc.API["chat_create"]):
                self.created.append(payload)
                return reply({"id": "c1", "chat": payload["chat"]})
            if (method, path) == ("POST", sc.API["chat"]) and "chat_id" in payload:
                self.completions.append(payload)
                return reply({"status": True, "task_ids": ["t1"], "chat_id": payload["chat_id"]})
            if (method, path) == ("POST", sc.API["chat"]):
                self.legacy_chats.append(payload)
                return self.legacy_reply(payload, reply)
            if (method, path) == ("GET", sc.API["chat_record"].format(id="c1")):
                self.polls += 1
                return reply({"id": "c1", "chat": {"history": {"messages": {self.assistant_id(): self.message()}}}})
            if (method, path) == ("DELETE", sc.API["chat_record"].format(id="c1")):
                self.deleted.append("chat c1")
                return reply(self.delete_status == 200, self.delete_status)
            raise AssertionError(f"unexpected request {method} {path}")

        def legacy_reply(self, payload, reply):
            files = payload["files"]
            kind = self.legacy["mixed" if len(files) == 2 else "all-full"]
            detail = kit_module._rag_unavailable_detail()
            if kind == "refuse":
                return reply({"detail": detail}, 503)
            if kind == "wrong-detail":
                return reply({"detail": "Something else went wrong."}, 503)
            if kind == "leak":
                return reply({"detail": detail, "context": sc.CANONICAL_FACT}, 503)
            source = {"source": {"type": "file", "id": "f1", "name": sc.HANDBOOK_NAME},
                      "document": [GateCheckTests.HANDBOOK], "distances": [1.0]}
            events = [{"sources": [source]}, {"choices": [{"delta": {"content": sc.CANONICAL_FACT}}]}]
            stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
            return reply(stream.encode(), kind="text/event-stream")

        def assistant_id(self):
            return self.completions[-1]["id"]

        def current(self, value):
            """A per-completion setting's value for the latest native chat completion."""

            return value[min(len(self.completions), len(value)) - 1] if isinstance(value, list) else value

        def message(self):
            output = []
            tool_name, answer = self.current(self.tool_name), self.current(self.answer)
            if tool_name:
                output += [
                    {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": tool_name,
                     "arguments": json.dumps({"file_id": "f1"}), "status": "completed"},
                    {"type": "function_call_output", "id": "fco_1", "call_id": "call_1",
                     "output": [{"type": "input_text", "text": self.tool_output}], "status": "completed"},
                ]
            output.append({"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                           "content": [{"type": "output_text", "text": answer}]})
            done = self.done_after is not None and self.polls >= self.done_after
            return {"id": self.assistant_id(), "role": "assistant", "content": answer if done else "",
                    "output": output if done else [], "done": done}

    def run_step(self, name, webui, timeout_s=None):
        with tempfile.TemporaryDirectory() as directory:
            trial = kit_module.Trial(make_kit(directory))
            trial.token, trial.listed_chat_model, trial.seed_file = "t", "chat", "f1"
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(kit_module.Kit, "uds", return_value=webui))
                stack.enter_context(mock.patch.object(kit_module, "NATIVE_CHAT_POLL_S", 0))
                if timeout_s is not None:
                    stack.enter_context(mock.patch.object(kit_module, "NATIVE_CHAT_TIMEOUT_S", timeout_s))
                return getattr(trial, name)()

    def assert_fails(self, name, webui, message=None, **kwargs):
        with self.assertRaises(sc.ScenarioFailure) as raised:
            self.run_step(name, webui, **kwargs)
        if message is not None:
            self.assertIn(message, str(raised.exception))
        return raised.exception

    # failclosed.full-context ----------------------------------------------------
    def test_a_closed_gate_refuses_both_full_context_attachment_sets(self):
        webui = self.FakeOpenWebUI()
        values = self.run_step("full_context", webui)
        refusal = {"status": 503, "fixed_detail": True, "sources": 0, "handbook_text": False}
        self.assertEqual(values["chats"], {"mixed": refusal, "all-full": refusal})
        self.assertEqual((values["health_before"], values["health_after"]), (503, 503))
        full = {"type": "file", "id": "f1", "context": "full"}
        self.assertEqual([chat["files"] for chat in webui.legacy_chats],
                         [[full, {"type": "file", "id": "f1"}], [full]])
        for chat in webui.legacy_chats:
            # No saved chat, session, or native calling: the attachment path alone.
            self.assertFalse({"chat_id", "session_id", "id"} & set(chat))
            self.assertEqual(chat["messages"], [{"role": "user", "content": sc.CITED_ANSWER_PROMPT}])

    def test_each_full_context_bypass_fails_the_closed_check(self):
        cases = {
            # A regression that reads a full-context item before the gate check.
            "all-full answered whole": {"legacy": {"all-full": "answer"}},
            "mixed answered whole": {"legacy": {"mixed": "answer"}},
            "another detail": {"legacy": {"mixed": "wrong-detail"}},
            "handbook text in the refusal": {"legacy": {"all-full": "leak"}},
            "the gate requalified": {"health": [503, 200]},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assert_fails("full_context", self.FakeOpenWebUI(**overrides))

    def test_the_full_context_check_needs_the_latched_gate_first(self):
        webui = self.FakeOpenWebUI(health=[200])
        self.assert_fails("full_context", webui, "health_before")
        self.assertEqual(webui.legacy_chats, [])

    # failclosed.native-tools ----------------------------------------------------
    def test_a_closed_gate_answers_a_ui_style_knowledge_tool_call_with_its_error_only(self):
        webui = self.FakeOpenWebUI()
        values = self.run_step("native_tools", webui)
        self.assertEqual(values["tools_called"], ["view_knowledge_file"])
        self.assertEqual(values["knowledge_tool_outputs"], [self.GATE_ERROR])
        self.assertFalse(values["handbook_text"])
        self.assertEqual(values["mode"], "plain")
        self.assertNotIn("first_attempt", values)
        self.assertEqual(len(webui.completions), 1)
        self.assertEqual((values["health_before"], values["health_after"]), (503, 503))
        # The chat is saved as the frontend saves it, then deleted.
        chat = webui.created[0]["chat"]
        completion = webui.completions[0]
        user, assistant = chat["messages"]
        self.assertEqual(chat["history"]["currentId"], assistant["id"])
        self.assertEqual((user["role"], user["parentId"], user["childrenIds"]), ("user", None, [assistant["id"]]))
        self.assertEqual((assistant["role"], assistant["parentId"], assistant["content"]),
                         ("assistant", user["id"], ""))
        self.assertEqual(completion["chat_id"], "c1")
        self.assertEqual(completion["id"], assistant["id"])
        self.assertTrue(completion["session_id"])
        self.assertEqual(completion["params"], {"function_calling": "native", "temperature": 0})
        self.assertNotIn("tool_choice", completion)
        self.assertNotIn("files", completion)
        self.assertEqual(completion["messages"], [{"role": "user", "content": user["content"]}])
        self.assertIn('Call view_knowledge_file with file_id "f1"', user["content"])
        self.assertEqual(webui.deleted, ["chat c1"])
        self.assertGreaterEqual(webui.polls, 2)

    def test_each_knowledge_tool_counts_and_each_must_return_the_gate_error(self):
        for tool in sorted(kit_module.NATIVE_KNOWLEDGE_TOOLS):
            with self.subTest(tool):
                values = self.run_step("native_tools", self.FakeOpenWebUI(tool_name=tool))
                self.assertEqual(values["knowledge_tool_outputs"], [self.GATE_ERROR])

    def test_a_chat_that_calls_no_knowledge_tool_never_passes(self):
        for tool in (None, "search_notes"):
            with self.subTest(tool):
                webui = self.FakeOpenWebUI(tool_name=tool)
                failure = self.assert_fails("native_tools", webui, "no knowledge tool call observed")
                self.assertIn('"mode": "retried with instruction"', str(failure))
                # One plain attempt and one retry, each chat deleted; never a third.
                self.assertEqual(len(webui.completions), 2)
                self.assertEqual(webui.deleted, ["chat c1", "chat c1"])

    def test_a_plain_attempt_without_a_knowledge_call_retries_once_with_the_instruction(self):
        webui = self.FakeOpenWebUI(tool_name=[None, "view_knowledge_file"])
        values = self.run_step("native_tools", webui)
        self.assertEqual(values["mode"], "retried with instruction")
        self.assertEqual(values["first_attempt"]["tools_called"], [])
        self.assertEqual(values["tools_called"], ["view_knowledge_file"])
        self.assertEqual(values["knowledge_tool_outputs"], [self.GATE_ERROR])
        plain, retried = webui.completions
        self.assertEqual([message["role"] for message in plain["messages"]], ["user"])
        system, user = retried["messages"]
        self.assertEqual(system["role"], "system")
        self.assertIn('call to view_knowledge_file with file_id "f1"', system["content"])
        self.assertEqual(user, plain["messages"][0])
        # The retry is a fresh saved chat, not a second turn in the first.
        self.assertEqual(len(webui.created), 2)
        self.assertNotEqual(plain["id"], retried["id"])
        for completion in (plain, retried):
            self.assertNotIn("tool_choice", completion)
        self.assertEqual(webui.deleted, ["chat c1", "chat c1"])

    def test_a_leak_in_the_plain_attempt_fails_even_when_the_retry_passes(self):
        webui = self.FakeOpenWebUI(tool_name=["search_notes", "view_knowledge_file"],
                                   answer=["The brass key, as the handbook says.", kit_module._rag_unavailable_detail()])
        failure = self.assert_fails("native_tools", webui)
        self.assertIn('"handbook_text": true', str(failure))
        self.assertNotIn(self.HANDBOOK, str(failure))
        self.assertEqual(len(webui.completions), 2)

    def test_each_native_tool_leak_fails_the_closed_check(self):
        handbook = json.dumps({"id": "f1", "content": self.HANDBOOK})
        cases = {
            # A 0005 without the knowledge-tool fix returns the handbook through view_knowledge_file.
            "the tool returns the handbook": {"tool_output": handbook, "answer": sc.CANONICAL_FACT},
            "another tool error": {"tool_output": json.dumps({"error": "File not found"})},
            "the answer carries handbook text": {"answer": "The brass key, as the handbook says."},
            "the gate requalified": {"health": [503, 200]},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                webui = self.FakeOpenWebUI(**overrides)
                failure = self.assert_fails("native_tools", webui)
                self.assertNotIn(self.HANDBOOK, str(failure))
                # A knowledge call that fails the step is never retried away.
                self.assertEqual(len(webui.completions), 1)
                self.assertEqual(webui.deleted, ["chat c1"])

    def test_a_native_chat_that_never_finishes_fails_and_is_still_deleted(self):
        webui = self.FakeOpenWebUI(done_after=None)
        self.assert_fails("native_tools", webui, "timed out waiting for the native-tools chat", timeout_s=0.0)
        self.assertEqual(len(webui.completions), 1)
        self.assertEqual(webui.deleted, ["chat c1"])

    def test_a_failed_native_chat_delete_fails_the_check(self):
        self.assert_fails("native_tools", self.FakeOpenWebUI(delete_status=500), "delete returned 500")

    # gate.explicit-reads --------------------------------------------------------
    def test_a_qualified_gate_allows_every_explicit_read_whole(self):
        webui = self.FakeOpenWebUI("qualified")
        values = self.run_step("explicit_reads", webui)
        read = {"status": 200, "sources": 1, "fact_in_sources": True}
        self.assertEqual(values["chats"], {"mixed": read, "all-full": read})
        self.assertEqual(values["view_knowledge_file_calls"], 1)
        self.assertTrue(values["view_knowledge_file_holds_fact"])
        self.assertEqual(values["mode"], "plain")
        self.assertEqual(webui.deleted, ["chat c1"])
        self.assertNotIn(self.HANDBOOK, json.dumps(values))

    def test_explicit_reads_retry_once_until_view_knowledge_file_is_called(self):
        # Another knowledge tool does not satisfy this step, so it triggers the retry.
        webui = self.FakeOpenWebUI("qualified", tool_name=["query_knowledge_files", "view_knowledge_file"])
        values = self.run_step("explicit_reads", webui)
        self.assertEqual(values["mode"], "retried with instruction")
        self.assertEqual(values["first_attempt"]["tools_called"], ["query_knowledge_files"])
        self.assertTrue(values["view_knowledge_file_holds_fact"])
        self.assertEqual(webui.completions[1]["messages"][0]["role"], "system")
        self.assertEqual(webui.deleted, ["chat c1", "chat c1"])
        self.assertNotIn(self.HANDBOOK, json.dumps(values))

    def test_each_over_gated_explicit_read_fails_the_qualified_check(self):
        cases = {
            # A 0005 without the all-full fix refuses that chat even when qualified.
            "all-full refused": {"legacy": {"all-full": "refuse"}},
            "mixed refused": {"legacy": {"mixed": "refuse"}},
            "the knowledge tool over-gated": {"tool_output": self.GATE_ERROR},
            "no view_knowledge_file call": {"tool_name": "query_knowledge_files"},
            "the gate is still closed": {"health": [503]},
            "the chat delete failed": {"delete_status": 500},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assert_fails("explicit_reads", self.FakeOpenWebUI("qualified", **overrides))

    def test_stored_tool_outputs_pair_by_call_id(self):
        message = {"output": [
            {"type": "function_call", "call_id": "a", "name": "view_file"},
            {"type": "function_call", "call_id": "b", "name": "view_knowledge_file"},
            {"type": "function_call_output", "call_id": "b", "output": [{"type": "input_text", "text": "B"}]},
            {"type": "function_call_output", "call_id": "a", "output": "A"},
            {"type": "message", "content": [{"type": "output_text", "text": "done"}]},
        ]}
        self.assertEqual(kit_module.tool_calls(message), [("view_file", "A"), ("view_knowledge_file", "B")])
        self.assertEqual(kit_module.tool_calls({"output": [{"type": "function_call", "call_id": "c", "name": "x"}]}),
                         [("x", None)])
        self.assertTrue(kit_module.gate_tool_error(self.GATE_ERROR))
        self.assertFalse(kit_module.gate_tool_error(None))
        self.assertFalse(kit_module.gate_tool_error(json.dumps({"error": kit_module._rag_unavailable_detail()})))


class QdrantPagingTests(unittest.TestCase):
    def test_the_paging_corpus_chunks_past_one_scroll_page_and_plants_its_fact_deep(self):
        corpus = kit_module.paging_corpus()
        self.assertEqual(corpus, kit_module.paging_corpus())
        sections = corpus.decode("utf-8").strip("\n").split("\n\n")
        self.assertEqual(len(sections), 1100)
        # Two sections never fit one 1000-character chunk, and none needs a
        # split, so either Open WebUI splitter gives one chunk per section.
        self.assertTrue(all(500 < len(section) < 1000 for section in sections))
        self.assertTrue(all(section.startswith("## ") and "\n\n" not in section for section in sections))
        planted = [number for number, section in enumerate(sections, 1)
                   if "The copper lantern hangs above the north greenhouse door." in section]
        self.assertEqual(planted, [1050])
        filler = "\n".join(section for number, section in enumerate(sections, 1) if number != 1050).lower()
        for word in ("copper", "lantern", "hang", "north", "greenhouse", "door", "where"):
            self.assertNotRegex(filler, rf"\b{word}")
        self.assertLess(len(corpus), 1024 * 1024)
        # Each section's page number is a whitespace token no other section
        # holds, so BM25 alone ranks that section first for it.
        for number, section in enumerate(sections, 1):
            self.assertIn(f"{number:04d}", section.split())
        self.assertEqual([number for number, section in enumerate(sections, 1) if "0417" in section.split()], [417])

    def test_a_tenant_count_is_one_exact_read_only_count_request(self):
        qdrant = kit_module.Qdrant(16333, "admin-key")
        requests = []

        def request(method, path, *, payload=None, token=None, **_kw):
            requests.append((method, path, payload, token))
            return sc.Response(200, "application/json", json.dumps({"result": {"count": 1100}}).encode())

        qdrant.endpoint = mock.Mock(request=mock.Mock(side_effect=request))
        self.assertEqual(qdrant.tenant_points("open-webui-rag-v1_knowledge", "k1"), 1100)
        self.assertEqual(requests, [(
            "POST", "/collections/open-webui-rag-v1_knowledge/points/count",
            {"filter": {"must": [{"key": "tenant_id", "match": {"value": "k1"}}]}, "exact": True},
            "admin-key",
        )])

    PLANTED_CHUNK = "## Ledger page 1050\nThe copper lantern hangs above the north greenhouse door. Ledger page 1050 row 1"
    PLANTED_SOURCES = [{"source": {"type": "collection", "id": "k1"}, "document": [PLANTED_CHUNK],
                        "metadata": [{"name": "household-paging-corpus.md"}], "distances": [0.91]}]
    # The knowledge tenant's first point after one scroll page, in point-id order.
    PAST_PAGE_CHUNK = "## Ledger page 0417\nLedger page 0417 row 1 lists amber basalt birch cedar cobalt and delta."

    class FakeOpenWebUI:
        """Open WebUI as the paging check sees it; ``tenants`` is what Qdrant then holds."""

        json = sc.Endpoint.json

        def __init__(self, *, file_points=1100, knowledge_points=1100, sources=None, hybrid=True, delete_status=200,
                     file_status="completed", trailing=None, bm25_documents=None):
            self.file_points, self.knowledge_points = file_points, knowledge_points
            self.sources = QdrantPagingTests.PLANTED_SOURCES if sources is None else sources
            self.bm25_documents = [QdrantPagingTests.PAST_PAGE_CHUNK] if bm25_documents is None else bm25_documents
            self.queries = []
            self.hybrid, self.delete_status, self.file_status = hybrid, delete_status, file_status
            # Counts Qdrant reports for a tenant before it has applied every point.
            self.trailing = {tenant: list(counts) for tenant, counts in (trailing or {}).items()}
            self.tenants, self.chats, self.deleted = {}, [], []

        def request(self, method, path, *, payload=None, body=None, content_type=None, token=None):
            def reply(value, status=200, kind="application/json"):
                return sc.Response(status, kind, value if isinstance(value, bytes) else json.dumps(value).encode())

            if (method, path) == ("GET", sc.API["rag_config"]):
                return reply({"ENABLE_RAG_HYBRID_SEARCH": self.hybrid, "TEXT_SPLITTER": "", "CHUNK_SIZE": 1000,
                              "CHUNK_OVERLAP": 100, "ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER": True})
            if (method, path) == ("POST", sc.API["files"]):
                self.tenants["file-f1"] = self.file_points
                return reply({"id": "f1"})
            if (method, path) == ("GET", sc.API["file_status"].format(id="f1")):
                return reply({"status": self.file_status})
            if (method, path) == ("GET", sc.API["file"].format(id="f1")):
                return reply({"id": "f1", "data": {"status": self.file_status, "error": "embedding failed"}})
            if (method, path) == ("POST", sc.API["knowledge_create"]):
                return reply({"id": "k1"})
            if (method, path) == ("POST", sc.API["knowledge_file_add"].format(id="k1")):
                self.tenants["k1"] = self.knowledge_points
                return reply({"id": "k1"})
            if (method, path) == ("POST", sc.API["chat"]):
                self.chats.append(payload)
                events = [{"sources": self.sources}, {"choices": [{"delta": {"content": "An answer."}}]}]
                stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
                return reply(stream.encode(), kind="text/event-stream")
            if (method, path) == ("POST", sc.API["retrieval_query_collection"]):
                self.queries.append(payload)
                documents = self.bm25_documents
                return reply({"distances": [[0.5] * len(documents)], "documents": [documents],
                              "metadatas": [[{"name": "household-paging-corpus.md"}] * len(documents)]})
            if (method, path) == ("DELETE", sc.API["knowledge_delete"].format(id="k1")):
                self.deleted.append("knowledge k1")
                return reply({}, self.delete_status)
            if (method, path) == ("DELETE", sc.API["file"].format(id="f1")):
                self.deleted.append("file f1")
                return reply({})
            raise AssertionError(f"unexpected request {method} {path}")

    def check(self, webui, settle_s=0.0, scrolls=None):
        qdrant = kit_module.Qdrant(16333, "admin-key")

        def count(method, path, *, payload, **_kw):
            tenant = payload["filter"]["must"][0]["match"]["value"]
            if path.endswith("/points/scroll"):
                if scrolls is not None:
                    scrolls.append((method, path, payload))
                if "offset" not in payload:
                    result = {"points": [{"id": "p0001"}, {"id": "p1000"}], "next_page_offset": "p1001"}
                else:
                    result = {"points": [{"id": "p1001", "payload": {"text": self.PAST_PAGE_CHUNK}}],
                              "next_page_offset": "p1002"}
                return sc.Response(200, "application/json", json.dumps({"result": result}).encode())
            trailing = webui.trailing.get(tenant)
            points = trailing.pop(0) if trailing else webui.tenants.get(tenant, 0)
            return sc.Response(200, "application/json", json.dumps({"result": {"count": points}}).encode())

        qdrant.endpoint = mock.Mock(request=mock.Mock(side_effect=count))
        timeouts = {**kit_module.PAGING_TIMEOUTS, "settle_s": settle_s}
        with mock.patch.object(kit_module, "PAGING_POLL_S", 0), \
                mock.patch.object(kit_module, "PAGING_TIMEOUTS", timeouts):
            return kit_module.paging_check(webui, qdrant, "t", "chat")

    def test_a_knowledge_base_past_one_scroll_page_passes_and_records_both_counts(self):
        webui = self.FakeOpenWebUI()
        outcome = self.check(webui)
        self.assertEqual(outcome.detail, "file tenant 1100 points; knowledge tenant 1100 points")
        self.assertEqual(outcome.values["points"], {"file": 1100, "knowledge": 1100})
        self.assertEqual(outcome.values["retrieved"], {"sources": 1, "chunks": 1, "planted": True})
        self.assertEqual([chat["files"] for chat in webui.chats], [[{"type": "collection", "id": "k1"}]])
        self.assertEqual(webui.deleted, ["knowledge k1", "file f1"])

    def test_bm25_alone_retrieves_the_first_knowledge_point_past_one_scroll_page(self):
        # A read that stops after one page drops that point from BM25's
        # corpus, and a BM25-only query has no dense branch to find it.
        webui, scrolls = self.FakeOpenWebUI(), []
        outcome = self.check(webui, scrolls=scrolls)
        tenant = {"must": [{"key": "tenant_id", "match": {"value": "k1"}}]}
        scroll = "/collections/open-webui-rag-v1_knowledge/points/scroll"
        self.assertEqual(scrolls, [
            ("POST", scroll, {"filter": tenant, "limit": 1000, "with_payload": False, "with_vector": False}),
            ("POST", scroll, {"filter": tenant, "offset": "p1001", "limit": 1, "with_payload": ["text"],
                              "with_vector": False}),
        ])
        self.assertEqual(webui.queries, [{"collection_names": ["k1"], "query": "0417", "k": 3, "k_reranker": 3,
                                          "hybrid": True, "hybrid_bm25_weight": 1.0}])
        self.assertEqual(outcome.values["bm25"], {"section": 417, "query": "0417", "documents": 1, "found": True})

    def test_counts_that_trail_the_upload_settle_only_at_the_corpus_size(self):
        # Two equal reads can still be partial while Qdrant applies points.
        webui = self.FakeOpenWebUI(trailing={"file-f1": [1001, 1001], "k1": [1000, 1000]})
        outcome = self.check(webui, settle_s=300.0)
        self.assertEqual(outcome.values["points"], {"file": 1100, "knowledge": 1100})

    def test_each_missed_paging_assertion_fails_and_still_cleans_up(self):
        unplanted = [{**self.PLANTED_SOURCES[0], "document": ["## Ledger page 0007\nLedger page 0007 row 1"]}]
        cases = {
            # A one-page scroll copies exactly one page into the knowledge base.
            "one scroll page copied": {"knowledge_points": 1000},
            "no tenant past the cap": {"file_points": 1000, "knowledge_points": 1000},
            # The corpus contract is one chunk per section.
            "a section split in two": {"file_points": 1101, "knowledge_points": 1101},
            "empty sources": {"sources": []},
            "planted sentence not retrieved": {"sources": unplanted},
            # Dense retrieval may still return the planted sentence.
            "BM25 misses the point past one page": {"bm25_documents": [self.PLANTED_CHUNK]},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                webui = self.FakeOpenWebUI(**overrides)
                with self.assertRaises(sc.ScenarioFailure):
                    self.check(webui)
                self.assertEqual(webui.deleted, ["knowledge k1", "file f1"])

    def test_a_paging_file_that_fails_or_times_out_in_processing_is_deleted(self):
        # The upload returns an id, but processing never completes, so the
        # check never reaches its own cleanup.
        no_wait = {**kit_module.PAGING_TIMEOUTS, "index_s": 0.0}
        for status, message in (("failed", "paging corpus processing failed: embedding failed"),
                                ("pending", "timed out waiting for paging corpus processing")):
            with self.subTest(status):
                webui = self.FakeOpenWebUI(file_status=status)
                with mock.patch.object(kit_module, "PAGING_TIMEOUTS", no_wait), \
                        mock.patch.object(kit_module.time, "sleep"), \
                        self.assertRaises(sc.ScenarioFailure) as raised:
                    self.check(webui)
                self.assertEqual(str(raised.exception), f"{message}; cleanup: file f1 DELETE returned 200")
                self.assertEqual(webui.deleted, ["file f1"])

    def test_hybrid_search_off_fails_before_anything_is_uploaded(self):
        webui = self.FakeOpenWebUI(hybrid=False)
        with self.assertRaises(sc.ScenarioFailure):
            self.check(webui)
        self.assertEqual(webui.tenants, {})

    def test_a_failed_cleanup_delete_fails_the_check(self):
        with self.assertRaises(sc.ScenarioFailure) as raised:
            self.check(self.FakeOpenWebUI(delete_status=500))
        self.assertIn("knowledge", str(raised.exception))


class HybridErrorTests(unittest.TestCase):
    """open-webui.acceptance.failclosed.hybrid-error against fake Open WebUI and Qdrant."""

    HANDBOOK_CHUNK = "## 3. Seed cabinet\nThe brass key opens the seed cabinet."

    class Fakes:
        """Open WebUI 0.11.4 and Qdrant sharing one knowledge tenant.

        ``fault`` is how a chat answers while the null-metadata point is
        planted: "refuse" (0005's 503), "fallback" (upstream's unreranked
        200), "latch" (503 and the gate stays closed), "wrong-detail", or
        "sentinel" (a 503 whose body quotes the planted text).  ``recovery``
        is how it answers once the point is gone: "answer", "empty",
        "no-fact", "nan", or "refuse".
        """

        json = sc.Endpoint.json

        def __init__(self, *, fault="refuse", recovery="answer", hybrid=True, health=200, file_points=4,
                     knowledge_points=None, delete_status=200, remaining=0, marker=True, plant_status=200,
                     recount_status=200, landed=True, stored=None, lingering=False):
            self.fault, self.recovery, self.hybrid = fault, recovery, hybrid
            self.health, self.file_points = health, file_points
            self.copied = file_points if knowledge_points is None else knowledge_points
            self.delete_status, self.remaining, self.marker = delete_status, remaining, marker
            self.plant_status, self.recount_status = plant_status, recount_status
            # ``landed`` False: Qdrant accepts the plant but the knowledge
            # tenant never holds it.  ``stored`` replaces the payload Qdrant
            # reads back; ``lingering`` keeps the point in the tenant's count
            # after its delete.
            self.landed, self.stored, self.lingering = landed, stored, lingering
            self.knowledge_points = 0
            self.planted = None
            self.in_tenant = False
            self.latched = False
            self.chats, self.qdrant_calls, self.deleted = [], [], []

        # Open WebUI ---------------------------------------------------------
        def request(self, method, path, *, payload: Any = None, body=None, content_type=None, token=None):
            def reply(value, status=200, kind="application/json"):
                return sc.Response(status, kind, value if isinstance(value, bytes) else json.dumps(value).encode())

            detail = kit_module._rag_unavailable_detail()
            if (method, path) == ("GET", sc.API["rag_config"]):
                return reply({"ENABLE_RAG_HYBRID_SEARCH": self.hybrid})
            if (method, path) == ("GET", sc.API["rag_health"]):
                status = 503 if self.latched else self.health
                return reply({"status": "qualified"} if status == 200 else {"detail": detail}, status)
            if (method, path) == ("POST", sc.API["knowledge_create"]):
                return reply({"id": "k1"})
            if (method, path) == ("POST", sc.API["knowledge_file_add"].format(id="k1")):
                self.knowledge_points = self.copied
                return reply({"id": "k1"})
            if (method, path) == ("POST", sc.API["chat"]):
                self.chats.append(payload)
                return self.chat(reply, detail)
            if (method, path) == ("DELETE", sc.API["knowledge_delete"].format(id="k1")):
                self.deleted.append("knowledge k1")
                if self.delete_status == 200:
                    self.knowledge_points = self.remaining
                return reply(self.delete_status == 200, self.delete_status)
            raise AssertionError(f"unexpected request {method} {path}")

        def chat(self, reply, detail):
            if self.planted is not None:
                kind = self.fault
                if kind == "latch":
                    self.latched = True
                if kind in {"refuse", "latch"}:
                    return reply({"detail": detail}, 503)
                if kind == "wrong-detail":
                    return reply({"detail": "Hybrid search failed."}, 503)
                if kind == "sentinel":
                    return reply({"detail": detail, "text": kit_module.HYBRID_FAULT_SENTINEL}, 503)
                documents, scores = [kit_module.HYBRID_FAULT_SENTINEL, HybridErrorTests.HANDBOOK_CHUNK], [0.4, 0.3]
            elif self.latched or self.recovery == "refuse":
                return reply({"detail": detail}, 503)
            else:
                documents, scores = {
                    "answer": ([HybridErrorTests.HANDBOOK_CHUNK], [0.93]),
                    "empty": ([], []),
                    "no-fact": (["## 1. Beds\nThe beds rest in winter."], [0.2]),
                    "nan": ([HybridErrorTests.HANDBOOK_CHUNK], [float("nan")]),
                }[self.recovery]
            sources = [{"source": {"type": "collection", "id": "k1", "name": sc.HANDBOOK_NAME},
                        "document": documents, "distances": scores}] if documents else []
            events = [{"sources": sources}, {"choices": [{"delta": {"content": sc.CANONICAL_FACT}}]}]
            stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
            return reply(stream.encode(), kind="text/event-stream")

        # Qdrant -----------------------------------------------------------------
        def qdrant(self):
            qdrant = kit_module.Qdrant(16333, "admin-key")

            def request(method, path, *, payload: Any = None, token=None, **_kw):
                self.qdrant_calls.append((method, path, payload, token))
                if path.endswith("/points/count"):
                    tenant = payload["filter"]["must"][0]["match"]["value"]
                    if tenant == "k1" and self.deleted and self.recount_status != 200:
                        return sc.Response(self.recount_status, "application/json", b"{}")
                    count = self.file_points if tenant == "file-f1" else self.knowledge_points
                    count += 1 if tenant == "k1" and self.in_tenant else 0
                    return sc.Response(200, "application/json", json.dumps({"result": {"count": count}}).encode())
                if method == "PUT" and path.endswith("/points?wait=true"):
                    if self.plant_status == 200:
                        self.planted = payload["points"][0]
                        self.in_tenant = self.landed
                    return sc.Response(self.plant_status, "application/json", b'{"result": {}}')
                if method == "GET" and path == f"/collections/{kit_module.COLLECTIONS[1]}/points/{kit_module.HYBRID_FAULT_POINT}":
                    if not self.in_tenant:
                        return sc.Response(404, "application/json", b'{"status": {"error": "Not found"}}')
                    stored = self.stored if self.stored is not None else (self.planted or {}).get("payload")
                    point = {"id": kit_module.HYBRID_FAULT_POINT, "payload": stored}
                    return sc.Response(200, "application/json", json.dumps({"result": point}).encode())
                if path.endswith("/points/delete?wait=true"):
                    self.planted = None
                    self.in_tenant = self.in_tenant and self.lingering
                    return sc.Response(200, "application/json", b'{"result": {}}')
                raise AssertionError(f"unexpected Qdrant request {method} {path}")

            qdrant.endpoint = mock.Mock(request=mock.Mock(side_effect=request))
            return qdrant

    def check(self, fakes):
        journal = mock.Mock(return_value=(
            "Hybrid search failed; refusing the unreranked vector-search fallback: 'NoneType' object is not a mapping"
            if fakes.marker else ""))
        with mock.patch.object(kit_module, "PAGING_POLL_S", 0), mock.patch.object(kit_module, "HYBRID_SETTLE_S", 0.0):
            values = kit_module.hybrid_error_check(fakes, fakes.qdrant(), "t", "chat", "f1", journal)
        return values, journal

    def test_a_hybrid_error_fails_closed_without_latching_and_recovers(self):
        fakes = self.Fakes()
        values, journal = self.check(fakes)
        refusal = {"status": 503, "fixed_detail": True, "sources": 0, "handbook_text": False, "sentinel": False}
        self.assertEqual(values["fault"], refusal)
        self.assertEqual((values["health_before"], values["health_after_fault"], values["health_after_recovery"]),
                         (200, 200, 200))
        self.assertEqual(values["recovery"], {"status": 200, "sources": 1, "fact_in_sources": True,
                                              "finite_scores": True})
        self.assertEqual(values["points"], {"file": 4, "knowledge": 4})
        # The legacy hybrid path reads the whole knowledge tenant, so the
        # read-back proves the fault point was among the points it merged.
        self.assertEqual(values["fault_point"], {"id": kit_module.HYBRID_FAULT_POINT, "in_knowledge_tenant": True,
                                                 "metadata_null": True, "tenant_points_with_fault": 5})
        self.assertEqual(values["tenant_points_after_fault_delete"], 4)
        self.assertTrue(values["fallback_refusal_logged"])
        self.assertEqual(values["cleanup"], {"knowledge_delete": 200, "knowledge_points_after_delete": 0})
        self.assertEqual(set(values["timings"]), {"knowledge_add_s", "fault_chat_s", "recovery_chat_s"})
        # Both chats are the same knowledge-scoped chat; nothing restarts or re-saves in between.
        self.assertEqual([chat["files"] for chat in fakes.chats], [[{"type": "collection", "id": "k1"}]] * 2)
        journal.assert_called_once()
        self.assertEqual(fakes.deleted, ["knowledge k1"])
        self.assertIsNone(fakes.planted)

    def test_the_planted_point_carries_a_null_metadata_payload_in_the_knowledge_tenant(self):
        fakes = self.Fakes()
        self.check(fakes)
        plants = [(method, path, payload, token) for method, path, payload, token in fakes.qdrant_calls
                  if method == "PUT"]
        self.assertEqual(plants, [(
            "PUT", "/collections/open-webui-rag-v1_knowledge/points?wait=true",
            {"points": [{"id": "00000000-0000-4000-8000-00000000fa17",
                         "vector": [1.0] + [0.0] * (kit_module.QDRANT_DIMENSIONS - 1),
                         "payload": {"tenant_id": "k1", "text": kit_module.HYBRID_FAULT_SENTINEL,
                                     "metadata": None}}]},
            "admin-key",
        )])
        deletes = [payload for method, path, payload, _ in fakes.qdrant_calls if path.endswith("/points/delete?wait=true")]
        self.assertEqual(deletes, [{"points": ["00000000-0000-4000-8000-00000000fa17"]}])
        self.assertNotIn("brass", kit_module.HYBRID_FAULT_SENTINEL.casefold())

    def test_the_fallback_refusal_log_line_is_recorded_not_gated(self):
        values, _ = self.check(self.Fakes(marker=False))
        self.assertFalse(values["fallback_refusal_logged"])

    def test_each_missed_hybrid_error_assertion_fails_and_still_cleans_up(self):
        cases = {
            # A 0005 without the hybrid-error fix takes upstream's unreranked fallback.
            "fallback answered": {"fault": "fallback"},
            # A hybrid-search error that latches the gate.
            "the gate latched": {"fault": "latch"},
            "another detail": {"fault": "wrong-detail"},
            "the planted text in the refusal": {"fault": "sentinel"},
            "no recovery sources": {"recovery": "empty"},
            "the fact not recovered": {"recovery": "no-fact"},
            "a non-finite recovery score": {"recovery": "nan"},
            "still refusing after the point is gone": {"recovery": "refuse"},
            "a partial knowledge copy": {"knowledge_points": 3},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                fakes = self.Fakes(**overrides)
                with self.assertRaises(sc.ScenarioFailure):
                    self.check(fakes)
                self.assertEqual(fakes.deleted, ["knowledge k1"])
                self.assertIsNone(fakes.planted)

    def test_a_fault_that_was_never_injected_shows_in_the_record(self):
        # A 200 at the fault chat with no refusal log line means the point
        # never broke hybrid search; the failure carries both facts.
        with self.assertRaises(sc.ScenarioFailure) as raised:
            self.check(self.Fakes(fault="fallback", marker=False))
        recorded = json.loads(str(raised.exception))
        self.assertEqual((recorded["fault"]["status"], recorded["fallback_refusal_logged"]), (200, False))

    def test_a_fault_point_outside_the_tenant_read_fails_before_the_fault_chat(self):
        # A 503 proves nothing unless hybrid search read the planted point:
        # a plant the tenant does not hold, or one Qdrant stored without its
        # null metadata, stops the check before any chat.
        payload = {"tenant_id": "k1", "text": kit_module.HYBRID_FAULT_SENTINEL}
        cases = {
            "not in the tenant": ({"landed": False}, {"in_knowledge_tenant": False, "metadata_null": False,
                                                      "tenant_points_with_fault": 4}),
            "another tenant": ({"stored": {**payload, "tenant_id": "k2", "metadata": None}},
                               {"in_knowledge_tenant": False, "metadata_null": True, "tenant_points_with_fault": 5}),
            "no metadata key": ({"stored": payload}, {"in_knowledge_tenant": True, "metadata_null": False,
                                                       "tenant_points_with_fault": 5}),
        }
        for name, (overrides, observed) in cases.items():
            with self.subTest(name):
                fakes = self.Fakes(**overrides)
                with self.assertRaises(sc.ScenarioFailure) as raised:
                    self.check(fakes)
                self.assertEqual(json.loads(str(raised.exception))["fault_point"],
                                 {"id": kit_module.HYBRID_FAULT_POINT, **observed})
                self.assertEqual(fakes.chats, [])
                self.assertEqual(fakes.deleted, ["knowledge k1"])
                self.assertIsNone(fakes.planted)

    def test_a_fault_point_left_in_the_tenant_fails_the_recovery(self):
        with self.assertRaises(sc.ScenarioFailure) as raised:
            self.check(self.Fakes(lingering=True))
        self.assertEqual(json.loads(str(raised.exception))["tenant_points_after_fault_delete"], 5)

    def test_hybrid_search_off_or_a_closed_gate_fails_before_anything_is_created(self):
        cases: tuple[dict[str, Any], ...] = ({"hybrid": False}, {"health": 503})
        for overrides in cases:
            with self.subTest(overrides):
                fakes = self.Fakes(**overrides)
                with self.assertRaises(sc.ScenarioFailure):
                    self.check(fakes)
                self.assertEqual((fakes.chats, fakes.deleted, fakes.qdrant_calls), ([], [], []))

    def test_a_failed_plant_still_deletes_the_knowledge_base(self):
        fakes = self.Fakes(plant_status=500)
        with self.assertRaises(sc.ScenarioFailure):
            self.check(fakes)
        self.assertEqual(fakes.chats, [])
        self.assertEqual(fakes.deleted, ["knowledge k1"])

    def test_a_failed_or_incomplete_knowledge_delete_fails_the_check(self):
        cases: tuple[tuple[dict[str, Any], str], ...] = (
            ({"delete_status": 500}, "delete returned 500"),
            ({"remaining": 2}, "still holds 2 points"),
            ({"recount_status": 500}, "count failed after its delete (ScenarioFailure)"),
        )
        for overrides, message in cases:
            with self.subTest(message):
                with self.assertRaises(sc.ScenarioFailure) as raised:
                    self.check(self.Fakes(**overrides))
                self.assertIn(message, str(raised.exception))


class FirstStartTests(unittest.TestCase):
    def test_the_alembic_tmp_table_warning_is_not_a_migration_error(self):
        warning = (
            "/usr/lib/python3.14/contextlib.py:148: SAWarning: Table '_alembic_tmp_tag' specifies columns 'id' as "
            "primary_key=True, not matching locally specified columns 'id', 'user_id'; setting the current primary "
            "key columns to 'id', 'user_id'. This warning may become an exception in a future release"
        )
        self.assertEqual(kit_module.migration_errors([warning, "INFO  [alembic.runtime.migration] Running upgrade"]), [])

    def test_the_0_11_4_upgrade_lines_are_not_migration_errors(self):
        # Open WebUI 0.11.1 added three revisions on top of 0.11.0's head.
        # None of them logs, so a fresh 0.11.4 start adds only Alembic's own
        # upgrade lines, with each revision's docstring title.
        upgrades = [
            "INFO  [alembic.runtime.migration] Running upgrade f0bd01a18a3d -> 1ce6ade7d93b, "
            "Add group_member user_id index",
            "INFO  [alembic.runtime.migration] Running upgrade 1ce6ade7d93b -> 6d09d1bf1f23, "
            "repair double encoded user oauth",
            "INFO  [alembic.runtime.migration] Running upgrade 6d09d1bf1f23 -> d4c1a8e37b62, "
            "add chat timer_at and chat list, unread and timer indexes",
        ]
        self.assertEqual(kit_module.migration_errors(upgrades), [])

    def test_the_trial_binds_the_0_11_4_head_and_qdrant_1_19_1(self):
        self.assertEqual(kit_module.ALEMBIC_HEAD, "d4c1a8e37b62")
        self.assertEqual(kit_module.QDRANT_VERSION, "1.19.1")
        # The v1 envelope contract keeps the 0.11.0 pair it measured.
        self.assertEqual(v1.CONTRACT["open_webui"]["alembic_head"], "f0bd01a18a3d")
        runbook = (REPO_ROOT / "docs" / "maintainers" / "open-webui-household-acceptance.md").read_text(encoding="utf-8")
        rows = {line.split("`")[1]: line for line in runbook.splitlines() if line.startswith("| `open-webui.")}
        self.assertIn(f"Alembic head `{kit_module.ALEMBIC_HEAD}`", rows["open-webui.acceptance.ready.first-start"])
        self.assertIn(f"Qdrant {kit_module.QDRANT_VERSION}", rows["open-webui.acceptance.qdrant.g4"])

    def test_the_first_start_requires_the_bound_head(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            kit.raw.mkdir(parents=True)
            (kit.raw / "first-start.json").write_text(
                json.dumps({"started_at": 1.0, "ready_s": 9.5, "qdrant_fresh": True}))
            data = Path(directory) / "data"
            data.mkdir()
            trial = kit_module.Trial(kit)
            for head, passes in ((kit_module.ALEMBIC_HEAD, True), ("f0bd01a18a3d", False)):
                with contextlib.closing(sqlite3.connect(data / "webui.db")) as connection, connection:
                    connection.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num TEXT)")
                    connection.execute("DELETE FROM alembic_version")
                    connection.execute("INSERT INTO alembic_version VALUES (?)", (head,))
                with self.subTest(head), mock.patch.object(kit_module, "data_dir", return_value=data), \
                        mock.patch.object(kit_module, "journal", return_value=""):
                    if passes:
                        self.assertEqual(trial.first_start()["alembic_head"], head)
                    else:
                        with self.assertRaises(sc.ScenarioFailure):
                            trial.first_start()

    def test_real_alembic_failures_are_migration_errors(self):
        failures = [
            "ERROR [alembic.util.messaging] Can't locate revision identified by 'f0bd01a18a3d'",
            "alembic.util.exc.CommandError: Can't locate revision identified by 'f0bd01a18a3d'",
            "  FAILED: Multiple head revisions are present (alembic)",
        ]
        self.assertEqual(kit_module.migration_errors(failures), failures)


class ResourceTests(unittest.TestCase):
    def test_only_oom_and_unplanned_restarts_gate(self):
        unit = "owui-acc-open-webui.service"
        calm = [
            {"units": {unit: {"oom_kill": 0, "NRestarts": 0, "memory_peak": 10, "CPUUsageNSec": 5}}},
            {"units": {unit: {"oom_kill": 0, "NRestarts": 0, "memory_peak": 900, "CPUUsageNSec": 50}}},
        ]
        gates = kit_module.resource_gates(calm)
        self.assertTrue(gates["passes"])
        self.assertEqual(gates["memory_peak_max_bytes"][unit], 900)
        oom = calm + [{"units": {unit: {"oom_kill": 1, "NRestarts": 0}}}]
        self.assertFalse(kit_module.resource_gates(oom)["passes"])
        crash = calm + [{"units": {unit: {"oom_kill": 0, "NRestarts": 1}}}]
        self.assertFalse(kit_module.resource_gates(crash)["passes"])
        # systemd resets NRestarts on every planned start, so an auto-restart
        # seen before a planned restart still fails the gate.
        first_start_crash = [
            {"units": {unit: {"oom_kill": 0, "NRestarts": 1}}},
            {"units": {unit: {"oom_kill": 0, "NRestarts": 0}}},
            {"units": {unit: {"oom_kill": 0, "NRestarts": 1}}},
        ]
        gates = kit_module.resource_gates(first_start_crash)
        self.assertFalse(gates["passes"])
        self.assertEqual(gates["unplanned_restarts"][unit], 1)

    def test_the_oom_gate_needs_an_observation_for_every_running_member(self):
        unit, relay, kit_slice = "owui-acc-open-webui.service", "owui-acc-relay.service", "builds-owui_acc.slice"

        def record(entry, relay_entry, slice_oom=0):
            return {"units": {unit: entry, relay: relay_entry},
                    "slice": {"unit": kit_slice, "state": "active", "oom_kill": slice_oom}}

        running = {"state": "active", "oom_kill": 0, "NRestarts": 0}
        # A stopped unit has no cgroup to read; the slice's hierarchical count covers it.
        stopped = {"state": "inactive", "NRestarts": 0}
        self.assertTrue(kit_module.resource_gates([record(running, stopped)])["passes"])
        unreadable = {"state": "active", "oom_kill": None, "NRestarts": 0}
        gates = kit_module.resource_gates([record(running, unreadable)])
        self.assertFalse(gates["passes"])
        self.assertEqual(gates["oom_unobserved"], [relay])
        gates = kit_module.resource_gates([record(running, stopped, slice_oom=1)])
        self.assertFalse(gates["passes"])
        self.assertEqual(gates["oom_kills"][kit_slice], 1)
        no_slice = [{"units": {unit: running}, "slice": {"unit": kit_slice, "state": "active", "oom_kill": None}}]
        self.assertEqual(kit_module.resource_gates(no_slice)["oom_unobserved"], [kit_slice])


class EvidenceTests(unittest.TestCase):
    def test_trial_map_is_one_pass_with_the_frozen_resmoke_ids_in_order(self):
        steps = kit_module.TRIAL_STEPS
        self.assertEqual(len(steps), 25)
        self.assertEqual(len(set(steps)), 25)
        # The persisted-profile check reads the first start's database before
        # commissioning's configure call rewrites the connection.
        self.assertEqual(steps[2:5], ("open-webui.acceptance.ready.first-start", "open-webui.acceptance.profile.persisted",
                                      "open-webui.acceptance.auth.one-admin"))
        # The paging corpus and the planted hybrid-search fault run after both
        # drills, so their anchor and timings never carry those points.
        rollback = steps.index("open-webui.acceptance.drill.rollback")
        self.assertEqual(steps[rollback + 1:rollback + 3],
                         ("open-webui.acceptance.qdrant.paging", "open-webui.acceptance.failclosed.hybrid-error"))
        # Both closed-gate checks run while reranker-down's latch holds, before
        # recovery requalifies the gate; the explicit reads follow it.
        self.assertEqual(
            steps[steps.index("open-webui.acceptance.failclosed.reranker-down"):
                  steps.index("open-webui.acceptance.gate.explicit-reads") + 1],
            ("open-webui.acceptance.failclosed.reranker-down", "open-webui.acceptance.failclosed.full-context",
             "open-webui.acceptance.failclosed.native-tools", "open-webui.acceptance.failclosed.recovery",
             "open-webui.acceptance.gate.explicit-reads"),
        )
        self.assertEqual(steps[-2:], ("open-webui.acceptance.resources", "open-webui.acceptance.evidence"))
        self.assertEqual(tuple(item for item in steps if item.startswith("open-webui.resmoke.")), sc.SCENARIO_IDS)
        self.assertEqual(sum(1 for item in steps if ".drill." in item), 2)
        self.assertEqual((kit_module.RESTORE_DRILL, kit_module.ROLLBACK_DRILL),
                         tuple(item for item in steps if ".drill." in item))
        # A changed step gets a new id and an evidence schema bump, never a
        # rewritten id; new steps bump the schema too.
        self.assertEqual(steps[7], "open-webui.acceptance.connections.no-stored-secret")
        self.assertEqual(kit_module.SCHEMA, "open-webui-household-acceptance/v4")

    def test_the_runbook_scenario_map_is_the_trial_map(self):
        runbook = (REPO_ROOT / "docs" / "maintainers" / "open-webui-household-acceptance.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| `(open-webui\.[^`]+)`", runbook, re.MULTILINE)
        self.assertEqual(tuple(rows), kit_module.TRIAL_STEPS)
        self.assertIn(f"`{kit_module.SCHEMA}`", runbook)

    def test_publicize_hides_private_paths_and_addresses(self):
        replacements = [("/srv/build/owui", "<root>"), ("/run/user/1000", "$XDG_RUNTIME_DIR")]
        value = {
            "a": "/srv/build/owui/state/x", "b": "http://127.0.0.1:13305/api/v1", "c": "[::1]:16379",
            "d": ["/run/user/1000/owui-acc/open-webui.sock", "https://localhost:18443"], "e": "::1", "f": 3,
        }
        public = kit_module.publicize(value, replacements)
        self.assertEqual(public["a"], "<root>/state/x")
        self.assertEqual(public["b"], "http://loopback:13305/api/v1")
        self.assertEqual(public["c"], "loopback:16379")
        self.assertEqual(public["d"], ["$XDG_RUNTIME_DIR/owui-acc/open-webui.sock", "https://loopback:18443"])
        self.assertEqual(public["e"], "loopback")
        self.assertEqual(public["f"], 3)
        v1.assert_public_safe(public)

    def test_the_effective_ip_policy_is_public_safe(self):
        shown = {"IPAddressAllow": "127.0.0.0/8 ::1/128", "IPAddressDeny": "0.0.0.0/0 ::/0"}
        public = kit_module.publicize(shown, [])
        v1.assert_public_safe(public)
        self.assertEqual(public["IPAddressAllow"], "loopback/8 loopback/128")
        self.assertEqual(kit_module.publicize("127.1.2.3:80 and 127.0.0.1", []), "loopback:80 and loopback")
        self.assertEqual(kit_module.publicize("10.127.0.0.1x", []), "10.127.0.0.1x")

    def test_a_non_default_lemonade_origin_never_reaches_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            kit.lemond_url = "http://lemond-host:13305"
            public = kit_module.publicize({"url": "http://lemond-host:13305/api/v1"}, kit.replacements())
            self.assertEqual(public, {"url": "<lemond>/api/v1"})
            kit.lemond_url = "http://127.0.0.1:23999"
            public = kit_module.publicize({"url": "http://127.0.0.1:23999/api/v1"}, kit.replacements())
            self.assertEqual(public, {"url": "<lemond>/api/v1"})
            self.assertEqual(make_kit(directory).replacements()[0][1], "<root>")

    def trial(self, directory, *, rehearsal):
        kit = make_kit(directory, rehearsal=rehearsal)
        kit.save_state(mode=kit.mode, credential_route="systemd-creds", lemonade_receipts=["ashp-m4-receipt-1"],
                       kit_commit="0" * 40)
        trial = kit_module.Trial(kit, {"version": "10.0.0", "start_time": "t0", "all_models_loaded": []})
        trial.lemond_post = {"version": "10.0.0", "start_time": "t0", "all_models_loaded": []}
        trial.steps = [
            kit_module.Step(step_id, sc.PASS, "ok", 1.0, {
                "path": f"{directory}/state/open-webui/data",
                "peer": "127.0.0.1:13305",
                "socket": f"{directory}/run/owui-acc/open-webui.sock",
            })
            for step_id in kit_module.TRIAL_STEPS[:-1]
        ]
        return kit, trial

    def test_evidence_is_public_safe_and_counts_one_trial_set(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            evidence = kit_module.build_evidence(kit, trial, 0, False)
            v1.assert_public_safe(evidence)
            self.assertEqual(evidence["schema"], "open-webui-household-acceptance/v4")
            self.assertEqual(
                (evidence["trial_set_count"], evidence["restore_drills"], evidence["rollback_drills"]), (1, 1, 1)
            )
            self.assertEqual(evidence["disposition"], "accepted")
            self.assertEqual(evidence["lemonade"]["receipt_ids"], ["ashp-m4-receipt-1"])
            self.assertNotIn(directory, json.dumps(evidence))
            self.assertNotIn("generation", json.dumps(evidence).lower())
            void = kit_module.build_evidence(kit, trial, 0, True)
            self.assertTrue(void["disposition"].startswith("void"))

    def test_the_0400_fallback_is_a_trial_condition_not_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            self.assertEqual(kit_module.build_evidence(kit, trial, 0, False)["conditions"], [])
            kit.save_state(credential_route="plaintext-0400")
            evidence = kit_module.build_evidence(kit, trial, 0, False)
            self.assertEqual(evidence["conditions"],
                             ["credentials: 0400-file fallback; systemd-creds --user unavailable"])
            self.assertEqual(evidence["disposition"], "accepted")
            v1.assert_public_safe(evidence)

    def test_evidence_counts_only_the_drills_that_ran(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            self.assertEqual(trial.drill_counts(), {"restore_drills": 1, "rollback_drills": 1})
            # A critical failure before the drills: neither drill step exists.
            trial.steps = [step for step in trial.steps
                           if step.id not in (kit_module.RESTORE_DRILL, kit_module.ROLLBACK_DRILL)]
            evidence = kit_module.build_evidence(kit, trial, 1, False)
            self.assertEqual((evidence["restore_drills"], evidence["rollback_drills"]), (0, 0))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = trial.finish()
            self.assertEqual(code, sc.EXIT_FAIL)
            recorded = trial.steps[-1]
            self.assertEqual((recorded.id, recorded.result), (kit_module.TRIAL_STEPS[-1], sc.FAIL))
            self.assertEqual(recorded.values["restore_drills"], 0)

    def test_an_undetectable_lemonade_restart_is_a_condition_not_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            evidence = kit_module.build_evidence(kit, trial, 0, None)
            self.assertIsNone(evidence["lemonade"]["restarted"])
            self.assertEqual(evidence["conditions"], [kit_module.LEMONADE_RESTART_CONDITION])
            self.assertEqual(evidence["disposition"], "accepted")
            v1.assert_public_safe(evidence)
            trial.lemond_pre = trial.lemond_post = {"status": "ok"}
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
                trial.finish()
            self.assertIn("not detectable from /api/v1/health", errors.getvalue())

    def test_the_trial_reads_the_journal_from_the_current_open_webui_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            kit.raw.mkdir(parents=True, exist_ok=True)
            (kit.raw / "first-start.json").write_text(json.dumps({"started_at": 100.0}))
            with mock.patch.object(kit_module, "unit_active_since", return_value=None):
                self.assertEqual(trial.open_webui_since(), 100.0)
            # The scenario context's journal is bound to that window.
            with mock.patch.object(kit_module, "unit_active_since", return_value=250.0), \
                    mock.patch.object(kit_module, "journal", return_value="") as read, \
                    mock.patch.object(kit_module, "upload_handbook", return_value="file-1"), \
                    mock.patch.object(kit_module.sc, "open_webui_pid", return_value=1), \
                    mock.patch.object(kit_module.sc, "read_process_environ", return_value=candidate_env()), \
                    mock.patch.object(kit_module, "effective_models",
                                      return_value=(candidate_env()["RAG_EMBEDDING_MODEL"],
                                                    candidate_env()["RAG_RERANKING_MODEL"])), \
                    mock.patch.object(kit_module.Kit, "caddy"), mock.patch.object(kit_module.Kit, "lemond"), \
                    mock.patch.object(kit_module.Kit, "qdrant"), \
                    mock.patch.object(kit_module, "a_id2_rows", return_value=[]), \
                    mock.patch.object(kit_module, "unit_show", return_value={}):
                trial.token = "token"
                trial.listed_chat_model = "resident-chat"
                ctx = trial.prepare_scenarios()
                self.assertIsNotNone(ctx.journal)
                assert ctx.journal is not None
                ctx.journal()
                # The recorded IP-policy warning comes from the same window.
                trial.unit_properties()
            warning = "owui-acc-open-webui.service: unit configures an IP firewall, but not running as root."
            with mock.patch.object(kit_module, "unit_active_since", return_value=250.0), \
                    mock.patch.object(kit_module, "journal", return_value=f"starting\n{warning}\n"), \
                    mock.patch.object(kit_module, "a_id2_rows", return_value=[]), \
                    mock.patch.object(kit_module, "unit_show", return_value={}):
                self.assertEqual(trial.unit_properties()["journal_warning"], warning)
            self.assertEqual(read.call_count, 2)
            for call in read.call_args_list:
                self.assertEqual(call, mock.call(kit_module.UNITS["open-webui"], since=250.0))

    def test_record_mode_writes_evidence_and_rehearsal_writes_none(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            with contextlib.redirect_stdout(io.StringIO()):
                code = trial.finish()
            self.assertEqual(code, sc.EXIT_PASS)
            written = list((kit.root / "evidence" / "public").glob("*.json"))
            self.assertEqual(len(written), 1)
            v1.assert_public_safe(json.loads(written[0].read_text()))
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=True)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = trial.finish()
            self.assertEqual(code, sc.EXIT_PASS)
            self.assertFalse((kit.root / "evidence").exists())
            self.assertIn("no evidence written", output.getvalue())
            self.assertNotIn("1.0", output.getvalue())

    def test_a_rehearsal_prints_the_detail_of_a_step_that_does_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            _kit, trial = self.trial(directory, rehearsal=True)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                trial.record(kit_module.Step("a", sc.PASS, "ok", 2.5, {"ready_s": 2.5}))
                trial.record(kit_module.Step("b", sc.FAIL, "ScenarioFailure: head mismatch", 2.5))
                trial.record(kit_module.Step("c", sc.BLOCKED, "stub unreachable", 2.5))
            self.assertEqual(
                output.getvalue().splitlines(),
                ["a PASS", "b FAIL ScenarioFailure: head mismatch", "c BLOCKED stub unreachable"],
            )

    def test_an_unsafe_record_keeps_the_values_privately(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            trial.steps[0].detail = "OSError: [Errno 2] No such file or directory: '/home/someone/x'"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
                code = trial.finish()
            self.assertEqual(code, sc.EXIT_FAIL)
            self.assertFalse(list((kit.root / "evidence" / "public").glob("*.json")) if (kit.root / "evidence" / "public").exists() else [])
            private = kit.root / "evidence" / "raw" / "trial-evidence.json"
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(json.loads(private.read_text())["steps"]), len(kit_module.TRIAL_STEPS))
            self.assertIn(str(private), errors.getvalue())
            # Teardown never deletes the only copy of the one trial's values.
            (kit.root / kit_module.MARKER).write_text("marker\n")
            (kit.root / "backups" / "anchor").mkdir(parents=True)
            for flags in ([], ["--keep-anchor"]):
                args = kit_module.parser().parse_args(["teardown", *flags, "--evidence-out", f"{directory}/out"])
                with mock.patch.object(kit_module, "systemctl") as systemctl, \
                        self.assertRaisesRegex(sc.Blocked, "only copy"):
                    kit_module.cmd_teardown(kit, args)
                systemctl.assert_not_called()
                self.assertTrue(private.is_file())

    def test_a_restore_that_misses_its_ceiling_still_runs_the_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            trial.steps = []
            ran = []

            def ok(name):
                def action(*_args, **_kwargs):
                    ran.append(name)
                    return {}
                return action

            def over_ceiling():
                ran.append("restore")
                raise sc.ScenarioFailure('{"restore_s": 41.0}')

            for name in ("identity", "unit_properties", "first_start", "profile_persisted", "commission", "restart", "g4",
                         "no_stored_secret",
                         "reranker_down", "full_context", "native_tools", "recovery", "explicit_reads", "privacy",
                         "rollback_drill", "qdrant_paging", "hybrid_error", "resources"):
                setattr(trial, name, ok(name))
            trial.restore_drill = over_ceiling
            trial.prepare_scenarios = lambda: None

            def scenario(scenario_id, _ctx):
                trial.record(kit_module.Step(scenario_id, sc.PASS, "ok", 0.0))

            trial.scenario = scenario
            trial.finish = lambda: 0
            with mock.patch.object(kit_module, "route_checks", return_value={}), \
                    mock.patch.object(sc, "lemond_snapshot", return_value=({}, {})), \
                    contextlib.redirect_stdout(io.StringIO()):
                trial.run()
            self.assertEqual(ran[-4:], ["rollback_drill", "qdrant_paging", "hybrid_error", "resources"])
            # The run records exactly the scenario map, in order, plus the
            # setup step; finish records the evidence step.
            expected = list(kit_module.TRIAL_STEPS[:-1])
            expected.insert(expected.index("open-webui.acceptance.connections.no-stored-secret") + 1,
                            "open-webui.acceptance.handbook-indexed")
            self.assertEqual([step.id for step in trial.steps], expected)
            results = {step.id: step.result for step in trial.steps}
            self.assertEqual(results["open-webui.acceptance.drill.restore"], sc.FAIL)
            self.assertEqual(results["open-webui.acceptance.drill.rollback"], sc.PASS)
            self.assertEqual(results["open-webui.acceptance.qdrant.paging"], sc.PASS)

    def test_a_step_can_record_its_measured_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            trial.steps = []
            measured = kit_module.Passed("file tenant 1100 points; knowledge tenant 1100 points",
                                         {"points": {"file": 1100, "knowledge": 1100}})
            with contextlib.redirect_stdout(io.StringIO()) as output:
                trial.step("open-webui.acceptance.qdrant.paging", lambda: measured)
            recorded = trial.steps[-1]
            self.assertEqual((recorded.result, recorded.detail, recorded.values),
                             (sc.PASS, measured.detail, measured.values))
            self.assertIn("knowledge tenant 1100 points", output.getvalue())

    def test_the_rollback_refuses_without_an_anchor_before_touching_state(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=False)
            (kit.root / "tree").mkdir()
            with mock.patch.object(kit_module, "systemctl") as systemctl:
                with self.assertRaises(sc.ScenarioFailure):
                    trial.rollback_drill()
            systemctl.assert_not_called()
            self.assertTrue((kit.root / "tree").is_dir())

    def test_escalation_and_critical_failures_stop_the_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            kit, trial = self.trial(directory, rehearsal=True)
            trial.steps = []

            def escalate():
                raise sc.Escalation("ESCALATE: zembed canary")

            def fail():
                raise sc.ScenarioFailure("no")

            with contextlib.redirect_stdout(io.StringIO()):
                trial.step("a", fail)
                with self.assertRaises(kit_module.Stop):
                    trial.step("b", fail, critical=True)
                with self.assertRaises(kit_module.Stop):
                    trial.step("c", escalate)
            self.assertEqual([step.result for step in trial.steps], [sc.FAIL, sc.FAIL, sc.ESCALATE])
            self.assertEqual(sc.aggregate_exit_code([step.result for step in trial.steps]), sc.EXIT_ESCALATE)


if __name__ == "__main__":
    unittest.main()
