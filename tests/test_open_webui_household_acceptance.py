import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
KIT = REPO_ROOT / "tools" / "accept_open_webui_household.py"
PACKAGED_ENV = REPO_ROOT / "packages" / "open-webui" / "open-webui.env"
OPEN_WEBUI_UNIT = REPO_ROOT / "packages" / "open-webui" / "open-webui.service"
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
    return sc.parse_env_file(PACKAGED_ENV.read_text(encoding="utf-8"))


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


def six_archives(directory):
    names = (
        "open-webui-0.11.0-5-x86_64.pkg.tar.zst",
        "python-rapidocr-3.9.2-1-any.pkg.tar.zst",
        "qdrant-1.19.0-1-x86_64.pkg.tar.zst",
        "qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst",
        "qdrant-web-ui-0.2.16-1-any.pkg.tar.zst",
        "python-faster-whisper-1.2.1-1-any.pkg.tar.zst",
    )
    return [write_archive(directory, name, name.encode()) for name in names]


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

    def test_defaults_come_from_the_packaged_env_and_the_contract(self):
        kit = self.kit("down")
        self.assertEqual(kit.root, kit_module.DEFAULT_ROOT)
        self.assertEqual(kit.lemond_url, sc.DEFAULT_LEMOND_URL)
        self.assertEqual(
            packaged_env()["RAG_OPENAI_API_BASE_URL"], sc.DEFAULT_LEMOND_URL + "/api/v1"
        )
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
        env = packaged_env()
        with tempfile.TemporaryDirectory() as directory:
            for rehearsal in (False, True):
                kit = make_kit(directory, rehearsal=rehearsal)
                overlay = kit.overlay(env)
                self.assertLessEqual(set(overlay), sc.overlay_allowlist(env, rehearsal=rehearsal))
                self.assertEqual(overlay["QDRANT_URI"], "http://127.0.0.1:16333")
                self.assertEqual(overlay["RAG_EXTERNAL_RERANKER_URL"], "http://127.0.0.1:13306/api/v1/rerank")
                self.assertEqual({**env, **overlay}["OPENAI_API_KEYS"], "")
                self.assertNotIn("HF_HUB_OFFLINE", overlay)
                self.assertNotIn("WHISPER_MODEL", overlay)
                state = str(Path(directory) / "state" / "open-webui")
                for key, value in overlay.items():
                    if "/" in value and not value.startswith("http"):
                        self.assertIn(state, value, key)
                        self.assertNotIn("/var/lib/open-webui", value, key)

    def test_rehearsal_points_the_provider_and_the_relay_at_the_stub(self):
        env = packaged_env()
        with tempfile.TemporaryDirectory() as directory:
            record = make_kit(directory)
            rehearsal = make_kit(directory, rehearsal=True)
            self.assertNotIn("OPENAI_API_BASE_URLS", record.overlay(env))
            self.assertEqual(env["OPENAI_API_BASE_URLS"], "http://127.0.0.1:13305/api/v1")
            self.assertEqual(rehearsal.overlay(env)["OPENAI_API_BASE_URLS"], "http://127.0.0.1:23305/api/v1")
            self.assertNotIn("RAG_OPENAI_API_BASE_URL", record.overlay(env))
            self.assertEqual(rehearsal.overlay(env)["RAG_OPENAI_API_BASE_URL"], "http://127.0.0.1:23305/api/v1")
            self.assertEqual((rehearsal.lemond_host, rehearsal.lemond_port), ("127.0.0.1", 23305))
            self.assertEqual((record.lemond_host, record.lemond_port), ("127.0.0.1", 13305))


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
            files = [value for _, key, value in lines if key == "EnvironmentFile"]
            self.assertEqual(
                files,
                [str(kit.root / "tree/open-webui/etc/open-webui/open-webui.env"), str(kit.root / "etc/acceptance.env")],
            )
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
        name = "open-webui-0.11.0-5-x86_64.pkg.tar.zst"
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
            record = write_archive(directory, "qdrant-1.19.0-1-x86_64.pkg.tar.zst", b"exact")
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
            {"name": name, "size": 1, "sha256": "0" * 64}
            for name in (
                "open-webui-0.11.0-5-x86_64.pkg.tar.zst", "python-rapidocr-3.9.2-1-any.pkg.tar.zst",
                "qdrant-1.19.0-1-x86_64.pkg.tar.zst", "qdrant-migration-1.18.3-1-x86_64.pkg.tar.zst",
                "qdrant-web-ui-0.2.16-1-any.pkg.tar.zst", "python-faster-whisper-1.2.1-1-any.pkg.tar.zst",
            )
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
            stack.enter_context(mock.patch.object(kit_module, "packaged_env_from_archive", return_value=packaged_env()))
            snapshot = stack.enter_context(mock.patch.object(sc, "lemond_snapshot", return_value=(health, models)))
            report, refusals = kit_module.preflight_facts(kit, probe_only=True)
        snapshot.assert_called_once()
        return report, refusals

    def served(self, *extra):
        env = packaged_env()
        ids = [env["RAG_EMBEDDING_MODEL"], env["RAG_RERANKING_MODEL"], "resident-chat", *extra]
        return {"data": [{"id": item} for item in ids]}, {"all_models_loaded": [{"model_name": item} for item in ids]}

    def test_preflight_passes_when_every_model_is_resident(self):
        models, health = self.served()
        with tempfile.TemporaryDirectory() as directory:
            report, refusals = self.run_preflight(directory, health=health, models=models)
        self.assertEqual(refusals, [])
        self.assertEqual(sorted(report["archives"].values()), ["ok"] * 6)

    def test_readiness_accepts_the_bare_listing_of_a_user_prefixed_chat_model(self):
        env = packaged_env()
        ids = [env["RAG_EMBEDDING_MODEL"], env["RAG_RERANKING_MODEL"], "Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL"]
        models = {"data": [{"id": item} for item in ids]}
        health = {"all_models_loaded": [{"model_name": item} for item in ids]}
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            kit.chat_model = sc.DEFAULT_CHAT_MODEL
            with mock.patch.object(kit_module.Kit, "packaged_env", return_value=env), \
                    mock.patch.object(sc, "lemond_snapshot", return_value=(health, models)):
                kit_module.require_lemond_ready(kit)

    def test_preflight_refuses_instead_of_loading_a_model(self):
        models, _ = self.served()
        env = packaged_env()
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

    def test_a_lemonade_other_than_the_packaged_provider_is_refused(self):
        models, health = self.served()
        with tempfile.TemporaryDirectory() as directory:
            _, refusals = self.run_preflight(directory, health=health, models=models,
                                             lemond_url="http://127.0.0.1:13400")
        self.assertTrue(any("differs from the packaged provider" in item for item in refusals), refusals)
        with tempfile.TemporaryDirectory() as directory:
            kit = make_kit(directory)
            kit.lemond_url = "http://127.0.0.1:13400"
            with mock.patch.object(kit_module.Kit, "packaged_env", return_value=packaged_env()), \
                    mock.patch.object(sc, "lemond_snapshot") as snapshot:
                with self.assertRaises(sc.Blocked):
                    kit_module.require_lemond_ready(kit)
            snapshot.assert_not_called()
            (kit.root / kit_module.MARKER).write_text("marker\n")
            (kit.root / "kit.json").write_text(json.dumps({"mode": "record", "credential_route": "systemd-creds",
                                                           "commissioned": False}))
            args = kit_module.parser().parse_args(["trial", "--root", directory, "--chat-model", "resident-chat",
                                                   "--lemond-url", "http://127.0.0.1:13400"])
            with mock.patch.object(kit_module, "kit_from_args", return_value=kit), \
                    mock.patch.object(kit_module.Kit, "packaged_env", return_value=packaged_env()), \
                    mock.patch.object(kit_module, "unit_active", return_value=True), \
                    contextlib.redirect_stderr(io.StringIO()):
                (kit.root / "evidence" / "raw").mkdir(parents=True)
                (kit.root / "evidence" / "raw" / "first-start.json").write_text("{}")
                code = kit_module.main(["trial", "--root", directory, "--chat-model", "resident-chat",
                                        "--lemonade-receipt", "r", "--lemond-url", "http://127.0.0.1:13400"])
            self.assertEqual(code, sc.EXIT_PRECONDITION)
        self.assertEqual(args.lemond_url, "http://127.0.0.1:13400")

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
                    mock.patch.object(kit_module.Kit, "packaged_env", return_value=packaged_env()), \
                    mock.patch.object(kit_module, "effective_models",
                                      return_value=(packaged_env()["RAG_EMBEDDING_MODEL"], packaged_env()["RAG_RERANKING_MODEL"])):
                with self.assertRaises(sc.Blocked):
                    kit_module.require_lemond_ready(kit)

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
                for package, packaged in (("open-webui", OPEN_WEBUI_UNIT), ("qdrant", QDRANT_UNIT)):
                    unit = root / "tree" / package / "usr" / "lib" / "systemd" / "system" / packaged.name
                    unit.parent.mkdir(parents=True)
                    unit.write_text(packaged.read_text())
                env = root / "tree" / "open-webui" / "etc" / "open-webui" / "open-webui.env"
                env.parent.mkdir(parents=True)
                env.write_text(PACKAGED_ENV.read_text())

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
                {"acceptance.env", "Caddyfile", "valkey-open-webui.conf", "qdrant-credential-shim"},
            )
            for item in referenced:
                self.assertTrue(Path(item).is_file(), item)
            acl = (root / "etc" / "valkey-open-webui.acl").read_text()
            self.assertIn(sc.valkey_password_hash("valkey-password"), acl)
            self.assertNotIn("valkey-password", acl)
            self.assertEqual((root / "etc" / "valkey-open-webui.acl").stat().st_mode & 0o777, 0o600)

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

    def test_the_production_whisper_placement_uses_the_base_pin(self):
        pin = sc.whisper_pin_record(sc.DEFAULT_WHISPER_MODEL)
        self.assertIn(f"rev={pin['revision']}", self.doc)
        for name, digest in pin["files"].items():
            self.assertIn(f"| `{name}` | `{digest}` |", self.doc)
            self.assertIn(f'"$src/{name}"', self.doc)


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
        self.assertFalse(restarted(None, {"uptime": 1}))


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

    def test_no_credential_check_ignores_toggles_and_flags_key_material(self):
        env = packaged_env()
        self.assertEqual(kit_module.nonempty_key_paths(env, {"OPENAI_API_KEYS": ""}), [])
        config = {
            "openai": {"api_keys": [""], "enable": True},
            "rag": {"openai": {"api_key": ""}, "external_reranker_api_key": ""},
            "auth": {"api_key": {"enable": False}},
        }
        self.assertEqual(kit_module.nonempty_key_paths(config), [])
        self.assertEqual(
            kit_module.nonempty_key_paths({"rag": {"openai": {"api_key": "sk-x"}}, "openai": {"api_keys": ["", "k"]}}),
            ["openai.api_keys", "rag.openai.api_key"],
        )

    def test_user_credentials_need_the_units_to_load_them_too(self):
        def fake_run(command, **_kwargs):
            if command[0] == "systemd-run":
                raise kit_module.KitError("systemd-run exited 243: Failed to set up credentials")
            return subprocess.CompletedProcess(command, 0, stdout=b"probe" if "decrypt" in command else b"")

        with mock.patch.object(kit_module, "run", side_effect=fake_run):
            self.assertFalse(kit_module.probe_systemd_creds())
        with mock.patch.object(kit_module, "run",
                               side_effect=lambda command, **_: subprocess.CompletedProcess(command, 0, stdout=b"probe")):
            self.assertTrue(kit_module.probe_systemd_creds())


