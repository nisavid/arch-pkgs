import ast
import asyncio
import builtins
import importlib.util
import math
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest import mock

from tests.open_webui_household_source_fixture import (
    materialize_exact_open_webui_source,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "packages" / "open-webui"
RAG_GATE = PACKAGE_DIR / "open-webui-rag-gate.py"
RAG_PATCH = PACKAGE_DIR / "0005-require-qualified-reranking.patch"
EXTERNAL_RERANKER_PREIMAGE = (
    REPO_ROOT
    / "tools"
    / "fixtures"
    / "open-webui-household"
    / "open-webui-0.11.0-pristine-external-reranker.py"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OpenWebUIHouseholdRAGGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_temporary, cls.upstream_source = (
            materialize_exact_open_webui_source()
        )

    @classmethod
    def tearDownClass(cls):
        cls.source_temporary.cleanup()

    def setUp(self):
        self.gate = load_module("household_rag_gate", RAG_GATE)

    def test_required_gate_starts_closed_and_only_semantic_qualification_reopens(self):
        self.gate.configure_required_reranker(True)

        with self.assertRaises(self.gate.RAGUnavailableError) as missing:
            self.gate.require_required_reranker(None)
        self.assertEqual(missing.exception.status_code, 503)
        self.assertEqual(str(missing.exception), self.gate.RAG_UNAVAILABLE_DETAIL)

        marker = object()
        self.gate.qualify_required_reranker([0.91, 0.08])
        self.gate.require_required_reranker(marker)

    def test_package_required_reranker_cannot_be_reconfigured_as_optional(self):
        marker = object()
        self.gate.configure_required_reranker(True)
        self.gate.qualify_required_reranker([0.91, 0.08])
        self.gate.require_required_reranker(marker)

        self.gate.configure_required_reranker(False)
        with self.assertRaises(self.gate.RAGUnavailableError):
            self.gate.require_required_reranker(marker)

        # The closed RAG boundary still does not participate in ordinary chat.
        self.gate.require_file_rag_ready([], None)

        self.gate.close_required_reranker()
        with self.assertRaises(self.gate.RAGUnavailableError):
            self.gate.require_required_reranker(marker)

        # Reconfiguration is not a readiness shortcut.
        self.gate.configure_required_reranker(True)
        with self.assertRaises(self.gate.RAGUnavailableError):
            self.gate.require_required_reranker(marker)

        for invalid in ([0.1, 0.9], [0.1], [math.nan, 0.1]):
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(self.gate.RAGUnavailableError),
            ):
                self.gate.qualify_required_reranker(invalid)

        self.gate.qualify_required_reranker([0.91, 0.08])
        self.gate.require_required_reranker(marker)

    def test_required_closed_rag_does_not_block_no_file_chat_but_refuses_file_bypasses(
        self,
    ):
        self.gate.configure_required_reranker(True)

        # The handler policy returns before consulting RAG for an ordinary chat.
        self.gate.require_file_rag_ready([], None)

        with self.assertRaises(self.gate.RAGUnavailableError):
            self.gate.require_file_rag_ready([{"type": "file"}], object())

        reranker = object()
        self.gate.qualify_required_reranker([0.91, 0.08])
        self.gate.require_file_rag_ready([{"type": "file"}], reranker)

        # Qualification cannot turn an explicit no-rerank mode into a safe path.
        unsafe_modes = (
            {"full_context": True},
            {"hybrid_search": False},
            {"bypass_embedding_and_retrieval": True},
        )
        for mode in unsafe_modes:
            with (
                self.subTest(mode=mode),
                self.assertRaises(self.gate.RAGUnavailableError),
            ):
                self.gate.require_file_rag_ready(
                    [{"type": "file"}],
                    reranker,
                    **mode,
                )

    def test_external_results_require_exact_indices_cardinality_and_finite_scores(self):
        self.assertEqual(
            self.gate.validate_external_rerank_results(
                [
                    {"index": 1, "relevance_score": 0.2},
                    {"index": 0, "relevance_score": 0.8},
                ],
                2,
            ),
            [0.8, 0.2],
        )

        invalid_results = (
            [{"index": 0, "relevance_score": 0.8}],
            [
                {"index": 0, "relevance_score": 0.8},
                {"index": 0, "relevance_score": 0.2},
            ],
            [
                {"index": 0, "relevance_score": 0.8},
                {"index": 2, "relevance_score": 0.2},
            ],
            [
                {"index": 0, "relevance_score": 0.8},
                {"index": 1, "relevance_score": math.inf},
            ],
            [
                {"index": True, "relevance_score": 0.8},
                {"index": 1, "relevance_score": 0.2},
            ],
        )
        for results in invalid_results:
            with (
                self.subTest(results=results),
                self.assertRaises(self.gate.RAGUnavailableError),
            ):
                self.gate.validate_external_rerank_results(results, 2)

    def test_chat_handler_refuses_required_rag_before_query_or_source_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            middleware_path = (
                source_root / "backend" / "open_webui" / "utils" / "middleware.py"
            )
            middleware_path.parent.mkdir(parents=True)
            shutil.copyfile(
                self.upstream_source / "backend/open_webui/utils/middleware.py",
                middleware_path,
            )
            applied = subprocess.run(
                [
                    "git",
                    "apply",
                    "--include=backend/open_webui/utils/middleware.py",
                    str(RAG_PATCH),
                ],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            parsed = ast.parse(middleware_path.read_text(encoding="utf-8"))
            handler_node = next(
                node
                for node in parsed.body
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name == "chat_completion_files_handler"
            )

            class FixtureConfig:
                values: ClassVar[dict] = {}

                @classmethod
                async def get_many(cls, *keys):
                    return {key: cls.values.get(key) for key in keys}

            namespace = {
                "Config": FixtureConfig,
                "RAGUnavailableError": self.gate.RAGUnavailableError,
                "Request": object,
                "UserModel": object,
                "require_file_rag_ready": self.gate.require_file_rag_ready,
            }
            exec(  # noqa: S102 - executes one extracted function from the exact bound source
                compile(
                    ast.fix_missing_locations(
                        ast.Module(body=[handler_node], type_ignores=[])
                    ),
                    str(middleware_path),
                    "exec",
                ),
                namespace,
            )
            handler = namespace["chat_completion_files_handler"]
            request = SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(
                        RERANKING_FUNCTION=lambda *_args, **_kwargs: []
                    )
                )
            )
            emitter = mock.AsyncMock()

            self.gate.configure_required_reranker(True)
            ordinary = asyncio.run(
                handler(
                    request,
                    {"metadata": {}, "messages": [], "model": "chat"},
                    {"__event_emitter__": emitter},
                    object(),
                )
            )
            self.assertEqual(ordinary[1], {"sources": []})

            generate_queries = mock.AsyncMock()
            source_lookup = mock.AsyncMock()
            namespace["generate_queries"] = generate_queries
            namespace["get_sources_from_items"] = source_lookup
            attached = {
                "metadata": {"files": [{"type": "file"}]},
                "messages": [{"role": "user", "content": "private query"}],
                "model": "chat",
            }

            modes = (
                {"closed": True},
                {"rag.enable_hybrid_search": False},
                {"rag.full_context": True},
                {"rag.bypass_embedding_and_retrieval": True},
            )
            for mode in modes:
                with self.subTest(mode=mode):
                    self.gate.configure_required_reranker(True)
                    if not mode.get("closed"):
                        self.gate.qualify_required_reranker([0.91, 0.08])
                    FixtureConfig.values = {
                        "rag.enable_hybrid_search": True,
                        "rag.full_context": False,
                        "rag.bypass_embedding_and_retrieval": False,
                        **{
                            key: value for key, value in mode.items() if key != "closed"
                        },
                    }
                    with self.assertRaises(self.gate.RAGUnavailableError):
                        asyncio.run(
                            handler(
                                request,
                                attached,
                                {"__event_emitter__": emitter},
                                object(),
                            )
                        )

            generate_queries.assert_not_awaited()
            source_lookup.assert_not_awaited()

    def test_failed_startup_qualification_keeps_chat_up_and_health_probe_503(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            router_path = (
                source_root / "backend" / "open_webui" / "routers" / "retrieval.py"
            )
            router_path.parent.mkdir(parents=True)
            shutil.copyfile(
                self.upstream_source / "backend/open_webui/routers/retrieval.py",
                router_path,
            )
            applied = subprocess.run(
                [
                    "git",
                    "apply",
                    "--include=backend/open_webui/routers/retrieval.py",
                    str(RAG_PATCH),
                ],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            parsed = ast.parse(router_path.read_text(encoding="utf-8"))
            health_node = next(
                node
                for node in parsed.body
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name == "get_rag_health"
            )
            health_node.decorator_list = []

            class FixtureHTTPException(Exception):
                def __init__(self, status_code, detail):
                    super().__init__(detail)
                    self.status_code = status_code
                    self.detail = detail

            namespace = {
                "Depends": lambda _dependency: None,
                "get_verified_user": object(),
                "HTTPException": FixtureHTTPException,
                "RAGUnavailableError": self.gate.RAGUnavailableError,
                "Request": object,
                "require_required_reranker": self.gate.require_required_reranker,
            }
            exec(  # noqa: S102 - executes one extracted function from the exact bound source
                compile(
                    ast.fix_missing_locations(
                        ast.Module(body=[health_node], type_ignores=[])
                    ),
                    str(router_path),
                    "exec",
                ),
                namespace,
            )
            health = namespace["get_rag_health"]
            request = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(RERANKING_FUNCTION=None))
            )

            self.gate.configure_required_reranker(True)
            with self.assertRaises(self.gate.RAGUnavailableError):
                self.gate.qualify_required_reranker([0.1, 0.9])

            # Startup is intentionally degraded, not failed: no-file chat stays outside RAG.
            self.gate.require_file_rag_ready([], None)
            with self.assertRaises(FixtureHTTPException) as unavailable:
                asyncio.run(health(request, object()))
            self.assertEqual(
                unavailable.exception.status_code, HTTPStatus.SERVICE_UNAVAILABLE
            )
            self.assertEqual(
                unavailable.exception.detail, self.gate.RAG_UNAVAILABLE_DETAIL
            )

            self.gate.qualify_required_reranker([0.91, 0.08])
            request.app.state.RERANKING_FUNCTION = object()
            self.assertEqual(
                asyncio.run(health(request, object())),
                {"status": "qualified"},
            )

    def test_builtin_chunk_queries_return_the_same_stable_rag_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            builtin_path = (
                source_root / "backend" / "open_webui" / "tools" / "builtin.py"
            )
            builtin_path.parent.mkdir(parents=True)
            shutil.copyfile(
                self.upstream_source / "backend/open_webui/tools/builtin.py",
                builtin_path,
            )
            applied = subprocess.run(
                [
                    "git",
                    "apply",
                    "--include=backend/open_webui/tools/builtin.py",
                    str(RAG_PATCH),
                ],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            parsed = ast.parse(builtin_path.read_text(encoding="utf-8"))
            function_nodes = [
                node
                for node in parsed.body
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name in {"query_chat_files", "query_knowledge_files"}
            ]
            namespace = {
                "json": __import__("json"),
                "log": mock.Mock(),
                "Optional": __import__("typing").Optional,
                "RAG_UNAVAILABLE_DETAIL": self.gate.RAG_UNAVAILABLE_DETAIL,
                "RAGUnavailableError": self.gate.RAGUnavailableError,
                "Request": object,
            }
            exec(  # noqa: S102 - executes two extracted functions from the exact bound source
                compile(
                    ast.fix_missing_locations(
                        ast.Module(body=function_nodes, type_ignores=[])
                    ),
                    str(builtin_path),
                    "exec",
                ),
                namespace,
            )

            request = SimpleNamespace()
            user = {"id": "fixture-user", "role": "user"}
            expected = {
                "error": self.gate.RAG_UNAVAILABLE_DETAIL,
                "status": HTTPStatus.SERVICE_UNAVAILABLE,
            }
            original_import = builtins.__import__

            for function_name, blocked_import, kwargs in (
                (
                    "query_chat_files",
                    "open_webui.retrieval.utils",
                    {"__files__": [{"type": "file", "id": "fixture-file"}]},
                ),
                (
                    "query_knowledge_files",
                    "open_webui.models.access_grants",
                    {},
                ),
            ):
                with self.subTest(function=function_name):

                    def guarded_import(
                        name, *args, _blocked_import=blocked_import, **import_kwargs
                    ):
                        if name == _blocked_import:
                            raise self.gate.RAGUnavailableError()
                        return original_import(name, *args, **import_kwargs)

                    with mock.patch("builtins.__import__", side_effect=guarded_import):
                        result = asyncio.run(
                            namespace[function_name](
                                "private query",
                                __request__=request,
                                __user__=user,
                                **kwargs,
                            )
                        )
                    self.assertEqual(__import__("json").loads(result), expected)

    def test_patch_is_bound_to_exact_source_and_covers_every_fail_open_path(self):
        patch = RAG_PATCH.read_text(encoding="utf-8")
        self.assertIn(
            "Open WebUI commit: f9590b8017199e56d5e953657e6498e3cef1d246", patch
        )
        self.assertIn(
            "Open WebUI 0.11.0 sdist SHA-256: "
            "e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9",
            patch,
        )

        for path in (
            "backend/open_webui/retrieval/models/external.py",
            "backend/open_webui/retrieval/utils.py",
            "backend/open_webui/utils/middleware.py",
            "backend/open_webui/tools/builtin.py",
            "backend/open_webui/routers/retrieval.py",
            "backend/open_webui/main.py",
        ):
            with self.subTest(path=path):
                self.assertIn(f"diff --git a/{path} b/{path}", patch)

        self.assertNotIn(
            "\n+            log.info(f'ExternalReranker:predict:query", patch
        )
        self.assertGreaterEqual(
            patch.count("except RAGUnavailableError:\n+            raise"), 3
        )
        self.assertIn("require_safe_retrieval_mode(", patch)
        self.assertIn("status_code=RAGUnavailableError.status_code", patch)
        self.assertIn("'status': RAGUnavailableError.status_code", patch)
        self.assertIn("@router.get('/health')", patch)
        self.assertIn("async def get_rag_health(", patch)
        middleware_patch = patch.split(
            "diff --git a/backend/open_webui/utils/middleware.py", 1
        )[1].split("diff --git", 1)[0]
        self.assertIn(
            "+        # Refuse unavailable or no-rerank modes before query generation.",
            middleware_patch,
        )

    def test_external_reranker_qualifies_then_latches_closed_on_runtime_fault(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            external_path = (
                source_root
                / "backend"
                / "open_webui"
                / "retrieval"
                / "models"
                / "external.py"
            )
            external_path.parent.mkdir(parents=True)
            shutil.copyfile(EXTERNAL_RERANKER_PREIMAGE, external_path)

            applied = subprocess.run(
                [
                    "git",
                    "apply",
                    "--include=backend/open_webui/retrieval/models/external.py",
                    str(RAG_PATCH),
                ],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            open_webui = types.ModuleType("open_webui")
            open_webui.__path__ = []
            env = types.ModuleType("open_webui.env")
            env.ENABLE_FORWARD_USER_INFO_HEADERS = False
            env.REQUESTS_VERIFY = True
            base = types.ModuleType("open_webui.retrieval.models.base_reranker")
            base.BaseReranker = object
            headers = types.ModuleType("open_webui.utils.headers")
            headers.include_user_info_headers = lambda value, _user: value

            gate_name = "open_webui.retrieval.rag_gate"
            gate = load_module(gate_name, RAG_GATE)

            good_response = mock.Mock()
            good_response.raise_for_status.return_value = None
            good_response.json.return_value = {
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 1, "relevance_score": 0.1},
                ]
            }
            malformed_response = mock.Mock()
            malformed_response.raise_for_status.return_value = None
            malformed_response.json.return_value = {
                "results": [{"index": 1, "relevance_score": 0.9}]
            }

            with mock.patch.dict(
                sys.modules,
                {
                    "open_webui": open_webui,
                    "open_webui.env": env,
                    "open_webui.retrieval.models.base_reranker": base,
                    "open_webui.retrieval.rag_gate": gate,
                    "open_webui.utils.headers": headers,
                },
            ):
                external = load_module("patched_external_reranker", external_path)
                with mock.patch.object(
                    external.requests,
                    "post",
                    side_effect=[good_response, malformed_response],
                ) as post:
                    reranker = external.ExternalReranker(
                        api_key="fixture-key",
                        url="http://127.0.0.1:9000/v1/rerank",
                        model="zerank-2-GGUF-Q8_0",
                        timeout=12.0,
                    )
                    reranker.qualify()
                    with self.assertRaises(gate.RAGUnavailableError):
                        reranker.predict([("query", "document")])
                    with self.assertRaises(gate.RAGUnavailableError):
                        reranker.predict([("query", "document")])

            # The closed latch rejects the third request without touching the provider.
            self.assertEqual(post.call_count, 2)

        for timeout in (None, 0, -1, math.inf, math.nan, True):
            with (
                self.subTest(timeout=timeout),
                self.assertRaises((ValueError, gate.RAGUnavailableError)),
            ):
                external.ExternalReranker(
                    api_key="fixture-key",
                    timeout=timeout,
                )

    def test_patch_applies_to_retained_exact_open_webui_source_and_compiles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            for relative in (
                "backend/open_webui/retrieval/models/external.py",
                "backend/open_webui/retrieval/utils.py",
                "backend/open_webui/utils/middleware.py",
                "backend/open_webui/tools/builtin.py",
                "backend/open_webui/routers/retrieval.py",
                "backend/open_webui/main.py",
            ):
                destination = source_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.upstream_source / relative, destination)

            checked = subprocess.run(
                ["git", "apply", "--check", str(RAG_PATCH)],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            subprocess.run(
                ["git", "apply", str(RAG_PATCH)],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=True,
            )
            shutil.copyfile(
                RAG_GATE,
                source_root / "backend" / "open_webui" / "retrieval" / "rag_gate.py",
            )
            compiled = subprocess.run(
                [sys.executable, "-m", "compileall", "-q", "backend/open_webui"],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
                env={
                    **os.environ,
                    "PYTHONPYCACHEPREFIX": str(source_root / "pycache"),
                },
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr or compiled.stdout)


if __name__ == "__main__":
    unittest.main()
