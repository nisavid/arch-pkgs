import contextlib
import importlib.util
import io
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = REPO_ROOT / "tools" / "open_webui_household_scenarios.py"
STUB = REPO_ROOT / "tools" / "fixtures" / "open-webui-household-acceptance" / "stub_provider.py"
# The trial candidate's open-webui.env and household profile example (exact
# copies of the 0.11.4-2 package files; the kit tests pin their digests).
CANDIDATE = REPO_ROOT / "tools" / "fixtures" / "open-webui-household-acceptance" / "open-webui-0.11.4-2"
PACKAGED_ENV = CANDIDATE / "open-webui.env"
PROFILE_EXAMPLE = CANDIDATE / "household.env.example"
RAG_GATE = REPO_ROOT / "packages" / "open-webui" / "open-webui-rag-gate.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scenarios = load("open_webui_household_scenarios", SCENARIOS)
stub = load("open_webui_household_stub_provider", STUB)


@contextlib.contextmanager
def running_stub():
    server = ThreadingHTTPServer(("127.0.0.1", 0), stub.StubRequestHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def packaged_env():
    """The candidate's vanilla open-webui.env."""

    return scenarios.parse_env_file(PACKAGED_ENV.read_text(encoding="utf-8"))


def candidate_env():
    """The candidate's open-webui.env with its example profile, rendered for the default provider, over it."""

    profile = scenarios.render_household_profile(PROFILE_EXAMPLE.read_text(encoding="utf-8"),
                                                 scenarios.DEFAULT_LEMOND_URL)
    return {**packaged_env(), **scenarios.parse_env_file(profile)}


class RegistryTests(unittest.TestCase):
    def test_scenario_ids_are_frozen_in_order(self):
        self.assertEqual(
            scenarios.SCENARIO_IDS,
            (
                "open-webui.resmoke.zembed-canary",
                "open-webui.resmoke.zerank-qualification",
                "open-webui.resmoke.cited-answer",
                "open-webui.resmoke.stt",
            ),
        )
        self.assertEqual(tuple(scenarios.SCENARIOS), scenarios.SCENARIO_IDS)
        self.assertEqual(scenarios.RECEIPT_SCHEMA, "open-webui-household-resmoke/v1")
        self.assertEqual(scenarios.TARGETS, ("acceptance", "production"))
        with self.assertRaises(TypeError):
            scenarios.SCENARIOS["open-webui.resmoke.extra"] = None

    def test_selection_keeps_registry_order_and_rejects_unknown_ids(self):
        self.assertEqual(scenarios.select_scenarios([]), scenarios.SCENARIO_IDS)
        self.assertEqual(scenarios.select_scenarios(["all"]), scenarios.SCENARIO_IDS)
        self.assertEqual(
            scenarios.select_scenarios(["open-webui.resmoke.stt", "open-webui.resmoke.zembed-canary"]),
            ("open-webui.resmoke.zembed-canary", "open-webui.resmoke.stt"),
        )
        with self.assertRaises(ValueError):
            scenarios.select_scenarios(["open-webui.resmoke.auth"])


class ExitCodeTests(unittest.TestCase):
    def test_exit_code_contract(self):
        codes = scenarios.aggregate_exit_code
        self.assertEqual(codes([]), 0)
        self.assertEqual(codes(["PASS", "PASS"]), 0)
        self.assertEqual(codes(["PASS", "FAIL"]), 1)
        self.assertEqual(codes(["FAIL", "BLOCKED"]), 75)
        self.assertEqual(codes(["ESCALATE"]), 3)
        self.assertEqual(codes(["FAIL", "ESCALATE", "BLOCKED"]), 3)
        with self.assertRaises(ValueError):
            codes(["SKIPPED"])

    def run_with(self, behaviors):
        def scenario(behavior):
            def run(_ctx):
                if behavior is not None:
                    raise behavior
                return {}

            return run

        table = dict(zip(scenarios.SCENARIO_IDS, (scenario(item) for item in behaviors)))
        with mock.patch.object(scenarios, "SCENARIOS", table), contextlib.redirect_stdout(io.StringIO()):
            return scenarios.run_scenarios(object(), ["all"])

    def test_escalation_and_blocked_stop_the_run_and_failures_continue(self):
        escalated = self.run_with([scenarios.Escalation("ESCALATE: zembed canary"), None, None, None])
        self.assertEqual([item.result for item in escalated], ["ESCALATE"])
        blocked = self.run_with([None, scenarios.Blocked(scenarios.NEEDS_OWNER_RESTART), None, None])
        self.assertEqual([item.result for item in blocked], ["PASS", "BLOCKED"])
        self.assertEqual(blocked[1].detail, "NEEDS OWNER: sudo systemctl restart open-webui.service")
        failed = self.run_with([None, None, scenarios.ScenarioFailure("no fact"), None])
        self.assertEqual([item.result for item in failed], ["PASS", "PASS", "FAIL", "PASS"])
        self.assertEqual(scenarios.aggregate_exit_code([item.result for item in failed]), 1)
        self.assertEqual(failed[2].line(), "open-webui.resmoke.cited-answer FAIL ScenarioFailure: no fact")

    def test_a_malformed_response_is_a_fail_row_not_a_crash(self):
        failed = self.run_with([None, AttributeError("'list' object has no attribute 'get'"), KeyError("id"), TypeError("x")])
        self.assertEqual([item.result for item in failed], ["PASS", "FAIL", "FAIL", "FAIL"])

    def resmoke_args(self, tmp, *extra):
        return [
            "resmoke", "--target", "acceptance", "--root", tmp, "--chat-model", "m",
            "--receipt", f"{tmp}/r.json", "--credentials-dir", tmp, "--socket", f"{tmp}/absent.sock", *extra,
        ]

    def acceptance_process(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(scenarios, "open_webui_pid", return_value=1))
        stack.enter_context(mock.patch.object(scenarios, "read_process_environ", return_value=candidate_env()))
        return stack

    def test_an_interrupted_resmoke_leaves_a_failing_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(scenarios, "open_webui_pid", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                scenarios.main(self.resmoke_args(tmp, "--lemond-url", "http://127.0.0.1:9"))
            receipt = json.loads(Path(f"{tmp}/r.json").read_text())
        self.assertEqual(receipt["exit_code"], 1)
        self.assertEqual(receipt["scenarios"][0]["id"], "open-webui.resmoke.run")

    def test_a_plain_http_origin_never_receives_the_smoke_password(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()), \
                mock.patch.object(scenarios, "signin") as signin:
            code = scenarios.main(["resmoke", "--target", "production", "--origin", "http://household.invalid",
                                   "--chat-model", "m", "--receipt", f"{tmp}/r.json"])
            receipt = json.loads(Path(f"{tmp}/r.json").read_text())
        self.assertEqual(code, 75)
        self.assertIn("https", receipt["precondition"])
        signin.assert_not_called()

    def test_an_unreachable_lemonade_is_a_precondition_with_a_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, self.acceptance_process(), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = scenarios.main(self.resmoke_args(tmp, "--lemond-url", "http://127.0.0.1:9"))
            receipt = json.loads(Path(f"{tmp}/r.json").read_text())
        self.assertEqual(code, 75)
        self.assertEqual(receipt["exit_code"], 75)
        self.assertIn("Lemonade is unreachable", receipt["precondition"])

    def test_an_unreachable_open_webui_is_a_precondition_with_a_receipt(self):
        env = candidate_env()
        models, health = (
            {"data": [{"id": item} for item in (env["RAG_EMBEDDING_MODEL"], env["RAG_RERANKING_MODEL"], "m")]},
            {"all_models_loaded": [{"model_name": item} for item in (env["RAG_EMBEDDING_MODEL"], env["RAG_RERANKING_MODEL"], "m")]},
        )
        with tempfile.TemporaryDirectory() as tmp, self.acceptance_process(), \
                mock.patch.object(scenarios, "lemond_snapshot", return_value=(health, models)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            (Path(tmp) / "resmoke-email").write_text("smoke@household.invalid")
            (Path(tmp) / "resmoke-password").write_text("pw")
            code = scenarios.main(self.resmoke_args(tmp))
            receipt = json.loads(Path(f"{tmp}/r.json").read_text())
        self.assertEqual(code, 75)
        self.assertIn("Open WebUI is unreachable", receipt["precondition"])

    def test_a_rehearsal_resmoke_writes_no_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, self.acceptance_process(), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = scenarios.main(self.resmoke_args(tmp, "--lemond-url", "http://127.0.0.1:9", "--mode", "rehearsal"))
            self.assertFalse(Path(f"{tmp}/r.json").exists())
        self.assertEqual(code, 75)

    def test_cli_returns_75_when_a_precondition_is_missing(self):
        for argv in (
            ["resmoke", "--target", "acceptance", "--chat-model", "m"],
            ["resmoke", "--target", "production", "--chat-model", "m"],
        ):
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = scenarios.main([*argv, "--receipt", f"{tmp}/r.json"])
                # A precondition failure still leaves its receipt.
                receipt = json.loads(Path(f"{tmp}/r.json").read_text())
            self.assertEqual(code, 75)
            self.assertEqual(receipt["exit_code"], 75)


class EnvironTests(unittest.TestCase):
    def test_filter_keeps_only_allowlisted_keys(self):
        raw = b"\0".join(
            [
                b"WEBUI_SECRET_KEY=not-for-evidence",
                b"REDIS_URL=redis://open-webui:hunter2@127.0.0.1:16379/0",
                b"QDRANT_API_KEY=jwt",
                b"OAUTH_CLIENT_INFO_ENCRYPTION_KEY=x",
                b"PATH=/usr/bin",
                b"DO_NOT_TRACK=true",
                b"RAG_EMBEDDING_QUERY_PREFIX=<|im_start|>system\nquery<|im_end|>\n<|im_start|>user\n",
                b"RAG_EMBEDDING_MODEL=zembed-1-Q4_K_M-GGUF-Q4_K_M",
                b"NOEQUALS",
                b"",
            ]
        )
        kept = scenarios.filter_environ(raw)
        self.assertEqual(set(kept), {"DO_NOT_TRACK", "RAG_EMBEDDING_QUERY_PREFIX", "RAG_EMBEDDING_MODEL"})
        self.assertEqual(kept["RAG_EMBEDDING_QUERY_PREFIX"], scenarios.ZEMBED_QUERY_HEAD)
        self.assertNotIn("hunter2", json.dumps(kept))

    def test_allowlist_holds_no_secret_bearing_key(self):
        for key in scenarios.ENVIRON_ALLOWLIST:
            self.assertNotRegex(key, r"SECRET|KEY$|PASSWORD|TOKEN|REDIS|OAUTH|_URL")
        self.assertLessEqual(set(scenarios.TELEMETRY_EXPECTED), scenarios.ENVIRON_ALLOWLIST)

    def test_process_environ_read_is_filtered(self):
        with mock.patch.dict(os.environ, {"WEBUI_SECRET_KEY": "x", "DO_NOT_TRACK": "true"}):
            kept = scenarios.read_process_environ(os.getpid())
        self.assertLessEqual(set(kept), scenarios.ENVIRON_ALLOWLIST)
        self.assertNotIn("WEBUI_SECRET_KEY", kept)

    def test_settings_come_from_the_filtered_environ(self):
        settings = scenarios.settings_from_environ(candidate_env())
        self.assertEqual(settings.embedding_model, candidate_env()["RAG_EMBEDDING_MODEL"])
        self.assertEqual(settings.reranking_model, candidate_env()["RAG_RERANKING_MODEL"])
        self.assertTrue(settings.reranking_model.startswith("zerank-2-"))
        with self.assertRaises(scenarios.Blocked):
            scenarios.settings_from_environ({"RAG_EMBEDDING_MODEL": "zembed"})
        with self.assertRaises(scenarios.Blocked):
            scenarios.confirm_model_ids(settings, "user.zembed-1-Q4_K_M-GGUF-Q4_K_M", None)
        scenarios.confirm_model_ids(settings, settings.embedding_model, None)

    def test_frozen_production_settings_come_only_from_committed_acceptance_evidence(self):
        evidence = REPO_ROOT / "docs" / "maintainers" / "evidence"
        of_record = set()
        accepted_entries = {}
        for path in sorted(evidence.glob("open-webui-household-acceptance-*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            for step in document.get("steps", []):
                if step.get("id") == "open-webui.acceptance.identity.archives":
                    for item in (step.get("values") or {}).get("archives", []):
                        of_record.add((item["name"], item["sha256"]))
            expectation = document.get("production_expectation")
            if document.get("disposition") == "accepted" and expectation:
                accepted_entries[expectation["version"]] = expectation["entry"]
        for version, expected in scenarios.PRODUCTION_EXPECTATIONS.items():
            self.assertIn((expected["archive"], expected["archive_sha256"]), of_record, version)
            self.assertEqual(set(expected), {"archive", "archive_sha256", *scenarios.PRODUCTION_EXPECTATION_KEYS})
            # Every value, including the multi-line prefixes, is the entry that
            # accepted evidence printed, so a paste error cannot pass.
            self.assertEqual(dict(expected), accepted_entries.get(version), version)
        with self.assertRaises(scenarios.Blocked):
            scenarios.settings_for_production("0.11.0-3")

    def test_the_trial_derives_the_production_entry_from_the_deployed_archive(self):
        env = candidate_env()
        derived = scenarios.production_expectation("open-webui-0.11.4-2-x86_64.pkg.tar.zst", "a" * 64, env)
        self.assertEqual(derived["version"], "0.11.4-2")
        self.assertEqual(derived["entry"]["archive_sha256"], "a" * 64)
        for key in scenarios.PRODUCTION_EXPECTATION_KEYS:
            self.assertEqual(derived["entry"][key], env[key])
        with self.assertRaises(ValueError):
            scenarios.production_expectation("qdrant-1.19.1-1-x86_64.pkg.tar.zst", "a" * 64, env)

    def test_production_settings_claim_the_digest_only_when_the_cached_archive_matched(self):
        env = candidate_env()
        with tempfile.TemporaryDirectory() as cache:
            name = "open-webui-0.11.4-2-x86_64.pkg.tar.zst"
            (Path(cache) / name).write_bytes(b"exact")
            digest = scenarios.v1._sha256_bytes(b"exact")
            entry = scenarios.production_expectation(name, digest, env)["entry"]
            with mock.patch.object(scenarios, "PRODUCTION_EXPECTATIONS", {"0.11.4-2": entry}):
                verified = scenarios.settings_for_production("0.11.4-2", Path(cache))
                unverified = scenarios.settings_for_production("0.11.4-2", Path(cache) / "absent")
                (Path(cache) / name).write_bytes(b"other")
                with self.assertRaises(scenarios.Blocked):
                    scenarios.settings_for_production("0.11.4-2", Path(cache))
        self.assertTrue(verified.archive_verified)
        self.assertFalse(unverified.archive_verified)
        receipt = scenarios.build_receipt(
            target="production", mode="record", settings=unverified, chat_model="chat", health=None, results=[]
        )
        self.assertIsNone(receipt["open_webui_archive_sha256"])
        self.assertEqual(receipt["open_webui_archive_binding"], "pacman-version-only")
        receipt = scenarios.build_receipt(
            target="production", mode="record", settings=verified, chat_model="chat", health=None, results=[]
        )
        self.assertEqual(receipt["open_webui_archive_sha256"], digest)
        self.assertEqual(receipt["open_webui_archive_binding"], "archive-sha256")


class ProcessTests(unittest.TestCase):
    def fake_cgroup(self, directory, commands):
        base = Path(directory)
        cgroup = base / "sys" / "user.slice" / "owui-acc-open-webui.service"
        cgroup.mkdir(parents=True)
        (cgroup / "cgroup.procs").write_text("".join(f"{pid}\n" for pid in commands))
        for pid, command in commands.items():
            (base / "proc" / str(pid)).mkdir(parents=True)
            (base / "proc" / str(pid) / "cmdline").write_bytes(b"\0".join(command) + b"\0")
        return base

    def pid(self, base):
        with mock.patch.object(scenarios, "_systemctl_show", return_value="/user.slice/owui-acc-open-webui.service"):
            return scenarios.open_webui_pid(cgroup_root=base / "sys", proc_root=base / "proc")

    def test_the_python_process_is_chosen_over_its_bwrap_parent(self):
        bwrap = [b"/usr/bin/bwrap", b"--dev-bind", b"/", b"/", b"--", b"/usr/bin/open-webui", b"serve"]
        python = [b"/usr/bin/python", b"-c", b"from open_webui import app; app()", b"serve"]
        with tempfile.TemporaryDirectory() as directory:
            base = self.fake_cgroup(directory, {100: bwrap, 101: [b"/bin/sh", b"/usr/bin/open-webui"], 102: python})
            self.assertEqual(self.pid(base), 102)
        with tempfile.TemporaryDirectory() as directory:
            base = self.fake_cgroup(directory, {100: bwrap, 102: python, 103: python})
            with self.assertRaises(scenarios.Blocked):
                self.pid(base)
        with tempfile.TemporaryDirectory() as directory:
            base = self.fake_cgroup(directory, {100: bwrap})
            with self.assertRaises(scenarios.Blocked):
                self.pid(base)


class TemplateTests(unittest.TestCase):
    def test_acceptance_caddyfile_is_loopback_internal_tls_under_the_root(self):
        root = Path("/srv/build/arch-pkgs-owui-acceptance")
        text = scenarios.render_acceptance_caddyfile(root, Path("/run/user/1000/owui-acc/open-webui.sock"))
        for line in (
            "admin off",
            "auto_https disable_redirects",
            "skip_install_trust",
            "default_bind 127.0.0.1",
            f"storage file_system {root}/state/caddy",
            "https://localhost:18443 {",
            "bind 127.0.0.1",
            "tls internal",
            "reverse_proxy unix//run/user/1000/owui-acc/open-webui.sock",
        ):
            self.assertIn(line, text)
        self.assertNotRegex(text, r"(?m)^\s*(http://|:80\b)")
        self.assertNotIn("@", text)
        self.assertEqual(
            scenarios.acceptance_caddy_root_certificate(root),
            root / "state/caddy/pki/authorities/local/root.crt",
        )

    def test_production_site_block_has_no_global_options(self):
        text = scenarios.render_template(
            "open-webui.caddy.in",
            {
                "GLOBAL_OPTIONS": "",
                "SITE_ADDRESS": "https://household.invalid",
                "BIND": "127.0.0.1",
                "TLS": "internal",
                "SOCKET": "/run/open-webui/open-webui.sock",
            },
        )
        self.assertNotIn("{\n\tadmin off", text)
        self.assertIn("reverse_proxy unix//run/open-webui/open-webui.sock", text)

    def test_template_tokens_must_match_exactly(self):
        with self.assertRaises(ValueError):
            scenarios.render_template("valkey-open-webui.conf.in", {"PORT": "16379", "ACL_FILE": "/a"})
        with self.assertRaises(ValueError):
            scenarios.render_template(
                "valkey-open-webui.conf.in", {"PORT": "1", "ACL_FILE": "/a", "DIR": "/d", "EXTRA": "x"}
            )
        with self.assertRaises(ValueError):
            scenarios.render_template(
                "valkey-open-webui.conf.in", {"PORT": "1", "ACL_FILE": "/a\nappendonly yes", "DIR": "/d"}
            )

    def test_valkey_is_rdb_only_and_the_acl_holds_only_a_hash(self):
        conf = scenarios.render_valkey_config(16379, Path("/r/etc/valkey.acl"), Path("/r/state/valkey"))
        self.assertIn("appendonly no", conf)
        self.assertNotIn("appendonly yes", conf)
        self.assertIn("bind 127.0.0.1\nport 16379\nprotected-mode yes", conf)
        self.assertIn("aclfile /r/etc/valkey.acl", conf)
        self.assertIn("dbfilename dump.rdb", conf)
        self.assertIn("maxmemory-policy noeviction", conf)
        digest = scenarios.valkey_password_hash("correct horse")
        acl = scenarios.render_valkey_acl(digest)
        self.assertIn("user default off", acl)
        self.assertIn(f"user open-webui on #{digest} ", acl)
        self.assertNotIn("correct horse", acl)
        with self.assertRaises(ValueError):
            scenarios.render_valkey_acl("correct horse")

    def test_the_expected_connection_is_one_credential_free_provider(self):
        expected = scenarios.expected_connection()
        self.assertEqual(expected, {
            "ENABLE_OLLAMA_API": "false",
            "ENABLE_OPENAI_API": "true",
            "OPENAI_API_BASE_URLS": "http://127.0.0.1:13305/api/v1",
            "OPENAI_API_KEYS": "",
        })
        self.assertEqual(scenarios.speech_environment(), {"WHISPER_MODEL": "base", "HF_HUB_OFFLINE": "1"})
        self.assertEqual(scenarios.speech_environment("tiny")["WHISPER_MODEL"], "tiny")
        # The packaged env turns both APIs off; the rendered profile turns the
        # OpenAI-compatible one back on for the provider.
        env = candidate_env()
        self.assertEqual({key: env[key] for key in expected}, expected)
        self.assertEqual((packaged_env()["ENABLE_OLLAMA_API"], packaged_env()["ENABLE_OPENAI_API"]), ("false", "false"))


class OverlayTests(unittest.TestCase):
    def test_overlay_keys_equal_the_allowlist(self):
        env = candidate_env()
        root = Path("/srv/build/arch-pkgs-owui-acceptance")
        overlay = scenarios.acceptance_overlay(env, root)
        self.assertEqual(set(overlay), scenarios.overlay_allowlist(env))
        path_keys = {key for key, value in env.items() if "/var/lib/open-webui" in value}
        self.assertEqual(scenarios.packaged_state_path_keys(env), path_keys)
        self.assertEqual(
            path_keys,
            {
                "STATIC_DIR",
                "DATA_DIR",
                "DATABASE_URL",
                "CACHE_DIR",
                "HF_HOME",
                "SENTENCE_TRANSFORMERS_HOME",
                "TIKTOKEN_CACHE_DIR",
                "WHISPER_MODEL_DIR",
            },
        )
        self.assertFalse(any("/var/lib/open-webui" in value for value in overlay.values()))
        self.assertEqual(overlay["DATABASE_URL"], f"sqlite:///{root}/state/open-webui/data/webui.db")
        self.assertEqual(overlay["QDRANT_URI"], "http://127.0.0.1:16333")
        self.assertEqual(overlay["RAG_EXTERNAL_RERANKER_URL"], "http://127.0.0.1:13306/api/v1/rerank")
        self.assertNotIn("RAG_OPENAI_API_BASE_URL", overlay)
        rendered = scenarios.render_overlay(overlay)
        self.assertEqual(scenarios.parse_env_file(rendered), overlay)

    def test_overlay_never_sets_the_provider_connection(self):
        # The rendered profile carries the provider for both modes; the overlay
        # only relays the reranker.
        overlay = scenarios.acceptance_overlay(candidate_env(), Path("/r"), relay_port=13306)
        for key in ("ENABLE_OLLAMA_API", "ENABLE_OPENAI_API", "OPENAI_API_BASE_URLS", "OPENAI_API_KEYS",
                    "RAG_OPENAI_API_BASE_URL"):
            self.assertNotIn(key, overlay)
        self.assertEqual(overlay["RAG_EXTERNAL_RERANKER_URL"], "http://127.0.0.1:13306/api/v1/rerank")

    def test_overlay_never_touches_secret_or_telemetry_keys(self):
        allowed = scenarios.overlay_allowlist(candidate_env())
        for key in ("WEBUI_SECRET_KEY", "REDIS_URL", "QDRANT_API_KEY", "DO_NOT_TRACK", "OFFLINE_MODE", "ENABLE_SIGNUP",
                    "ENABLE_OPENAI_API", "OPENAI_API_BASE_URLS", "OPENAI_API_KEYS"):
            self.assertNotIn(key, allowed)


class LemonadeSafetyTests(unittest.TestCase):
    def test_no_code_path_mutates_lemonade(self):
        self.assertEqual(
            set(scenarios.LEMOND_API.values()),
            {"/api/v1/health", "/api/v1/models", "/api/v1/embeddings", "/api/v1/rerank"},
        )
        for path in (SCENARIOS, STUB):
            source = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"/api/v1/(load|unload|pull|delete|pin|params|install)\b", source), path
            )

    def test_models_must_be_served_and_already_loaded(self):
        models = {"data": [{"id": "a"}, {"id": "b"}, {"id": "chat"}]}
        health = {"all_models_loaded": [{"model_name": "a"}, {"model_name": "b"}]}
        with self.assertRaisesRegex(scenarios.Blocked, "does not serve c"):
            scenarios.require_models_ready(models, health, ("a", "c"))
        with self.assertRaisesRegex(scenarios.Blocked, "has not loaded chat"):
            scenarios.require_models_ready(models, health, ("a", "b", "chat"))
        scenarios.require_models_ready(models, health, ("a", "b"))

    def test_a_user_prefixed_id_and_its_bare_name_are_the_same_model(self):
        canonical = "user.Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL"
        bare = "Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL"
        self.assertEqual(scenarios.bare_model_id(canonical), bare)
        self.assertEqual(scenarios.bare_model_id(bare), bare)
        self.assertEqual(scenarios.bare_model_id("user.user.x"), "user.x")
        for listed, wanted in ((bare, canonical), (canonical, bare), (canonical, canonical), (bare, bare)):
            models = {"data": [{"id": "e"}, {"id": listed}]}
            health = {"all_models_loaded": [{"model_name": "e"}, {"model_name": listed}]}
            scenarios.require_models_ready(models, health, ("e", wanted))
        loaded_bare = {"all_models_loaded": [{"model_name": "e"}], "model_loaded": bare}
        scenarios.require_models_ready({"data": [{"id": canonical}]}, loaded_bare, (canonical,))
        with self.assertRaisesRegex(scenarios.Blocked, "has not loaded"):
            scenarios.require_models_ready(
                {"data": [{"id": bare}]}, {"all_models_loaded": [{"model_name": "e"}]}, (canonical,)
            )
        with self.assertRaisesRegex(scenarios.Blocked, "does not serve"):
            scenarios.require_models_ready({"data": [{"id": "user.other"}]}, {}, (canonical,))

    def test_a_served_user_id_and_a_distinct_bare_id_make_the_pin_ambiguous(self):
        models = {"data": [{"id": "user.X"}, {"id": "X"}]}
        loaded = {"all_models_loaded": [{"model_name": "X"}]}
        for wanted in ("user.X", "X"):
            with self.assertRaisesRegex(scenarios.Blocked, "ambiguous"):
                scenarios.require_models_ready(models, loaded, (wanted,))
        both_loaded = {"all_models_loaded": [{"model_name": "user.X"}, {"model_name": "X"}]}
        with self.assertRaisesRegex(scenarios.Blocked, "ambiguous"):
            scenarios.require_models_ready({"data": [{"id": "user.X"}]}, both_loaded, ("user.X",))

    def test_the_open_webui_chat_id_is_the_listed_form_of_the_designated_model(self):
        canonical = scenarios.DEFAULT_CHAT_MODEL
        bare = scenarios.bare_model_id(canonical)
        self.assertEqual(canonical, "user.Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL")
        self.assertEqual(scenarios.listed_model_id({bare, "x"}, canonical), bare)
        self.assertEqual(scenarios.listed_model_id({canonical, bare}, canonical), canonical)
        self.assertEqual(scenarios.listed_model_id({canonical}, bare), canonical)
        self.assertIsNone(scenarios.listed_model_id({"x"}, canonical))

    class FakeWebui:
        """Open WebUI's admin routes for configure: a model list and a model-entry table."""

        def __init__(self, listed, registered=(), inaccessible=(), create_status=200, raced=False):
            self.listed = listed
            # raced: another writer registers the model while this create fails.
            self.raced = raced
            self.registered = set(registered)
            self.inaccessible = set(inaccessible)
            self.create_status = create_status
            self.posted = {}
            self.creates = []

        def json(self, method, path, payload=None, token=None):
            if method == "POST":
                self.posted[path] = payload
                return {}
            return {"data": [{"id": item} for item in self.listed]} if path == scenarios.API["models"] else {}

        def request(self, method, path, payload=None, token=None, **_):
            if method == "POST" and path == scenarios.API["model_create"]:
                assert payload is not None
                self.creates.append(payload)
                if self.create_status == 200 or self.raced:
                    self.registered.add(payload["id"])
                if self.create_status == 200:
                    return scenarios.Response(200, "application/json", json.dumps(payload).encode())
                return scenarios.Response(self.create_status, "application/json", b'{"detail":"taken"}')
            prefix = scenarios.API["model"].split("{")[0]
            if method == "GET" and path.startswith(prefix):
                model_id = scenarios.urllib.parse.unquote(path[len(prefix):])
                if model_id in self.inaccessible:
                    return scenarios.Response(401, "application/json", b'{"detail":"prohibited"}')
                if model_id in self.registered:
                    return scenarios.Response(200, "application/json", b"{}")
                return scenarios.Response(404, "application/json", b'{"detail":"We could not find what you are looking for :/"}')
            raise AssertionError(f"unexpected {method} {path}")

    def test_configure_registers_the_listed_chat_model_and_sets_it_as_the_default(self):
        bare = scenarios.bare_model_id(scenarios.DEFAULT_CHAT_MODEL)
        webui = self.FakeWebui([bare])
        summary = scenarios.configure(webui, "t", chat_model=scenarios.DEFAULT_CHAT_MODEL)
        self.assertEqual(webui.posted[scenarios.API["models_config"]]["DEFAULT_MODELS"], bare)
        self.assertEqual(summary["chat_model"], bare)
        self.assertEqual(summary["chat_model_registration"], "created")
        self.assertEqual(summary["designated_chat_model"], scenarios.DEFAULT_CHAT_MODEL)
        self.assertEqual(summary["whisper_model"], "base")
        # The entry is the 0.11.4 ModelForm for the connection's own model.
        self.assertEqual(webui.creates, [{"id": bare, "base_model_id": None, "name": bare, "meta": {}, "params": {}}])
        self.assertEqual(scenarios.webui_chat_model(webui, "t", scenarios.DEFAULT_CHAT_MODEL), bare)

    def test_registering_the_chat_model_is_idempotent(self):
        webui = self.FakeWebui(["chat"], registered={"chat"})
        self.assertEqual(scenarios.configure(webui, "t", chat_model="chat")["chat_model_registration"], "existing")
        self.assertEqual(webui.creates, [])
        # A create that loses a race to another writer still ends registered.
        racing = self.FakeWebui(["chat"], create_status=401, raced=True)
        self.assertEqual(scenarios.register_chat_model(racing, "t", "chat"), "existing")
        # A create that fails outright is a failure that names Open WebUI's detail.
        failing = self.FakeWebui(["chat"], create_status=400)
        with self.assertRaisesRegex(scenarios.ScenarioFailure, "HTTP 400: taken"):
            scenarios.register_chat_model(failing, "t", "chat")

    def test_the_chat_precondition_refuses_a_listed_but_unregistered_model(self):
        webui = self.FakeWebui(["chat"])
        with self.assertRaisesRegex(scenarios.Blocked, "lists the chat model chat but has no model entry"):
            scenarios.webui_chat_model(webui, "t", "chat")
        self.assertEqual(webui.creates, [])
        hidden = self.FakeWebui(["chat"], inaccessible={"chat"})
        with self.assertRaisesRegex(scenarios.Blocked, "grant this account read access"):
            scenarios.webui_chat_model(hidden, "t", "chat")
        with self.assertRaisesRegex(scenarios.Blocked, "cannot read"):
            scenarios.register_chat_model(hidden, "t", "chat")
        with self.assertRaisesRegex(scenarios.Blocked, "does not list"):
            scenarios.webui_chat_model(self.FakeWebui(["other"]), "t", "chat")

    def test_the_resmoke_chat_model_defaults_to_the_owner_pin(self):
        args = scenarios._parser().parse_args(["resmoke", "--target", "production", "--receipt", "r.json"])
        self.assertEqual(args.chat_model, scenarios.DEFAULT_CHAT_MODEL)
        self.assertEqual(args.whisper_model, "base")

    def test_rerank_results_are_validated(self):
        self.assertEqual(
            scenarios.validate_rerank_results(
                [{"index": 1, "relevance_score": 0.1}, {"index": 0, "relevance_score": 0.9}], 2
            ),
            [0.9, 0.1],
        )
        for bad in (
            [{"index": 0, "relevance_score": 0.9}],
            [{"index": 0, "relevance_score": math.nan}, {"index": 1, "relevance_score": 0.1}],
            [{"index": 0, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}],
            [{"index": True, "relevance_score": 0.9}, {"index": 1, "relevance_score": 0.1}],
        ):
            with self.assertRaises(scenarios.ScenarioFailure):
                scenarios.validate_rerank_results(bad, 2)

    def test_rag_gate_constants_are_read_from_the_packaged_gate(self):
        gate = load("open_webui_rag_gate_for_scenarios", RAG_GATE)
        self.assertEqual(
            scenarios.rag_gate_constants(),
            (gate.RAG_QUALIFICATION_QUERY, tuple(gate.RAG_QUALIFICATION_DOCUMENTS)),
        )


class CitedAnswerTests(unittest.TestCase):
    def test_constants_match_the_v1_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = scenarios.v1.generate_fixture(Path(tmp), materialize_heavy=False)
        self.assertEqual(fixture["canonical_fact"], scenarios.CANONICAL_FACT)
        self.assertEqual(fixture["canonical_query"], scenarios.CANONICAL_QUERY)
        self.assertEqual(fixture["canonical_citation"], scenarios.CANONICAL_CITATION)
        self.assertIn(scenarios.CANONICAL_FACT.encode(), scenarios.handbook_bytes())

    def test_streamed_and_plain_chat_replies_parse(self):
        source = {"source": {"id": "f1", "name": "winter-garden-handbook.md"}, "distances": [0.83]}
        stream = (
            "data: " + json.dumps({"sources": [source]}) + "\n\n"
            "data: " + json.dumps({"choices": [{"delta": {"content": "The brass key opens "}}]}) + "\n\n"
            "data: " + json.dumps({"choices": [{"delta": {"content": "the seed cabinet."}}]}) + "\n\n"
            "data: [DONE]\n\n"
        ).encode()
        text, sources = scenarios.parse_chat_response(stream, "text/event-stream; charset=utf-8")
        summary = scenarios.summarize_sources(sources)
        self.assertTrue(scenarios.cited_answer_passes(text, summary, "winter-garden-handbook.md"))
        plain = json.dumps(
            {"choices": [{"message": {"content": "The brass key opens the seed cabinet."}}], "sources": [source, source]}
        ).encode()
        text, sources = scenarios.parse_chat_response(plain, "application/json")
        self.assertEqual(scenarios.summarize_sources(sources)["count"], 1)

    def open_webui_0_11_4_source(self, file_id="f1", names=(None,), scores=(0.2778, 0.0556, 0.0)):
        """A file source as Open WebUI 0.11.4 streams it to an API client.

        ``source`` echoes the request's file item, which carries no name; each
        chunk's metadata carries the upload name as ``name`` and ``source``.
        """

        metadata = [{"file_id": file_id, "name": name, "source": name, "created_by": "u1"} if name else {"file_id": file_id}
                    for name in names]
        return {"source": {"type": "file", "id": file_id}, "document": ["chunk"] * len(metadata),
                "metadata": metadata, "distances": list(scores)}

    def test_a_0_11_4_file_source_is_named_by_its_chunks_upload_name(self):
        handbook = scenarios.HANDBOOK_NAME
        fact = "The brass key opens the seed cabinet."
        source = self.open_webui_0_11_4_source(names=(handbook,) * 3)
        summary = scenarios.summarize_sources([source])
        self.assertEqual(summary, {"count": 1, "names": [handbook], "scores": [0.2778, 0.0556, 0.0]})
        self.assertTrue(scenarios.cited_answer_passes(fact, summary, handbook))
        # A chunk that names its upload only as "source" still counts.
        only_source = {**source, "metadata": [{"file_id": "f1", "source": handbook}]}
        self.assertEqual(scenarios.summarize_sources([only_source])["names"], [handbook])
        # The check stays filename-only: another upload name, or none at all
        # (the rehearsal's names [null]), fails.
        for names in (("other.md",), (None,)):
            summary = scenarios.summarize_sources([self.open_webui_0_11_4_source(names=names)])
            self.assertFalse(scenarios.cited_answer_passes(fact, summary, handbook), names)
        self.assertEqual(scenarios.summarize_sources([self.open_webui_0_11_4_source()])["names"], [None])
        # One source whose chunks cite two files is two names, not the handbook.
        mixed = scenarios.summarize_sources([self.open_webui_0_11_4_source(names=(handbook, "other.md"))])
        self.assertEqual(mixed["names"], [handbook, "other.md"])
        self.assertFalse(scenarios.cited_answer_passes(fact, mixed, handbook))
        # The web UI's item carries its name; with no chunk name it is the fallback.
        ui = {"source": {"type": "file", "id": "f1", "name": handbook}, "distances": [0.9]}
        self.assertEqual(scenarios.summarize_sources([ui])["names"], [handbook])

    def cited_context(self, delete_status, chat_status=200):
        events = [
            {"sources": [{"source": {"id": "f1", "name": scenarios.HANDBOOK_NAME}, "distances": [0.9]}]},
            {"choices": [{"delta": {"content": scenarios.CANONICAL_FACT}}]},
        ]
        stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode() + b"data: [DONE]\n\n"
        responses = {
            ("POST", scenarios.API["files"]): mock.Mock(status=200, json=lambda: {"id": "f1"}),
            ("POST", scenarios.API["chat"]): mock.Mock(status=chat_status, body=stream, content_type="text/event-stream"),
        }
        deletes = []

        def request(method, path, **_kw):
            if method == "DELETE":
                deletes.append(path)
                if isinstance(delete_status, Exception):
                    raise delete_status
                return mock.Mock(status=delete_status)
            return responses[(method, path)]

        webui = mock.Mock(request=mock.Mock(side_effect=request))
        ctx = scenarios.Context(target="production", webui=webui, lemond=mock.Mock(), token="t",
                                settings=scenarios.settings_from_environ(candidate_env()), chat_model="m")
        return ctx, deletes

    def test_cited_answer_deletes_its_upload_and_fails_when_the_delete_fails(self):
        with mock.patch.object(scenarios, "_wait_for_file"):
            ctx, deletes = self.cited_context(200)
            values = scenarios.cited_answer(ctx)
            self.assertEqual(values["expected_source_name"], scenarios.HANDBOOK_NAME)
            self.assertEqual(len(deletes), 1)
            ctx, deletes = self.cited_context(500)
            with self.assertRaisesRegex(scenarios.ScenarioFailure, "delete returned 500"):
                scenarios.cited_answer(ctx)
            # A failing chat keeps its own error even when the cleanup also fails.
            ctx, deletes = self.cited_context(OSError("gone"), chat_status=502)
            with self.assertRaisesRegex(scenarios.ScenarioFailure, "HTTP 502"):
                scenarios.cited_answer(ctx)
            self.assertEqual(len(deletes), 1)

    def test_a_failed_file_reports_the_error_open_webui_stored(self):
        stored = "Unexpected Response: 400 (Bad Request) Limit exceeded 999999999 > 1000 for \"limit\""
        ctx, deletes = self.cited_context(200)
        fixed = ctx.webui.request.side_effect

        def request(method, path, **kw):
            if (method, path) == ("GET", scenarios.API["file_status"].format(id="f1")):
                return scenarios.Response(200, "application/json", b'{"status": "failed"}')
            if (method, path) == ("GET", scenarios.API["file"].format(id="f1")):
                record = {"id": "f1", "data": {"status": "failed", "error": stored}}
                return scenarios.Response(200, "application/json", json.dumps(record).encode())
            return fixed(method, path, **kw)

        ctx.webui.request.side_effect = request
        with self.assertRaises(scenarios.ScenarioFailure) as raised:
            scenarios.cited_answer(ctx)
        self.assertIn("status failed", str(raised.exception))
        self.assertIn(stored, str(raised.exception))
        self.assertEqual(len(deletes), 1)

    def test_cited_answer_rejects_extra_sources_and_non_finite_scores(self):
        fact = scenarios.CANONICAL_FACT
        two = {"count": 2, "names": ["a", "b"], "scores": [0.5, 0.4]}
        nan = {"count": 1, "names": ["a"], "scores": [math.nan]}
        none = {"count": 1, "names": ["a"], "scores": []}
        for summary in (two, nan, none):
            self.assertFalse(scenarios.cited_answer_passes(fact, summary, "a"))
        self.assertFalse(scenarios.cited_answer_passes("No idea.", {"count": 1, "names": ["a"], "scores": [1.0]}, "a"))


class SpeechTests(unittest.TestCase):
    def test_transcription_pass_condition(self):
        text = (
            "And so my fellow Americans, ask not what your country can do for you, "
            "ask what you can do for your country."
        )
        self.assertTrue(scenarios.transcription_passes(text, "en"))
        self.assertTrue(scenarios.transcription_passes(text, None))
        self.assertFalse(scenarios.transcription_passes(text, "de"))
        self.assertFalse(scenarios.transcription_passes("ask not what your country can do for you", "en"))

    def test_provider_rebuild_needs_an_owner_restart(self):
        self.assertTrue(scenarios.provider_restart_needed(100.0, 200.0))
        self.assertTrue(scenarios.provider_restart_needed(None, 200.0))
        self.assertFalse(scenarios.provider_restart_needed(300.0, 200.0))
        self.assertFalse(scenarios.provider_restart_needed(300.0, None))

    def test_ported_pins_match_the_merged_speech_evidence(self):
        relative = "docs/maintainers/evidence/speech-providers-4.8.2-1.2.1/g0-g2.json"
        self.assertIn(relative, SCENARIOS.read_text(encoding="utf-8"))
        evidence = json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))
        inputs = evidence["gates"]["G2"]["fixture"]["inputs"]
        whisper = inputs["whisper_model"]
        self.assertEqual(scenarios.WHISPER_TINY["repository"], whisper["repository"])
        self.assertEqual(scenarios.WHISPER_TINY["revision"], whisper["revision"])
        self.assertEqual(scenarios.WHISPER_TINY["files"]["model.bin"], whisper["model.bin_sha256"])
        self.assertEqual(scenarios.JFK_FLAC_SHA256, inputs["audio"]["sha256"])

    def test_whisper_base_is_the_default_and_pinned_by_revision_and_file_digests(self):
        self.assertEqual(scenarios.DEFAULT_WHISPER_MODEL, "base")
        self.assertEqual(set(scenarios.WHISPER_PINS), {"base", "tiny"})
        base = scenarios.whisper_pin_record("base")
        self.assertEqual(base["repository"], "Systran/faster-whisper-base")
        self.assertEqual(base["revision"], "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66")
        self.assertEqual(
            base["files"]["model.bin"], "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"
        )
        tiny = scenarios.whisper_pin_record("tiny")
        self.assertEqual(
            tiny["files"]["model.bin"], "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1"
        )
        for record in (base, tiny):
            self.assertEqual(set(record["files"]), {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"})
            for digest in record["files"].values():
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
            json.dumps(record)


def unit_vector(*components, dimensions=2560):
    vector = [0.0] * dimensions
    for index, value in enumerate(components):
        vector[index] = value
    return vector


class ZembedCanaryTests(unittest.TestCase):
    """The canary's record: per-vector dimensions and norms, kept on escalation."""

    QUERY = unit_vector(1.0)
    RELEVANT = unit_vector(0.9, math.sqrt(1 - 0.81))
    UNRELATED = unit_vector(0.0, 0.0, 1.0)

    def context(self, stored_chunk=None):
        settings = scenarios.settings_from_environ(candidate_env())
        endpoint = scenarios.Endpoint(origin="http://127.0.0.1:9")
        return scenarios.Context(target="acceptance", webui=endpoint, lemond=endpoint, token="", settings=settings,
                                 chat_model="chat", stored_chunk=stored_chunk)

    def run_canary(self, *, unrelated=None, stored_chunk=None, direct=None):
        def embed(_ctx, text):
            for canary, vector in ((scenarios.CANARY_QUERY, self.QUERY), (scenarios.CANARY_RELEVANT, self.RELEVANT),
                                   (scenarios.CANARY_UNRELATED, unrelated or self.UNRELATED)):
                if text.endswith(canary):
                    return vector
            return direct

        with mock.patch.object(scenarios, "lemond_embed", side_effect=embed):
            return scenarios.run_scenario(self.context(stored_chunk), "open-webui.resmoke.zembed-canary")

    def test_a_pass_records_every_vectors_dimensions_and_norm(self):
        outcome = self.run_canary(stored_chunk=lambda: ("chunk", self.QUERY), direct=self.QUERY)
        self.assertEqual(outcome.result, scenarios.PASS)
        vectors = outcome.values["vectors"]
        self.assertEqual(sorted(vectors), ["direct_chunk", "query", "relevant", "stored_chunk", "unrelated"])
        for name, record in vectors.items():
            self.assertEqual(record["dimensions"], 2560, name)
            self.assertAlmostEqual(record["norm"], 1.0, places=9, msg=name)
        self.assertEqual(outcome.values["margin"], 0.9)
        self.assertEqual(outcome.values["stored_vector_cosine"], 1.0)

    def test_an_escalation_keeps_the_values_it_computed(self):
        # A norm outside the tolerance escalates before the stored-vector check.
        outcome = self.run_canary(unrelated=unit_vector(0.0, 0.0, 2.0),
                                  stored_chunk=lambda: self.fail("the stored chunk is read only after a pass"))
        self.assertEqual(outcome.result, scenarios.ESCALATE)
        self.assertEqual(outcome.detail, "ESCALATE: zembed canary")
        self.assertEqual(outcome.values["vectors"]["unrelated"], {"dimensions": 2560, "norm": 2.0})
        self.assertEqual(outcome.values["vectors"]["query"], {"dimensions": 2560, "norm": 1.0})
        self.assertEqual(outcome.values["margin"], 0.9)
        self.assertEqual(outcome.values["texts"]["query"], scenarios.CANARY_QUERY)
        self.assertEqual(outcome.values["prefix_source"], scenarios.settings_from_environ(candidate_env()).source)
        # A stored vector that differs from the settings-prefixed one escalates
        # with its cosine and both chunk vectors recorded.
        outcome = self.run_canary(stored_chunk=lambda: ("chunk", self.QUERY), direct=self.UNRELATED)
        self.assertEqual(outcome.result, scenarios.ESCALATE)
        self.assertIn("stored vector", outcome.detail)
        self.assertEqual(outcome.values["stored_vector_cosine"], 0.0)
        self.assertEqual(outcome.values["vectors"]["direct_chunk"], {"dimensions": 2560, "norm": 1.0})
        self.assertEqual(outcome.values["margin"], 0.9)
        # A stored vector holding NaN has a NaN cosine, which the old
        # "similarity < 0.999" comparison let pass; it escalates.
        outcome = self.run_canary(stored_chunk=lambda: ("chunk", unit_vector(math.nan)), direct=self.QUERY)
        self.assertEqual(outcome.result, scenarios.ESCALATE)
        self.assertIn("stored vector", outcome.detail)
        self.assertIsNone(outcome.values["stored_vector_cosine"])
        self.assertIsNone(outcome.values["vectors"]["stored_chunk"]["norm"])
        json.dumps(outcome.values, allow_nan=False)
        # A stored vector of another length, or a zero stored vector, has no
        # cosine; both escalate (exit 3) rather than fail.
        for stored in (unit_vector(1.0, dimensions=1024), unit_vector()):
            outcome = self.run_canary(stored_chunk=lambda stored=stored: ("chunk", stored), direct=self.QUERY)
            self.assertEqual(outcome.result, scenarios.ESCALATE)
            self.assertIsNone(outcome.values["stored_vector_cosine"])
            self.assertEqual(outcome.values["vectors"]["stored_chunk"]["dimensions"], len(stored))
        # A non-finite vector escalates with JSON-safe values.
        outcome = self.run_canary(unrelated=unit_vector(math.nan))
        self.assertEqual(outcome.result, scenarios.ESCALATE)
        self.assertIsNone(outcome.values["vectors"]["unrelated"]["norm"])
        self.assertIsNone(outcome.values["margin"])
        json.dumps(outcome.values, allow_nan=False)


class ErrorDetailTests(unittest.TestCase):
    """Failure messages carry the HTTP status and Open WebUI's detail, bounded and public-safe."""

    def response(self, status, body, content_type="application/json"):
        return scenarios.Response(status, content_type, body)

    def test_the_detail_comes_from_the_json_detail_or_the_body(self):
        detail = scenarios.response_detail
        self.assertEqual(detail(self.response(400, b'{"detail":"Model not found"}')), "Model not found")
        self.assertEqual(detail(self.response(500, b'{"error":{"message":"upstream failed"}}')), "upstream failed")
        self.assertEqual(detail(self.response(422, b'{"detail":[{"loc":["body","id"],"msg":"field required"}]}')),
                         '[{"loc": ["body", "id"], "msg": "field required"}]')
        self.assertEqual(detail(self.response(502, b"Bad Gateway\n\n", "text/plain")), "Bad Gateway")
        self.assertIsNone(detail(self.response(500, b"")))
        self.assertEqual(scenarios.error_detail(self.response(500, b"")), "")
        self.assertEqual(scenarios.error_detail(self.response(400, b'{"detail":"Model not found"}')), ": Model not found")

    def test_the_detail_is_bounded_and_redacted(self):
        text = ("failed reading /var/lib/example/data/webui.db for admin@example.org "
                "from 203.0.113.7 with Bearer abc123 token=xyz")
        detail = scenarios.public_detail(text)
        for private in ("/var/lib/example", "admin@example.org", "203.0.113.7", "abc123", "xyz"):
            self.assertNotIn(private, detail)
        self.assertIn("<path>", detail)
        self.assertLessEqual(len(scenarios.public_detail("x" * 1000)), scenarios.ERROR_DETAIL_LIMIT)
        scenarios.v1.assert_public_safe({"detail": detail})

    def test_a_failed_json_call_names_the_status_and_the_detail(self):
        endpoint = scenarios.Endpoint(origin="http://127.0.0.1:9")
        with mock.patch.object(endpoint, "request", return_value=self.response(400, b'{"detail":"Model not found"}')):
            with self.assertRaisesRegex(scenarios.ScenarioFailure,
                                        r"^POST /api/v1/models/model returned HTTP 400: Model not found$"):
                endpoint.json("POST", "/api/v1/models/model?id=x", {})


class ReceiptTests(unittest.TestCase):
    def test_receipt_is_public_safe_and_carries_the_exit_code(self):
        settings = scenarios.settings_from_environ(candidate_env())
        results = [
            scenarios.ScenarioResult("open-webui.resmoke.zembed-canary", "PASS", "ok", 1.0, {"margin": 0.3}),
            scenarios.ScenarioResult("open-webui.resmoke.zerank-qualification", "FAIL", "HTTP 500", 0.1),
        ]
        receipt = scenarios.build_receipt(
            target="production",
            mode="record",
            settings=settings,
            chat_model="chat",
            health={"version": "10.0.0", "all_models_loaded": []},
            results=results,
        )
        self.assertEqual(receipt["schema"], "open-webui-household-resmoke/v1")
        self.assertEqual(receipt["exit_code"], 1)
        self.assertEqual(receipt["lemonade"], {"version": "10.0.0"})
        self.assertIsNone(receipt["open_webui_archive_sha256"])
        self.assertIsNone(receipt["open_webui_archive_binding"])
        blocked = scenarios.build_receipt(
            target="acceptance", mode="rehearsal", settings=None, chat_model="chat",
            health=None, results=[], precondition="NEEDS LEAD: Lemonade has not loaded chat",
        )
        self.assertEqual(blocked["exit_code"], 75)
        with self.assertRaises(ValueError):
            scenarios.build_receipt(
                target="production", mode="record", settings=settings, chat_model="chat",
                health=None, results=[scenarios.ScenarioResult("x", "FAIL", "token=abc", 0.0)],
            )


    UNSAFE = ("cannot read /home/someone/handbook.md from 192.168.1.20 or fd12:3456::7 for admin@example.org "
              "with api_key=k1 at nas.lan")

    def assert_redacted(self, text):
        for private in ("/home/someone", "192.168.1.20", "fd12:3456::7", "admin@example.org", "k1", "nas.lan"):
            self.assertNotIn(private, text)
        scenarios.v1.assert_public_safe({"detail": text})

    def test_an_unsafe_failure_still_writes_a_public_safe_receipt(self):
        settings = scenarios.settings_from_environ(candidate_env())

        def failing(_ctx):
            raise scenarios.ScenarioFailure(self.UNSAFE)

        def blocked(_ctx):
            raise scenarios.Blocked("NEEDS OWNER: " + self.UNSAFE)

        table = {"open-webui.resmoke.zembed-canary": failing, "open-webui.resmoke.zerank-qualification": blocked}
        with mock.patch.object(scenarios, "SCENARIOS", table):
            results = [scenarios.run_scenario(object(), scenario_id) for scenario_id in table]
        for result in results:
            self.assert_redacted(result.detail)
        self.assertTrue(results[0].detail.startswith("ScenarioFailure: cannot read <path>"))
        receipt = scenarios.build_receipt(target="production", mode="record", settings=settings, chat_model="chat",
                                          health=None, results=results)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            scenarios.write_receipt(path, receipt)
            self.assert_redacted(path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["exit_code"], 75)

    def test_a_failed_files_stored_error_is_redacted(self):
        class Webui:
            def request(self, method, path, **_):
                if path.endswith("/process/status"):
                    return scenarios.Response(200, "application/json", b'{"status": "failed"}')
                record = {"id": "f1", "data": {"error": ReceiptTests.UNSAFE}}
                return scenarios.Response(200, "application/json", json.dumps(record).encode())

        ctx = scenarios.Context(target="acceptance", webui=Webui(), lemond=Webui(), token="t",
                                settings=scenarios.settings_from_environ(candidate_env()), chat_model="chat")
        with self.assertRaises(scenarios.ScenarioFailure) as raised:
            scenarios._wait_for_file(ctx, "f1")
        self.assertIn("status failed: cannot read <path>", str(raised.exception))
        self.assert_redacted(str(raised.exception))


    TOKEN, SESSION = "eyJhbGciOiJIUzI1NiJ9.tok3n-value", "s3ssion-value-42"

    def test_credentials_in_an_http_error_never_reach_the_receipt(self):
        # The Greptile reproduction: an upstream 502 whose body echoes the
        # request's Authorization and Cookie headers.
        body = (f"Bad Gateway\nAuthorization: Bearer {self.TOKEN}\nCookie: session={self.SESSION}; theme=dark\n"
                "Via: proxy").encode()
        endpoint = scenarios.Endpoint(origin="http://127.0.0.1:9")

        def failing(_ctx):
            with mock.patch.object(endpoint, "request", return_value=scenarios.Response(502, "text/plain", body)):
                endpoint.json("GET", "/api/v1/retrieval/health")
            return {}

        with mock.patch.object(scenarios, "SCENARIOS", {"open-webui.resmoke.zerank-qualification": failing}):
            result = scenarios.run_scenario(object(), "open-webui.resmoke.zerank-qualification")
        self.assertEqual(result.result, scenarios.FAIL)
        self.assertIn("HTTP 502", result.detail)
        receipt = scenarios.build_receipt(target="production", mode="record",
                                          settings=scenarios.settings_from_environ(candidate_env()),
                                          chat_model="chat", health=None, results=[result])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            scenarios.write_receipt(path, receipt)
            written = path.read_text(encoding="utf-8")
        for secret in (self.TOKEN, self.SESSION, "tok3n", "s3ssion"):
            self.assertNotIn(secret, written)
        self.assertIn("<redacted credential>", written)

    def test_every_credential_form_is_redacted_value_included(self):
        secret = "V4LUE-9f8e7d"
        forms = (
            f"Authorization: Basic {secret}",
            f"proxy-authorization: Digest username=x, response={secret}",
            f"Cookie: a=1; sid={secret}",
            f"Set-Cookie: sid={secret}; Path=/; HttpOnly",
            f"X-Api-Key: {secret}",
            f"x-goog-api-key: {secret}",
            f"X-Auth-Token: {secret}",
            f'{{"headers": {{"Authorization": "Bearer {secret}", "Accept": "*/*"}}}}',
            f"{{'cookie': 'session={secret}'}}",
            f"request failed with token {secret}",
            f"password = {secret} and more",
            f"api_key={secret}",
            f"-----BEGIN PRIVATE KEY-----\n{secret}\n-----END PRIVATE KEY-----",
        )
        for form in forms:
            with self.subTest(form=form):
                detail = scenarios.public_detail(f"upstream error: {form}", scenarios.RESULT_DETAIL_LIMIT)
                self.assertNotIn(secret, detail)
                self.assertTrue(detail.startswith("upstream error:"))
                scenarios.v1.assert_public_safe({"detail": detail})
        # Ordinary text is untouched.
        for plain in ("Model not found", "the key brass opens the seed cabinet", "HTTP 400: taken"):
            self.assertEqual(scenarios.public_detail(plain), plain)

    def test_the_safety_check_still_refuses_raw_credential_text(self):
        # public_detail never weakens the receipt's own check.
        for raw in (f"Authorization: Bearer {self.TOKEN}", f"cookie: session={self.SESSION}", "token=abc"):
            with self.assertRaises(ValueError):
                scenarios.v1.assert_public_safe({"detail": raw})


class FailureValuesTests(unittest.TestCase):
    """A failed scenario keeps what it measured, JSON-safe and redacted."""

    def run_one(self, error, scenario_id="open-webui.resmoke.cited-answer"):
        def failing(_ctx):
            raise error

        with mock.patch.object(scenarios, "SCENARIOS", {scenario_id: failing}):
            return scenarios.run_scenario(object(), scenario_id)

    def test_the_failure_message_stays_backward_compatible(self):
        self.assertEqual(scenarios.ScenarioFailure("no").values, {})
        self.assertEqual(str(scenarios.ScenarioFailure("no", {"a": 1})), "no")
        self.assertEqual(scenarios.ScenarioFailure("no", {"a": 1}).values, {"a": 1})

    def test_a_failed_scenario_records_its_values(self):
        values = {"timings": {"upload_s": 0.5, "chat_s": 2.0}, "sources": {"count": 0, "names": [], "scores": []},
                  "expected_source_name": scenarios.HANDBOOK_NAME, "fact_present": False}
        result = self.run_one(scenarios.ScenarioFailure(json.dumps(values, sort_keys=True), values))
        self.assertEqual(result.result, scenarios.FAIL)
        self.assertEqual(result.values, values)

    def test_failure_values_are_json_safe_and_public_safe(self):
        unsafe = {
            "detail": ReceiptTests.UNSAFE,
            "scores": [0.9, float("nan"), float("-inf")],
            "pair": ("Authorization: Bearer s3cret", 1),
            "margin": float("inf"),
        }
        result = self.run_one(scenarios.ScenarioFailure("measured", unsafe))
        self.assertEqual(result.result, scenarios.FAIL)
        text = json.dumps(result.values, allow_nan=False)
        for private in ("/home/someone", "192.168.1.20", "fd12:3456::7", "admin@example.org", "k1", "nas.lan",
                        "s3cret"):
            self.assertNotIn(private, text)
        self.assertEqual(result.values["scores"], [0.9, None, None])
        self.assertIsNone(result.values["margin"])
        receipt = scenarios.build_receipt(target="production", mode="record",
                                          settings=scenarios.settings_from_environ(candidate_env()),
                                          chat_model="chat", health=None, results=[result])
        json.dumps(receipt, allow_nan=False)
        self.assertEqual(receipt["scenarios"][0]["values"], result.values)

    def test_other_failures_and_blocks_record_no_values(self):
        for error, expected in ((KeyError("id"), scenarios.FAIL), (scenarios.Blocked("NEEDS OWNER: x"), scenarios.BLOCKED)):
            with self.subTest(error=error):
                result = self.run_one(error)
                self.assertEqual((result.result, result.values), (expected, {}))

    def test_an_escalation_keeps_its_values_unchanged(self):
        values = {"margin": 0.1, "vectors": {"query": {"dimensions": 2560, "norm": None}},
                  "texts": {"query": scenarios.CANARY_QUERY}}
        result = self.run_one(scenarios.Escalation("ESCALATE: zembed canary", values),
                              "open-webui.resmoke.zembed-canary")
        self.assertEqual((result.result, result.values, result.detail),
                         (scenarios.ESCALATE, values, "ESCALATE: zembed canary"))

    def test_zerank_keeps_its_scores_when_the_relevant_document_is_not_first(self):
        class Webui:
            def request(self, *_args, **_kwargs):
                return scenarios.Response(200, "application/json", b'{"status": "qualified"}')

        class Lemond:
            def json(self, *_args, **_kwargs):
                return {"results": [{"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.8}]}

        ctx = scenarios.Context(target="acceptance", webui=Webui(), lemond=Lemond(), token="t",
                                settings=scenarios.settings_from_environ(candidate_env()), chat_model="chat")
        with mock.patch.object(scenarios, "rag_gate_constants", return_value=("q", ("relevant", "other"))):
            result = scenarios.run_scenario(ctx, "open-webui.resmoke.zerank-qualification")
        self.assertEqual(result.result, scenarios.FAIL)
        self.assertIn("not ranked first", result.detail)
        self.assertEqual(result.values, {"health": "qualified", "scores": [0.1, 0.8]})

    def test_zerank_keeps_the_health_it_measured_on_every_failure(self):
        class Webui:
            def __init__(self, status):
                self.status = status

            def request(self, *_args, **_kwargs):
                return scenarios.Response(self.status, "application/json", b'{"status": "qualified"}')

        class Lemond:
            def json(self, *_args, **_kwargs):
                return {"results": [{"index": 0}]}

        settings = scenarios.settings_from_environ(candidate_env())
        with mock.patch.object(scenarios, "rag_gate_constants", return_value=("q", ("relevant", "other"))):
            unhealthy = scenarios.run_scenario(
                scenarios.Context(target="acceptance", webui=Webui(500), lemond=Lemond(), token="t",
                                  settings=settings, chat_model="chat"), "open-webui.resmoke.zerank-qualification")
            malformed = scenarios.run_scenario(
                scenarios.Context(target="acceptance", webui=Webui(200), lemond=Lemond(), token="t",
                                  settings=settings, chat_model="chat"), "open-webui.resmoke.zerank-qualification")
        self.assertEqual((unhealthy.result, unhealthy.values), (scenarios.FAIL, {"health_status": 500}))
        self.assertEqual((malformed.result, malformed.values), (scenarios.FAIL, {"health": "qualified"}))
        self.assertIn("one result per document", malformed.detail)


class ScenarioMeasurementTests(unittest.TestCase):
    """Every failure path keeps the timings and records a scenario took before it."""

    cited_context = CitedAnswerTests.cited_context

    def cited(self, ctx, wait=None):
        with mock.patch.object(scenarios, "_wait_for_file", side_effect=wait), \
                mock.patch.object(scenarios, "SCENARIOS", {"cited": scenarios.cited_answer}):
            return scenarios.run_scenario(ctx, "cited")

    def assert_receipt_safe(self, result):
        receipt = scenarios.build_receipt(target="production", mode="record",
                                          settings=scenarios.settings_from_environ(candidate_env()),
                                          chat_model="chat", health=None, results=[result])
        json.dumps(receipt, allow_nan=False)

    def test_failed_or_timed_out_processing_keeps_the_upload_timing(self):
        for message in ("file processing ended with HTTP 200 status failed: embedding failed",
                        "file processing did not complete in time"):
            with self.subTest(message):
                ctx, deletes = self.cited_context(200)
                result = self.cited(ctx, scenarios.ScenarioFailure(message))
                self.assertEqual((result.result, result.detail), (scenarios.FAIL, f"ScenarioFailure: {message}"))
                self.assertEqual(set(result.values["timings"]), {"upload_s"})
                self.assertEqual(result.values["expected_source_name"], scenarios.HANDBOOK_NAME)
                self.assertEqual(len(deletes), 1)
                self.assert_receipt_safe(result)

    def test_a_failed_chat_keeps_every_timing_and_still_cleans_up(self):
        ctx, deletes = self.cited_context(200, chat_status=502)
        result = self.cited(ctx)
        self.assertEqual(result.result, scenarios.FAIL)
        self.assertIn("HTTP 502", result.detail)
        self.assertEqual(set(result.values["timings"]), {"upload_s", "index_s", "chat_s"})
        self.assertEqual(len(deletes), 1)
        self.assert_receipt_safe(result)

    def test_a_chat_transport_error_keeps_the_timings_and_its_detail(self):
        ctx, deletes = self.cited_context(200)
        fixed = ctx.webui.request.side_effect

        def request(method, path, **kw):
            if (method, path) == ("POST", scenarios.API["chat"]):
                raise ConnectionResetError("connection reset by peer")
            return fixed(method, path, **kw)

        ctx.webui.request.side_effect = request
        result = self.cited(ctx)
        self.assertEqual((result.result, result.detail), (scenarios.FAIL, "ConnectionResetError: connection reset by peer"))
        self.assertEqual(set(result.values["timings"]), {"upload_s", "index_s"})
        self.assertEqual(len(deletes), 1)
        self.assert_receipt_safe(result)

    def test_a_failed_upload_keeps_its_timing(self):
        ctx, deletes = self.cited_context(200)
        ctx.webui.request.side_effect = lambda *_a, **_k: mock.Mock(status=500, body=b"", json=lambda: None)
        result = self.cited(ctx)
        self.assertEqual(result.result, scenarios.FAIL)
        self.assertIn("handbook upload returned HTTP 500", result.detail)
        self.assertEqual(set(result.values["timings"]), {"upload_s"})
        self.assertEqual(deletes, [])

    def test_a_failed_transcription_keeps_its_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "jfk.flac"
            audio.write_bytes(b"flac")
            webui = mock.Mock(request=mock.Mock(return_value=scenarios.Response(500, "text/plain", b"boom")))
            ctx = scenarios.Context(target="acceptance", webui=webui, lemond=mock.Mock(), token="t",
                                    settings=scenarios.settings_from_environ(candidate_env()), chat_model="chat",
                                    audio=audio)
            with mock.patch.object(scenarios.v1, "_file_sha256", return_value=scenarios.JFK_FLAC_SHA256):
                result = scenarios.run_scenario(ctx, "open-webui.resmoke.stt")
        self.assertEqual(result.result, scenarios.FAIL)
        self.assertIn("transcription returned HTTP 500", result.detail)
        self.assertEqual(set(result.values), {"transcription_s", "whisper"})
        self.assert_receipt_safe(result)

    def test_a_failed_stored_chunk_read_keeps_the_canary_margin(self):
        canary = ZembedCanaryTests()

        def unreadable():
            raise OSError("qdrant unreachable")

        outcome = canary.run_canary(stored_chunk=unreadable)
        self.assertEqual((outcome.result, outcome.detail), (scenarios.FAIL, "OSError: qdrant unreachable"))
        self.assertEqual(outcome.values["margin"], 0.9)
        self.assertEqual(sorted(outcome.values["vectors"]), ["query", "relevant", "unrelated"])
        self.assert_receipt_safe(outcome)

    def test_a_failed_initial_embedding_keeps_the_vectors_before_it(self):
        canary = ZembedCanaryTests()
        cases = (
            # The relevant embedding's transport fails after the query's.
            ({scenarios.CANARY_RELEVANT: OSError("connection refused")}, "OSError: connection refused",
             ["query"]),
            # The unrelated embedding comes back malformed.
            ({scenarios.CANARY_UNRELATED: scenarios.ScenarioFailure("Lemonade embeddings returned malformed data")},
             "ScenarioFailure: Lemonade embeddings returned malformed data", ["query", "relevant"]),
        )
        for failures, detail, recorded in cases:
            with self.subTest(detail=detail):
                def embed(_ctx, text, failures=failures):
                    for canary_text, vector in ((scenarios.CANARY_QUERY, canary.QUERY),
                                                (scenarios.CANARY_RELEVANT, canary.RELEVANT),
                                                (scenarios.CANARY_UNRELATED, canary.UNRELATED)):
                        if text.endswith(canary_text):
                            if canary_text in failures:
                                raise failures[canary_text]
                            return vector
                    raise AssertionError(text)

                with mock.patch.object(scenarios, "lemond_embed", side_effect=embed):
                    outcome = scenarios.run_scenario(canary.context(), "open-webui.resmoke.zembed-canary")
                self.assertEqual((outcome.result, outcome.detail), (scenarios.FAIL, detail))
                self.assertEqual(sorted(outcome.values["vectors"]), recorded)
                self.assertEqual(outcome.values["vectors"]["query"]["dimensions"], 2560)
                self.assertEqual(outcome.values["dimensions"], 2560)
                self.assertNotIn("margin", outcome.values)
                self.assert_receipt_safe(outcome)


class CredentialFieldTests(unittest.TestCase):
    """A credential-named field never reaches a receipt, by name or by value."""

    SECRET = "s3cret-V4LUE"

    def test_credential_fields_are_renamed_and_their_values_redacted(self):
        cases = (
            {"api_key": self.SECRET},
            {"api_key": ""},
            {"outer": {"token": self.SECRET, "nested": [{"X-Api-Key": self.SECRET, "Password": None}]}},
            {"session": self.SECRET, "client_secret": self.SECRET, "authorization": f"Bearer {self.SECRET}"},
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    scenarios.v1.assert_public_safe(value)
                public = scenarios.public_values(value)
                scenarios.v1.assert_public_safe(public)
                text = json.dumps(public)
                self.assertNotIn(self.SECRET, text)
                self.assertIn("<redacted credential>", text)
        self.assertEqual(scenarios.public_values({"api_key": "s3cret"}),
                         {"redacted_credential_field": "<redacted credential>"})
        nested = scenarios.public_values({"outer": {"token": "a", "cookie": "b", "count": 2}})
        self.assertEqual(nested, {"outer": {"redacted_credential_field": "<redacted credential>",
                                            "redacted_credential_field_2": "<redacted credential>", "count": 2}})

    def test_ordinary_fields_are_kept(self):
        value = {"selected_token": "kept", "runtime_credentials": ["openai-api-key"], "token_count": 3,
                 "health_status": 200, "env_keys": ["HAYSTACK_TELEMETRY_ENABLED"],
                 "stub_requests_with_credential": 0, "nonempty_key_fields": []}
        self.assertEqual(scenarios.public_values(value), value)

    def test_plural_credential_fields_redact_every_element(self):
        cases = (
            ({"provider_api_keys": [self.SECRET]}, {"redacted_credential_field": ["<redacted credential>"]}),
            ({"OPENAI_API_KEYS": [self.SECRET, ""]},
             {"redacted_credential_field": ["<redacted credential>", "<redacted credential>"]}),
            ({"api_keys": []}, {"redacted_credential_field": []}),
            ({"tokens": [self.SECRET]}, {"redacted_credential_field": ["<redacted credential>"]}),
            ({"passwords": (self.SECRET,)}, {"redacted_credential_field": ["<redacted credential>"]}),
            ({"secrets": {"a": self.SECRET}}, {"redacted_credential_field": "<redacted credential>"}),
            ({"keys": [self.SECRET]}, {"redacted_credential_field": ["<redacted credential>"]}),
            ({"outer": [{"session_tokens": [self.SECRET]}]},
             {"outer": [{"redacted_credential_field": ["<redacted credential>"]}]}),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                public = scenarios.public_values(value)
                self.assertEqual(public, expected)
                scenarios.v1.assert_public_safe(public)
                self.assertNotIn(self.SECRET, json.dumps(public))

    def test_common_credential_names_are_redacted(self):
        for name in ("aws_access_key_id", "aws_secret_access_key", "docker_auth_config", "ssh_auth_sock",
                     "credentials", "aws_credentials", "credential", "CLIENT-SECRET"):
            with self.subTest(name=name):
                public = scenarios.public_values({name: self.SECRET})
                self.assertEqual(public, {"redacted_credential_field": "<redacted credential>"})
                scenarios.v1.assert_public_safe(public)

    def test_a_failure_carrying_a_credential_field_still_writes_a_receipt(self):
        def failing(_ctx):
            raise scenarios.ScenarioFailure("measured", {"api_key": self.SECRET, "timings": {"upload_s": 0.5}})

        with mock.patch.object(scenarios, "SCENARIOS", {"x": failing}):
            result = scenarios.run_scenario(object(), "x")
        receipt = scenarios.build_receipt(target="production", mode="record",
                                          settings=scenarios.settings_from_environ(candidate_env()),
                                          chat_model="chat", health=None, results=[result])
        self.assertNotIn(self.SECRET, json.dumps(receipt))
        self.assertEqual(result.values["timings"], {"upload_s": 0.5})


class KitBackstopTests(unittest.TestCase):
    """The kit's receipt and evidence backstop: v1's check, then the widened credential rules."""

    SECRET = "s3cret-V4LUE"
    CREDENTIAL_NAMES = (
        "provider_api_keys", "api_keys", "OPENAI_API_KEYS", "apikeys", "tokens", "session_tokens", "passwords",
        "secrets", "cookies", "keys", "secret_keys", "private_keys", "access_keys", "aws_access_key_id",
        "aws_secret_access_key", "docker_auth_config", "ssh_auth_sock", "credentials", "aws_credentials",
        "credential", "session", "session_id", "sid", "passwd", "client_secret", "proxy_authorization",
    )
    EXEMPT = {"env_keys": ["HAYSTACK_TELEMETRY_ENABLED"], "stub_requests_with_credential": 0,
              "runtime_credentials": ["openai-api-key"], "selected_token": 3, "token_count": 512,
              "nonempty_key_fields": [], "credential_route": "systemd-creds",
              "redacted_credential_field": ["<redacted credential>"]}

    def test_each_plural_and_compound_credential_field_is_rejected(self):
        for name in self.CREDENTIAL_NAMES:
            for value in ({name: [self.SECRET]}, {name: ""}, {"outer": [{name: {"a": self.SECRET}}]}):
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, "secret-valued field"):
                    scenarios.assert_kit_public_safe(value)

    def test_plural_secret_assignments_in_text_are_rejected_and_redacted(self):
        for text in (f"tokens={self.SECRET}", f"api_keys: {self.SECRET}", f"passwords = {self.SECRET}",
                     f"secrets:{self.SECRET}", f"api-keys={self.SECRET}"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "secret-like material"):
                    scenarios.assert_kit_public_safe({"detail": text})
                detail = scenarios.public_detail(f"upstream error: {text}", scenarios.RESULT_DETAIL_LIMIT)
                self.assertNotIn(self.SECRET, detail)
                scenarios.assert_kit_public_safe({"detail": detail})

    def test_v1_findings_still_fail_first(self):
        for value in ({"api_key": "x"}, {"detail": "token=abc"}, {"path": "/home/someone/x"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scenarios.assert_kit_public_safe(value)

    def test_the_exemptions_and_ordinary_text_pass(self):
        scenarios.assert_kit_public_safe(self.EXEMPT)
        scenarios.assert_kit_public_safe({"detail": "the tokens are counted; 3 secrets of the garden", "count": 2})
        self.assertEqual(scenarios.public_values(self.EXEMPT), self.EXEMPT)

    def test_redacted_failure_values_always_pass_the_backstop(self):
        for name in self.CREDENTIAL_NAMES:
            with self.subTest(name=name):
                scenarios.assert_kit_public_safe(scenarios.public_values({name: [self.SECRET], "outer": {name: "x"}}))

    def test_receipts_use_the_backstop(self):
        result = scenarios.ScenarioResult("open-webui.resmoke.cited-answer", scenarios.FAIL, "measured", 0.1,
                                          {"provider_api_keys": [self.SECRET]})
        with self.assertRaisesRegex(ValueError, "secret-valued field"):
            scenarios.build_receipt(target="production", mode="record",
                                    settings=scenarios.settings_from_environ(candidate_env()), chat_model="chat",
                                    health=None, results=[result])
        with tempfile.TemporaryDirectory() as directory, \
                self.assertRaisesRegex(ValueError, "secret-valued field"):
            scenarios.write_receipt(Path(directory) / "receipt.json", {"tokens": [self.SECRET]})


class StubProviderTests(unittest.TestCase):
    def test_stub_embeddings_honor_the_zembed_heads(self):
        def embed(head, text):
            response = stub.embeddings({"model": stub.EMBEDDING_MODEL, "input": [head + text]})
            return response["data"][0]["embedding"]

        query = embed(stub.QUERY_HEAD, scenarios.CANARY_QUERY)
        relevant = embed(stub.DOCUMENT_HEAD, scenarios.CANARY_RELEVANT)
        unrelated = embed(stub.DOCUMENT_HEAD, scenarios.CANARY_UNRELATED)
        self.assertEqual(len(query), 2560)
        self.assertTrue(scenarios.v1.embedding_canary_passes(query, relevant, unrelated))
        self.assertEqual(stub.QUERY_HEAD, scenarios.ZEMBED_QUERY_HEAD)
        self.assertEqual(stub.DOCUMENT_HEAD, scenarios.ZEMBED_DOCUMENT_HEAD)
        self.assertEqual(candidate_env()["RAG_EMBEDDING_QUERY_PREFIX"], scenarios.ZEMBED_QUERY_HEAD)
        self.assertEqual(candidate_env()["RAG_EMBEDDING_CONTENT_PREFIX"], scenarios.ZEMBED_DOCUMENT_HEAD)

    def test_stub_rerank_qualifies_the_packaged_gate(self):
        query, documents = scenarios.rag_gate_constants()
        response = stub.rerank({"model": stub.RERANKING_MODEL, "query": query, "documents": list(documents)})
        scores = scenarios.validate_rerank_results(response["results"], len(documents))
        self.assertGreater(scores[0], scores[1])

    def test_stub_chat_quotes_the_retrieved_sentence(self):
        handbook = scenarios.handbook_bytes().decode()
        request = {
            "model": stub.CHAT_MODEL,
            "messages": [
                {"role": "system", "content": f"<context><source id=\"1\">{handbook}</source></context>"},
                {"role": "user", "content": scenarios.CITED_ANSWER_PROMPT},
            ],
        }
        self.assertEqual(stub.chat_answer(request), scenarios.CANONICAL_FACT)
        events = "".join(stub.chat_events(request)).encode()
        text, _ = scenarios.parse_chat_response(events, "text/event-stream")
        self.assertEqual(text, scenarios.CANONICAL_FACT)

    def test_stub_calls_the_named_tool_and_answers_from_its_result(self):
        prompt = ('Call view_knowledge_file with file_id "f1" and repeat its sentence about the seed cabinet '
                  "word for word. If the tool returns an error, reply with that error only.")
        tools = [{"type": "function", "function": {"name": name, "parameters": {}}}
                 for name in ("list_knowledge_bases", "view_knowledge_file")]
        request = {"model": stub.CHAT_MODEL, "tools": tools, "messages": [{"role": "user", "content": prompt}]}
        call = {"id": stub.TOOL_CALL_ID, "type": "function",
                "function": {"name": "view_knowledge_file", "arguments": '{"file_id":"f1"}'}}
        completion = stub.chat_completion(request)["choices"][0]
        self.assertEqual(completion["finish_reason"], "tool_calls")
        self.assertEqual(completion["message"]["tool_calls"], [call])
        events = [json.loads(line[len("data: "):]) for line in "".join(stub.chat_events(request)).splitlines()
                  if line.startswith("data: {")]
        self.assertEqual(events[0]["choices"][0]["delta"]["tool_calls"], [{"index": 0, **call}])
        self.assertEqual(events[-1]["choices"][0]["finish_reason"], "tool_calls")
        # A tool the request does not offer is never called.
        self.assertIsNone(stub.requested_tool_call({**request, "tools": tools[:1]}))
        self.assertIsNone(stub.requested_tool_call({**request, "messages": [{"role": "user", "content": "Hi."}]}))

        def answer(result):
            follow_up = {**request, "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "", "tool_calls": [call]},
                {"role": "tool", "tool_call_id": stub.TOOL_CALL_ID, "content": result},
            ]}
            self.assertIsNone(stub.requested_tool_call(follow_up))
            return stub.chat_answer(follow_up)

        error = "Document retrieval is temporarily unavailable while its inference provider is unhealthy."
        self.assertEqual(answer(json.dumps({"error": error, "status": 503})), error)
        handbook = scenarios.handbook_bytes().decode()
        self.assertEqual(answer(json.dumps({"id": "f1", "content": handbook})), scenarios.CANONICAL_FACT)

    def test_stub_refuses_messages_that_hold_no_object(self):
        # A message array of non-objects is a malformed request (HTTP 400),
        # never an IndexError inside the stub.
        request = {"model": stub.CHAT_MODEL, "messages": ["Call view_file", 3, None],
                   "tools": [{"type": "function", "function": {"name": "view_file"}}]}
        for answer in (stub.requested_tool_call, stub.chat_answer, stub.chat_completion):
            with self.subTest(answer.__name__), self.assertRaisesRegex(stub.StubError, "message object"):
                answer(request)

    def test_stub_parsing_stays_linear_on_hostile_prompts(self):
        self.assertEqual(stub._between("a<context>x</context>", "<context>", "</context>"), "x")
        self.assertIsNone(stub._between("a<context>x", "<context>", "</context>"))
        for content in (
            "<context>" + "<" * 40_000 + "</context>",
            "<context>" * 20_000,
            "<user_query>" * 20_000,
            "Call view_file with file_id " + '"' * 40_000,
            "Call " * 20_000,
        ):
            hostile = {"model": stub.CHAT_MODEL, "messages": [{"role": "user", "content": content}],
                       "tools": [{"type": "function", "function": {"name": "view_file"}}]}
            started = time.monotonic()
            self.assertIsInstance(stub.chat_answer(hostile), str)
            stub.requested_tool_call(hostile)
            # The backtracking patterns this replaced took over a second here.
            self.assertLess(time.monotonic() - started, 0.5)

    def test_https_endpoints_refuse_tls_older_than_1_2(self):
        import ssl

        self.assertEqual(scenarios.tls_context().minimum_version, ssl.TLSVersion.TLSv1_2)
        endpoint = scenarios.Endpoint(origin="https://example.invalid")
        self.assertIsNotNone(endpoint.context)
        assert endpoint.context is not None
        self.assertEqual(endpoint.context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_the_stub_logs_whether_a_credential_was_sent_never_its_value(self):
        for header, sent in ((None, False), ("", False), ("Bearer", False), ("Bearer ", False),
                             ("Bearer    ", False), ("bearer x", True), ("Bearer tok", True), ("Basic dXNlcg==", True)):
            with self.subTest(header=header):
                self.assertEqual(stub.credential_sent(header), sent)

    def test_stub_serves_the_lemonade_routes_without_a_key(self):
        with running_stub() as url:
            lemond = scenarios.Endpoint(origin=url)
            health, models = scenarios.lemond_snapshot(lemond)
            scenarios.require_models_ready(
                models, health, (stub.EMBEDDING_MODEL, stub.RERANKING_MODEL, stub.CHAT_MODEL)
            )
            settings = scenarios.settings_from_environ(candidate_env())
            ctx = scenarios.Context(
                target="acceptance", webui=lemond, lemond=lemond, token="", settings=settings, chat_model=stub.CHAT_MODEL
            )
            values = scenarios.zembed_canary(ctx)
            self.assertEqual(values["dimensions"], 2560)
            self.assertEqual({record["dimensions"] for record in values["vectors"].values()}, {2560})
            self.assertEqual(values["stored_vector_cosine"], "not-applicable")
            self.assertEqual(lemond.request("POST", "/api/v1/load", payload={}).status, 404)


if __name__ == "__main__":
    unittest.main()