class FirstStartTests(unittest.TestCase):
    def test_the_alembic_tmp_table_warning_is_not_a_migration_error(self):
        warning = (
            "/usr/lib/python3.14/contextlib.py:148: SAWarning: Table '_alembic_tmp_tag' specifies columns 'id' as "
            "primary_key=True, not matching locally specified columns 'id', 'user_id'; setting the current primary "
            "key columns to 'id', 'user_id'. This warning may become an exception in a future release"
        )
        self.assertEqual(kit_module.migration_errors([warning, "INFO  [alembic.runtime.migration] Running upgrade"]), [])

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


class EvidenceTests(unittest.TestCase):
    def test_trial_map_is_one_pass_with_the_frozen_resmoke_ids_in_order(self):
        steps = kit_module.TRIAL_STEPS
        self.assertEqual(len(steps), 19)
        self.assertEqual(len(set(steps)), 19)
        self.assertEqual(tuple(item for item in steps if item.startswith("open-webui.resmoke.")), sc.SCENARIO_IDS)
        self.assertEqual(sum(1 for item in steps if ".drill." in item), 2)

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
            self.assertEqual(evidence["schema"], "open-webui-household-acceptance/v1")
            self.assertEqual(
                (evidence["trial_set_count"], evidence["restore_drills"], evidence["rollback_drills"]), (1, 1, 1)
            )
            self.assertEqual(evidence["disposition"], "accepted")
            self.assertEqual(evidence["lemonade"]["receipt_ids"], ["ashp-m4-receipt-1"])
            self.assertNotIn(directory, json.dumps(evidence))
            self.assertNotIn("generation", json.dumps(evidence).lower())
            void = kit_module.build_evidence(kit, trial, 0, True)
            self.assertTrue(void["disposition"].startswith("void"))

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

            for name in ("identity", "unit_properties", "first_start", "commission", "restart", "g4", "no_credential",
                         "reranker_down", "recovery", "privacy", "rollback_drill", "resources"):
                setattr(trial, name, ok(name))
            trial.restore_drill = over_ceiling
            trial.prepare_scenarios = lambda: None
            trial.scenario = ok("scenario")
            trial.finish = lambda: 0
            with mock.patch.object(kit_module, "route_checks", return_value={}), \
                    mock.patch.object(sc, "lemond_snapshot", return_value=({}, {})), \
                    contextlib.redirect_stdout(io.StringIO()):
                trial.run()
            self.assertIn("rollback_drill", ran)
            results = {step.id: step.result for step in trial.steps}
            self.assertEqual(results["open-webui.acceptance.drill.restore"], sc.FAIL)
            self.assertEqual(results["open-webui.acceptance.drill.rollback"], sc.PASS)

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
