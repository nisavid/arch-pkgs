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
# copies of the 0.11.4-1 package files; the kit tests pin their digests).
CANDIDATE = REPO_ROOT / "tools" / "fixtures" / "open-webui-household-acceptance" / "open-webui-0.11.4-1"
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
        derived = scenarios.production_expectation("open-webui-0.11.4-1-x86_64.pkg.tar.zst", "a" * 64, env)
        self.assertEqual(derived["version"], "0.11.4-1")
        self.assertEqual(derived["entry"]["archive_sha256"], "a" * 64)
        for key in scenarios.PRODUCTION_EXPECTATION_KEYS:
            self.assertEqual(derived["entry"][key], env[key])
        with self.assertRaises(ValueError):
            scenarios.production_expectation("qdrant-1.19.1-1-x86_64.pkg.tar.zst", "a" * 64, env)

    def test_production_settings_claim_the_digest_only_when_the_cached_archive_matched(self):
        env = candidate_env()
        with tempfile.TemporaryDirectory() as cache:
            name = "open-webui-0.11.4-1-x86_64.pkg.tar.zst"
            (Path(cache) / name).write_bytes(b"exact")
            digest = scenarios.v1._sha256_bytes(b"exact")
            entry = scenarios.production_expectation(name, digest, env)["entry"]
            with mock.patch.object(scenarios, "PRODUCTION_EXPECTATIONS", {"0.11.4-1": entry}):
                verified = scenarios.settings_for_production("0.11.4-1", Path(cache))
                unverified = scenarios.settings_for_production("0.11.4-1", Path(cache) / "absent")
                (Path(cache) / name).write_bytes(b"other")
                with self.assertRaises(scenarios.Blocked):
                    scenarios.settings_for_production("0.11.4-1", Path(cache))
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

    def test_configure_sets_the_listed_chat_id_as_the_default(self):
        bare = scenarios.bare_model_id(scenarios.DEFAULT_CHAT_MODEL)
        posted = {}

        class FakeWebui:
            def json(self, method, path, payload=None, token=None):
                if method == "POST":
                    posted[path] = payload
                    return {}
                return {"data": [{"id": bare}]} if path == scenarios.API["models"] else {}

        summary = scenarios.configure(FakeWebui(), "t", chat_model=scenarios.DEFAULT_CHAT_MODEL)
        self.assertEqual(posted[scenarios.API["models_config"]]["DEFAULT_MODELS"], bare)
        self.assertEqual(summary["chat_model"], bare)
        self.assertEqual(summary["designated_chat_model"], scenarios.DEFAULT_CHAT_MODEL)
        self.assertEqual(summary["whisper_model"], "base")

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
            self.assertEqual(values["stored_vector_cosine"], "not-applicable")
            self.assertEqual(lemond.request("POST", "/api/v1/load", payload={}).status, 404)


if __name__ == "__main__":
    unittest.main()
