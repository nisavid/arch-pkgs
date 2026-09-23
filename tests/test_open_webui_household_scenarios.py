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
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = REPO_ROOT / "tools" / "open_webui_household_scenarios.py"
STUB = REPO_ROOT / "tools" / "fixtures" / "open-webui-household-acceptance" / "stub_provider.py"
PACKAGED_ENV = REPO_ROOT / "packages" / "open-webui" / "open-webui.env"
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
    return scenarios.parse_env_file(PACKAGED_ENV.read_text(encoding="utf-8"))


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
        stack.enter_context(mock.patch.object(scenarios, "read_process_environ", return_value=packaged_env()))
        return stack

    def test_an_unreachable_lemonade_is_a_precondition_with_a_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, self.acceptance_process(), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = scenarios.main(self.resmoke_args(tmp, "--lemond-url", "http://127.0.0.1:9"))
            receipt = json.loads(Path(f"{tmp}/r.json").read_text())
        self.assertEqual(code, 75)
        self.assertEqual(receipt["exit_code"], 75)
        self.assertIn("Lemonade is unreachable", receipt["precondition"])

    def test_an_unreachable_open_webui_is_a_precondition_with_a_receipt(self):
        env = packaged_env()
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
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
            code = scenarios.main(
                ["resmoke", "--target", "acceptance", "--chat-model", "m", "--receipt", f"{tmp}/r.json"]
            )
        self.assertEqual(code, 75)


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
        settings = scenarios.settings_from_environ(packaged_env())
        self.assertEqual(settings.embedding_model, packaged_env()["RAG_EMBEDDING_MODEL"])
        self.assertEqual(settings.reranking_model, packaged_env()["RAG_RERANKING_MODEL"])
        self.assertTrue(settings.reranking_model.startswith("zerank-2-"))
        with self.assertRaises(scenarios.Blocked):
            scenarios.settings_from_environ({"RAG_EMBEDDING_MODEL": "zembed"})
        with self.assertRaises(scenarios.Blocked):
            scenarios.confirm_model_ids(settings, "user.zembed-1-Q4_K_M-GGUF-Q4_K_M", None)
        scenarios.confirm_model_ids(settings, settings.embedding_model, None)

    def test_frozen_production_settings_come_only_from_committed_acceptance_evidence(self):
        evidence = REPO_ROOT / "docs" / "maintainers" / "evidence"
        of_record = set()
        for path in sorted(evidence.glob("open-webui-household-acceptance-*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            for step in document.get("steps", []):
                if step.get("id") == "open-webui.acceptance.identity.archives":
                    for item in (step.get("values") or {}).get("archives", []):
                        of_record.add((item["name"], item["sha256"]))
        for version, expected in scenarios.PRODUCTION_EXPECTATIONS.items():
            self.assertIn((expected["archive"], expected["archive_sha256"]), of_record, version)
            self.assertEqual(set(expected), {"archive", "archive_sha256", *scenarios.PRODUCTION_EXPECTATION_KEYS})
        with self.assertRaises(scenarios.Blocked):
            scenarios.settings_for_production("0.11.0-3")

    def test_the_trial_derives_the_production_entry_from_the_deployed_archive(self):
        env = packaged_env()
        derived = scenarios.production_expectation("open-webui-0.11.0-5-x86_64.pkg.tar.zst", "a" * 64, env)
        self.assertEqual(derived["version"], "0.11.0-5")
        self.assertEqual(derived["entry"]["archive_sha256"], "a" * 64)
        for key in scenarios.PRODUCTION_EXPECTATION_KEYS:
            self.assertEqual(derived["entry"][key], env[key])
        with self.assertRaises(ValueError):
            scenarios.production_expectation("qdrant-1.19.0-1-x86_64.pkg.tar.zst", "a" * 64, env)

    def test_production_settings_claim_the_digest_only_when_the_cached_archive_matched(self):
        env = packaged_env()
        with tempfile.TemporaryDirectory() as cache:
            name = "open-webui-0.11.0-5-x86_64.pkg.tar.zst"
            (Path(cache) / name).write_bytes(b"exact")
            digest = scenarios.v1._sha256_bytes(b"exact")
            entry = scenarios.production_expectation(name, digest, env)["entry"]
            with mock.patch.object(scenarios, "PRODUCTION_EXPECTATIONS", {"0.11.0-5": entry}):
                verified = scenarios.settings_for_production("0.11.0-5", Path(cache))
                unverified = scenarios.settings_for_production("0.11.0-5", Path(cache) / "absent")
                (Path(cache) / name).write_bytes(b"other")
                with self.assertRaises(scenarios.Blocked):
                    scenarios.settings_for_production("0.11.0-5", Path(cache))
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

    def test_connection_seed_is_exactly_the_three_keyless_keys(self):
        seed = scenarios.connection_seed()
        self.assertEqual(set(seed), {"ENABLE_OLLAMA_API", "OPENAI_API_BASE_URLS", "OPENAI_API_KEYS"})
        self.assertEqual(set(seed), scenarios.CONNECTION_SEED_KEYS)
        self.assertEqual(seed["ENABLE_OLLAMA_API"], "false")
        self.assertEqual(seed["OPENAI_API_BASE_URLS"], "http://127.0.0.1:13305/api/v1")
        self.assertEqual(seed["OPENAI_API_KEYS"], "")
        self.assertEqual(scenarios.speech_environment(), {"WHISPER_MODEL": "tiny", "HF_HUB_OFFLINE": "1"})
        env = packaged_env()
        self.assertEqual({key: env[key] for key in scenarios.CONNECTION_SEED_KEYS}, seed)


class OverlayTests(unittest.TestCase):
    def test_overlay_keys_equal_the_allowlist(self):
        env = packaged_env()
        root = Path("/srv/build/arch-pkgs-owui-acceptance")
        overlay = scenarios.acceptance_overlay(env, root)
        self.assertEqual(
            set(overlay), scenarios.overlay_allowlist(env, rehearsal=False) - scenarios.CONNECTION_SEED_KEYS
        )
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

    def test_rehearsal_overlay_points_every_provider_url_at_the_stub(self):
        env = packaged_env()
        overlay = scenarios.acceptance_overlay(
            env, Path("/r"), lemond_url="http://127.0.0.1:23305", relay_port=13306, rehearsal=True
        )
        self.assertEqual(
            set(overlay),
            scenarios.overlay_allowlist(env, rehearsal=True) - {"ENABLE_OLLAMA_API", "OPENAI_API_KEYS"},
        )
        self.assertEqual(overlay["RAG_OPENAI_API_BASE_URL"], "http://127.0.0.1:23305/api/v1")
        self.assertEqual(overlay["OPENAI_API_BASE_URLS"], "http://127.0.0.1:23305/api/v1")

    def test_overlay_adds_the_whole_seed_for_a_package_without_it(self):
        env = {key: value for key, value in packaged_env().items() if key not in scenarios.CONNECTION_SEED_KEYS}
        overlay = scenarios.acceptance_overlay(env, Path("/r"))
        self.assertEqual({key: overlay[key] for key in scenarios.CONNECTION_SEED_KEYS}, scenarios.connection_seed())

    def test_overlay_never_touches_secret_or_telemetry_keys(self):
        allowed = scenarios.overlay_allowlist(packaged_env(), rehearsal=True)
        for key in ("WEBUI_SECRET_KEY", "REDIS_URL", "QDRANT_API_KEY", "DO_NOT_TRACK", "OFFLINE_MODE", "ENABLE_SIGNUP"):
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

    def test_ported_pins_carry_their_source(self):
        source = SCENARIOS.read_text(encoding="utf-8")
        self.assertIn("e12fdd98251a01cdc99f22a5a113741b2473b107", source)
        self.assertEqual(scenarios.WHISPER_TINY["revision"], "d90ca5fe260221311c53c58e660288d3deb8d356")
        self.assertRegex(scenarios.JFK_FLAC_SHA256, r"^[0-9a-f]{64}$")


class ReceiptTests(unittest.TestCase):
    def test_receipt_is_public_safe_and_carries_the_exit_code(self):
        settings = scenarios.settings_from_environ(packaged_env())
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
        self.assertEqual(packaged_env()["RAG_EMBEDDING_QUERY_PREFIX"], scenarios.ZEMBED_QUERY_HEAD)
        self.assertEqual(packaged_env()["RAG_EMBEDDING_CONTENT_PREFIX"], scenarios.ZEMBED_DOCUMENT_HEAD)

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

    def test_stub_serves_the_lemonade_routes_without_a_key(self):
        with running_stub() as url:
            lemond = scenarios.Endpoint(origin=url)
            health, models = scenarios.lemond_snapshot(lemond)
            scenarios.require_models_ready(
                models, health, (stub.EMBEDDING_MODEL, stub.RERANKING_MODEL, stub.CHAT_MODEL)
            )
            settings = scenarios.settings_from_environ(packaged_env())
            ctx = scenarios.Context(
                target="acceptance", webui=lemond, lemond=lemond, token="", settings=settings, chat_model=stub.CHAT_MODEL
            )
            values = scenarios.zembed_canary(ctx)
            self.assertEqual(values["dimensions"], 2560)
            self.assertEqual(values["stored_vector_cosine"], "not-applicable")
            self.assertEqual(lemond.request("POST", "/api/v1/load", payload={}).status, 404)


if __name__ == "__main__":
    unittest.main()
