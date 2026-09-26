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
# 0005 helpers in tools/builtin.py that the gated builtin tools call.
BUILTIN_GATE_HELPERS = frozenset(
    {
        "_knowledge_note_ids",
        "_rag_closed",
        "_rag_closed_tool_error",
        "_rag_unavailable_tool_error",
    }
)
EXTERNAL_RERANKER_PREIMAGE = (
    REPO_ROOT
    / "tools"
    / "fixtures"
    / "open-webui-household"
    / "open-webui-0.11.4-pristine-external-reranker.py"
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

    def exec_patched_definitions(
        self, relative: str, names: set[str], namespace: dict
    ) -> set[str]:
        """Execute the named top-level definitions of one 0005-patched file."""

        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            path = source_root / relative
            path.parent.mkdir(parents=True)
            shutil.copyfile(self.upstream_source / relative, path)
            applied = subprocess.run(
                ["git", "apply", f"--include={relative}", str(RAG_PATCH)],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            parsed = ast.parse(path.read_text(encoding="utf-8"))
            nodes: list[ast.stmt] = [
                node
                for node in parsed.body
                if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                and node.name in names
            ]
            exec(  # noqa: S102 - executes extracted definitions from the exact bound source
                compile(
                    ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                    str(path),
                    "exec",
                ),
                namespace,
            )
        return {getattr(node, "name", "") for node in nodes}

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
            function_nodes: list[ast.stmt] = [
                node
                for node in parsed.body
                if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                and node.name
                in {"query_chat_files", "query_knowledge_files"} | BUILTIN_GATE_HELPERS
            ]
            namespace = {
                # 0.11.4 serializes through JSONCodec, which is stdlib json
                # unless ENABLE_ORJSON is set.
                "JSONCodec": __import__("json"),
                "log": mock.Mock(),
                "Optional": __import__("typing").Optional,
                "RAG_UNAVAILABLE_DETAIL": self.gate.RAG_UNAVAILABLE_DETAIL,
                "RAGUnavailableError": self.gate.RAGUnavailableError,
                "Request": object,
                "require_required_reranker": self.gate.require_required_reranker,
            }
            exec(  # noqa: S102 - executes extracted functions from the exact bound source
                compile(
                    ast.fix_missing_locations(
                        ast.Module(body=function_nodes, type_ignores=[])
                    ),
                    str(builtin_path),
                    "exec",
                ),
                namespace,
            )

            # A qualified gate lets both tools reach retrieval, which then fails.
            self.gate.configure_required_reranker(True)
            self.gate.qualify_required_reranker([0.91, 0.08])
            request = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(RERANKING_FUNCTION=object()))
            )
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
            "Open WebUI commit: 8bd8b4fac5e059578ac0c74b3c18d11139f88b7d", patch
        )
        self.assertIn(
            "Open WebUI 0.11.4 sdist SHA-256: "
            "1f1a31668a0dee733953c29d6183d78dd78984e696aa8eb0f2083f5796497be0",
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
                        model="zerank-2-GGUF",
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

    def test_empty_rerank_candidates_return_nothing_and_keep_the_gate_open(self):
        # Since 0.11.4, RerankCompressor returns [] for an empty candidate
        # list before it consults the reranker, so an empty retrieval yields
        # no content and no longer closes the qualified gate. Real candidates
        # still pass only with valid reranker scores, or close the gate.
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            relative = "backend/open_webui/retrieval/utils.py"
            utils_path = source_root / relative
            utils_path.parent.mkdir(parents=True)
            shutil.copyfile(self.upstream_source / relative, utils_path)
            applied = subprocess.run(
                ["git", "apply", f"--include={relative}", str(RAG_PATCH)],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            parsed = ast.parse(utils_path.read_text(encoding="utf-8"))
            compressor_node = next(
                node
                for node in parsed.body
                if isinstance(node, ast.ClassDef) and node.name == "RerankCompressor"
            )

            class CompressorFields:
                def __init__(self, **fields):
                    for name, value in fields.items():
                        setattr(self, name, value)

            typing_module = __import__("typing")
            namespace = {
                "Any": typing_module.Any,
                "BaseDocumentCompressor": CompressorFields,
                "Callbacks": typing_module.Any,
                "Document": SimpleNamespace,
                "RAGUnavailableError": self.gate.RAGUnavailableError,
                "Sequence": typing_module.Sequence,
                "asyncio": asyncio,
                "close_required_reranker": self.gate.close_required_reranker,
                "operator": __import__("operator"),
                "validate_rerank_scores": self.gate.validate_rerank_scores,
            }
            exec(  # noqa: S102 - executes one extracted class from the exact bound source
                compile(
                    ast.fix_missing_locations(
                        ast.Module(body=[compressor_node], type_ignores=[])
                    ),
                    str(utils_path),
                    "exec",
                ),
                namespace,
            )

        reranked_batches = []

        def malformed_reranker(query, documents):
            reranked_batches.append(list(documents))
            return []

        compressor = namespace["RerankCompressor"](
            embedding_function=None,
            top_n=3,
            reranking_function=malformed_reranker,
            r_score=0.0,
        )
        marker = object()
        self.gate.configure_required_reranker(True)
        self.gate.qualify_required_reranker([0.91, 0.08])

        self.assertEqual(asyncio.run(compressor.acompress_documents([], "query")), [])
        self.assertEqual(reranked_batches, [])
        self.gate.require_required_reranker(marker)

        candidate = SimpleNamespace(page_content="unreranked text", metadata={})
        with self.assertRaises(self.gate.RAGUnavailableError):
            asyncio.run(compressor.acompress_documents([candidate], "query"))
        self.assertEqual(reranked_batches, [[candidate]])
        with self.assertRaises(self.gate.RAGUnavailableError):
            self.gate.require_required_reranker(marker)

    def test_hybrid_search_error_fails_closed_without_unreranked_vector_fallback(self):
        # Upstream query_collection falls back to a plain vector search when
        # hybrid search raises, and that search never reaches the reranker.
        # With reranking required, the error fails closed with the gate's
        # stable 503 instead. It is not a reranker fault, so the gate stays
        # qualified and the next request retries hybrid search.
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            relative = "backend/open_webui/retrieval/utils.py"
            utils_path = source_root / relative
            utils_path.parent.mkdir(parents=True)
            shutil.copyfile(self.upstream_source / relative, utils_path)
            applied = subprocess.run(
                ["git", "apply", f"--include={relative}", str(RAG_PATCH)],
                cwd=source_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)

            parsed = ast.parse(utils_path.read_text(encoding="utf-8"))
            function_nodes: list[ast.stmt] = [
                node
                for node in parsed.body
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name
                in {"query_collection", "query_collection_with_hybrid_search"}
            ]
            self.assertEqual(len(function_nodes), 2)

            class FixtureConfig:
                # The packaged retrieval settings that reach this path.
                values: ClassVar[dict] = {
                    "rag.enable_hybrid_search": True,
                    "rag.bypass_embedding_and_retrieval": False,
                    "rag.top_k_reranker": 3,
                    "rag.relevance_threshold": 0.0,
                    "rag.hybrid_bm25_weight": 0.5,
                    "rag.enable_hybrid_search_enriched_texts": False,
                }

                @classmethod
                async def get_many(cls, *keys):
                    return {key: cls.values.get(key) for key in keys}

            vector_searches = []

            def unreranked_vector_search(**kwargs):
                vector_searches.append(kwargs["collection_name"])
                return SimpleNamespace(
                    model_dump=lambda: {
                        "distances": [[0.42]],
                        "documents": [["unreranked text"]],
                        "metadatas": [[{}]],
                    }
                )

            def merge_results(results, k):
                return {
                    key: [[value for result in results for value in result[key][0]][:k]]
                    for key in ("distances", "documents", "metadatas")
                }

            hybrid_search = mock.AsyncMock()
            namespace = {
                "ASYNC_VECTOR_DB_CLIENT": SimpleNamespace(
                    get=mock.AsyncMock(return_value=object())
                ),
                "Config": FixtureConfig,
                "RAG_EMBEDDING_QUERY_PREFIX": "query: ",
                "RAGUnavailableError": self.gate.RAGUnavailableError,
                "asyncio": asyncio,
                "log": mock.Mock(),
                "merge_and_sort_query_results": merge_results,
                "query_doc": unreranked_vector_search,
                "query_doc_with_hybrid_search": hybrid_search,
                # Qdrant has no backend-native hybrid search.
                "query_doc_with_native_hybrid_search": mock.AsyncMock(
                    return_value=None
                ),
                "require_safe_retrieval_mode": self.gate.require_safe_retrieval_mode,
            }
            exec(  # noqa: S102 - executes two extracted functions from the exact bound source
                compile(
                    ast.fix_missing_locations(
                        ast.Module(body=function_nodes, type_ignores=[])
                    ),
                    str(utils_path),
                    "exec",
                ),
                namespace,
            )

        query_collection = namespace["query_collection"]
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(RERANKING_FUNCTION=lambda *_args, **_kwargs: [])
            )
        )
        embedding_function = mock.AsyncMock(return_value=[[0.1, 0.2]])

        def retrieve(collection_names):
            return asyncio.run(
                query_collection(
                    request,
                    collection_names=collection_names,
                    queries=["private query"],
                    embedding_function=embedding_function,
                    k=3,
                )
            )

        marker = object()
        self.gate.configure_required_reranker(True)
        self.gate.qualify_required_reranker([0.91, 0.08])

        hybrid_search.return_value = {
            "distances": [[0.97]],
            "documents": [["reranked text"]],
            "metadatas": [[{}]],
        }
        self.assertEqual(retrieve(["file-a"])["documents"], [["reranked text"]])

        # An ordinary error in every collection's hybrid query, such as a BM25
        # or embedding fault, makes hybrid search raise for the whole request.
        hybrid_search.reset_mock(return_value=True)
        hybrid_search.side_effect = TypeError("'NoneType' object is not a mapping")
        with self.assertRaises(self.gate.RAGUnavailableError) as refused:
            retrieve(["file-a", "file-b"])
        self.assertEqual(str(refused.exception), self.gate.RAG_UNAVAILABLE_DETAIL)
        self.assertEqual(hybrid_search.await_count, 2)
        self.assertEqual(vector_searches, [])
        embedding_function.assert_not_awaited()
        self.gate.require_required_reranker(marker)

    def test_mixed_full_context_chat_refuses_while_closed_and_passes_when_qualified(
        self,
    ):
        # A full-context file beside a searched one makes all_full_context
        # false. A closed gate still refuses the whole attachment set before
        # query generation; a qualified gate passes the explicit full item on.
        class FixtureConfig:
            @classmethod
            async def get_many(cls, *keys):
                packaged = {
                    "rag.enable_hybrid_search": True,
                    "rag.full_context": False,
                    "rag.bypass_embedding_and_retrieval": False,
                }
                return {key: packaged.get(key) for key in keys}

        generate_queries = mock.AsyncMock(side_effect=RuntimeError("no task model"))
        source_lookup = mock.AsyncMock(return_value=[])
        namespace = {
            "Config": FixtureConfig,
            "RAGUnavailableError": self.gate.RAGUnavailableError,
            "Request": object,
            "UserModel": object,
            "generate_queries": generate_queries,
            "get_last_user_message": lambda messages: messages[-1]["content"],
            "get_sources_from_items": source_lookup,
            "log": mock.Mock(),
            "require_file_rag_ready": self.gate.require_file_rag_ready,
        }
        self.exec_patched_definitions(
            "backend/open_webui/utils/middleware.py",
            {"chat_completion_files_handler"},
            namespace,
        )
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(RERANKING_FUNCTION=lambda *_args, **_kwargs: [])
            )
        )
        mixed = [
            {"type": "file", "id": "full-file", "context": "full"},
            {"type": "file", "id": "searched-file"},
        ]

        def chat():
            return asyncio.run(
                namespace["chat_completion_files_handler"](
                    request,
                    {
                        "metadata": {"files": mixed},
                        "messages": [{"role": "user", "content": "private query"}],
                        "model": "chat",
                    },
                    {"__event_emitter__": mock.AsyncMock()},
                    object(),
                )
            )

        self.gate.configure_required_reranker(True)
        with self.assertRaises(self.gate.RAGUnavailableError):
            chat()
        generate_queries.assert_not_awaited()
        source_lookup.assert_not_awaited()

        self.gate.qualify_required_reranker([0.91, 0.08])
        chat()
        source_lookup.assert_awaited_once()
        lookup = source_lookup.await_args_list[0].kwargs
        self.assertEqual(lookup["items"], mixed)
        self.assertIs(lookup["full_context"], False)

    def test_mixed_full_context_sources_refuse_while_closed_and_pass_when_qualified(
        self,
    ):
        # get_sources_from_items serves the files handler and query_chat_files.
        # A closed gate refuses before any item is read; a qualified gate
        # returns the explicit full-context item whole and searches the rest.
        whole_text = "whole explicitly requested document"
        searched = {
            "distances": [[0.97]],
            "documents": [["reranked chunk"]],
            "metadatas": [[{"file_id": "searched-file"}]],
        }

        class FixtureConfig:
            @classmethod
            async def get(cls, key):
                return {"rag.bypass_embedding_and_retrieval": False}.get(key)

        files = SimpleNamespace(
            get_file_by_id=mock.AsyncMock(
                return_value=SimpleNamespace(id="searched-file", user_id="fixture-user")
            )
        )
        query_collection = mock.AsyncMock(return_value=searched)
        namespace = {
            "BYPASS_RETRIEVAL_ACCESS_CONTROL": False,
            "Config": FixtureConfig,
            "Files": files,
            "RAGUnavailableError": self.gate.RAGUnavailableError,
            "UserModel": object,
            "asyncio": asyncio,
            "filter_accessible_collections": mock.AsyncMock(
                side_effect=lambda names, _user: names
            ),
            "log": mock.Mock(),
            "query_collection": query_collection,
            "require_safe_retrieval_mode": self.gate.require_safe_retrieval_mode,
        }
        self.exec_patched_definitions(
            "backend/open_webui/retrieval/utils.py",
            {"get_sources_from_items"},
            namespace,
        )
        items = [
            {
                "type": "file",
                "id": "full-file",
                "name": "full.md",
                "context": "full",
                "file": {"data": {"content": whole_text}},
            },
            {"type": "file", "id": "searched-file"},
        ]

        def sources():
            return asyncio.run(
                namespace["get_sources_from_items"](
                    None,
                    [dict(item) for item in items],
                    ["private query"],
                    mock.AsyncMock(),
                    3,
                    lambda *_args, **_kwargs: [],
                    3,
                    0.0,
                    0.5,
                    True,
                    full_context=False,
                    user=SimpleNamespace(id="fixture-user", role="user"),
                )
            )

        self.gate.configure_required_reranker(True)
        with self.assertRaises(self.gate.RAGUnavailableError):
            sources()
        files.get_file_by_id.assert_not_awaited()
        query_collection.assert_not_awaited()

        self.gate.qualify_required_reranker([0.91, 0.08])
        documents = [source["document"] for source in sources()]
        self.assertEqual(documents, [[whole_text], ["reranked chunk"]])
        self.assertEqual(
            query_collection.await_args_list[0].kwargs["collection_names"],
            {"file-searched-file"},
        )

    def test_builtin_knowledge_tools_refuse_while_closed_and_read_when_qualified(
        self,
    ):
        # Native function calling stays on. While the gate is closed, every
        # builtin tool that returns file, knowledge, or attached-note content
        # answers with the gate's tool error before reading anything. A
        # qualified gate allows these explicit whole-document reads.
        knowledge_text = "The brass key opens the seed cabinet."
        note_text = "Attached note: the seed cabinet is in the shed."
        stored_file = SimpleNamespace(
            id="file-1",
            filename="handbook.md",
            user_id="fixture-user",
            data={"content": knowledge_text},
            created_at=1,
            updated_at=1,
        )
        stored_note = SimpleNamespace(
            id="note-1",
            title="Shed",
            user_id="fixture-user",
            data={"content": {"md": note_text}},
        )
        json_codec = __import__("json")
        files = SimpleNamespace(get_file_by_id=mock.AsyncMock(return_value=stored_file))
        notes = SimpleNamespace(get_note_by_id=mock.AsyncMock(return_value=stored_note))
        knowledges = SimpleNamespace(
            get_knowledges_by_file_id=mock.AsyncMock(return_value=[])
        )
        chat_files = mock.AsyncMock(
            return_value=[({"type": "file", "id": "file-1"}, stored_file)]
        )
        attributes = {
            "open_webui": {},
            "open_webui.models": {},
            "open_webui.models.access_grants": {"AccessGrants": object()},
            "open_webui.models.files": {"Files": files},
            "open_webui.models.knowledge": {"Knowledges": knowledges},
            "open_webui.models.notes": {"Notes": notes},
            "open_webui.retrieval": {},
            "open_webui.retrieval.external": {
                "retrieve_external_knowledge": mock.AsyncMock()
            },
            "open_webui.retrieval.utils": {"query_collection": mock.AsyncMock()},
        }
        modules = {}
        for name, values in attributes.items():
            modules[name] = types.ModuleType(name)
            vars(modules[name]).update(values)

        def grep(files_to_search, _pattern, _case_insensitive, _count_only):
            return json_codec.dumps(
                [
                    {"file_id": file.id, "line": file.data["content"]}
                    for file in files_to_search
                ]
            )

        namespace = {
            "Groups": SimpleNamespace(
                get_groups_by_member_id=mock.AsyncMock(return_value=[])
            ),
            "JSONCodec": json_codec,
            "Optional": __import__("typing").Optional,
            "RAG_UNAVAILABLE_DETAIL": self.gate.RAG_UNAVAILABLE_DETAIL,
            "RAGUnavailableError": self.gate.RAGUnavailableError,
            "Request": object,
            "UserModel": lambda **fields: SimpleNamespace(**fields),
            "VIEW_FILE_DEFAULT_MAX_CHARS": 10_000,
            "VIEW_FILE_MAX_CHARS": 100_000,
            "_get_accessible_chat_files": chat_files,
            "_grep_file_models": grep,
            "_has_read_access_to_file": mock.AsyncMock(return_value=True),
            "asyncio": asyncio,
            "log": mock.Mock(),
            "require_required_reranker": self.gate.require_required_reranker,
        }
        tools = {
            "grep_chat_files": {
                "pattern": "brass",
                "__files__": [{"type": "file", "id": "file-1"}],
            },
            "grep_knowledge_files": {"pattern": "brass", "file_id": "file-1"},
            "view_file": {"file_id": "file-1"},
            "view_knowledge_file": {"file_id": "file-1"},
            "query_knowledge_files": {
                "query": "seed cabinet",
                "__model_knowledge__": [{"type": "note", "id": "note-1"}],
            },
        }
        defined = self.exec_patched_definitions(
            "backend/open_webui/tools/builtin.py",
            set(tools) | BUILTIN_GATE_HELPERS,
            namespace,
        )
        self.assertLessEqual(set(tools), defined)
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    RERANKING_FUNCTION=object(), EMBEDDING_FUNCTION=object()
                )
            )
        )
        user = {"id": "fixture-user", "role": "user"}
        refusal = {
            "error": self.gate.RAG_UNAVAILABLE_DETAIL,
            "status": HTTPStatus.SERVICE_UNAVAILABLE,
        }
        readers = (
            files.get_file_by_id,
            notes.get_note_by_id,
            knowledges.get_knowledges_by_file_id,
            chat_files,
        )

        def call(name):
            with mock.patch.dict(sys.modules, modules):
                return asyncio.run(
                    namespace[name](__request__=request, __user__=user, **tools[name])
                )

        self.gate.configure_required_reranker(True)
        for name in tools:
            with self.subTest(gate="closed", tool=name):
                result = call(name)
                self.assertEqual(json_codec.loads(result), refusal)
                self.assertNotIn("seed cabinet", result)
        for reader in readers:
            reader.assert_not_awaited()

        self.gate.qualify_required_reranker([0.91, 0.08])
        for name in tools:
            with self.subTest(gate="qualified", tool=name):
                expected = (
                    note_text if name == "query_knowledge_files" else knowledge_text
                )
                self.assertIn(expected, call(name))

    def test_all_full_context_chat_passes_when_qualified_but_not_in_global_modes(
        self,
    ):
        # Every attachment set to full context is an explicit whole-document
        # request: refused while closed, allowed once qualified. The global
        # full-context and bypass modes stay refused even when qualified.
        class FixtureConfig:
            values: ClassVar[dict] = {}

            @classmethod
            async def get_many(cls, *keys):
                return {key: cls.values.get(key) for key in keys}

        generate_queries = mock.AsyncMock()
        source_lookup = mock.AsyncMock(return_value=[])
        namespace = {
            "Config": FixtureConfig,
            "RAGUnavailableError": self.gate.RAGUnavailableError,
            "Request": object,
            "UserModel": object,
            "generate_queries": generate_queries,
            "get_last_user_message": lambda messages: messages[-1]["content"],
            "get_sources_from_items": source_lookup,
            "log": mock.Mock(),
            "require_file_rag_ready": self.gate.require_file_rag_ready,
        }
        self.exec_patched_definitions(
            "backend/open_webui/utils/middleware.py",
            {"chat_completion_files_handler"},
            namespace,
        )
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(RERANKING_FUNCTION=lambda *_args, **_kwargs: [])
            )
        )
        full = [
            {"type": "file", "id": "first-file", "context": "full"},
            {"type": "file", "id": "second-file", "context": "full"},
        ]
        packaged = {
            "rag.enable_hybrid_search": True,
            "rag.full_context": False,
            "rag.bypass_embedding_and_retrieval": False,
        }

        def chat(**config):
            FixtureConfig.values = {**packaged, **config}
            return asyncio.run(
                namespace["chat_completion_files_handler"](
                    request,
                    {
                        "metadata": {"files": full},
                        "messages": [{"role": "user", "content": "private query"}],
                        "model": "chat",
                    },
                    {"__event_emitter__": mock.AsyncMock()},
                    object(),
                )
            )

        self.gate.configure_required_reranker(True)
        with self.assertRaises(self.gate.RAGUnavailableError):
            chat()
        source_lookup.assert_not_awaited()

        self.gate.qualify_required_reranker([0.91, 0.08])
        chat()
        lookup = source_lookup.await_args_list[0].kwargs
        self.assertEqual(lookup["items"], full)
        self.assertIs(lookup["full_context"], True)
        generate_queries.assert_not_awaited()

        for mode in (
            {"rag.full_context": True},
            {"rag.bypass_embedding_and_retrieval": True},
        ):
            with (
                self.subTest(mode=mode),
                self.assertRaises(self.gate.RAGUnavailableError),
            ):
                chat(**mode)
        source_lookup.assert_awaited_once()

    def test_all_full_context_sources_return_whole_documents_only_when_qualified(
        self,
    ):
        # get_sources_from_items refuses only the global modes, which it reads
        # from Config, not its full_context argument.
        class FixtureConfig:
            values: ClassVar[dict] = {}

            @classmethod
            async def get(cls, key):
                return cls.values.get(key)

        namespace = {
            "Config": FixtureConfig,
            "RAGUnavailableError": self.gate.RAGUnavailableError,
            "UserModel": object,
            "log": mock.Mock(),
            "require_safe_retrieval_mode": self.gate.require_safe_retrieval_mode,
        }
        self.exec_patched_definitions(
            "backend/open_webui/retrieval/utils.py",
            {"get_sources_from_items"},
            namespace,
        )
        whole = ["first whole document", "second whole document"]
        items = [
            {
                "type": "file",
                "id": f"file-{index}",
                "name": f"file-{index}.md",
                "context": "full",
                "file": {"data": {"content": text}},
            }
            for index, text in enumerate(whole)
        ]

        def sources(**config):
            FixtureConfig.values = {
                "rag.full_context": False,
                "rag.bypass_embedding_and_retrieval": False,
                **config,
            }
            return asyncio.run(
                namespace["get_sources_from_items"](
                    None,
                    [dict(item) for item in items],
                    ["private query"],
                    mock.AsyncMock(),
                    3,
                    lambda *_args, **_kwargs: [],
                    3,
                    0.0,
                    0.5,
                    True,
                    full_context=True,
                    user=SimpleNamespace(id="fixture-user", role="user"),
                )
            )

        self.gate.configure_required_reranker(True)
        with self.assertRaises(self.gate.RAGUnavailableError):
            sources()

        self.gate.qualify_required_reranker([0.91, 0.08])
        self.assertEqual(
            [source["document"] for source in sources()], [[text] for text in whole]
        )
        for mode in (
            {"rag.full_context": True},
            {"rag.bypass_embedding_and_retrieval": True},
        ):
            with (
                self.subTest(mode=mode),
                self.assertRaises(self.gate.RAGUnavailableError),
            ):
                sources(**mode)

    def test_knowledge_attached_notes_refuse_while_closed_but_personal_notes_stay(
        self,
    ):
        # Notes attached to the model or its folder as knowledge are gated:
        # view_note refuses them and search_notes omits them while the gate is
        # closed. Unattached notes and chat attachments are personal data and
        # stay readable. A qualified gate allows every note.
        json_codec = __import__("json")
        stored = {
            note_id: SimpleNamespace(
                id=note_id,
                title=note_id,
                user_id="fixture-user",
                created_at=1,
                updated_at=1,
                data={"content": {"md": f"seed cabinet text of {note_id}"}},
            )
            for note_id in ("model-note", "folder-note", "chat-note", "own-note")
        }
        notes = SimpleNamespace(
            get_note_by_id=mock.AsyncMock(side_effect=lambda note_id: stored[note_id]),
            search_notes=mock.AsyncMock(
                return_value=SimpleNamespace(items=list(stored.values()))
            ),
        )
        access_grants = types.ModuleType("open_webui.models.access_grants")
        vars(access_grants).update(AccessGrants=object())
        namespace = {
            "Groups": SimpleNamespace(
                get_groups_by_member_id=mock.AsyncMock(return_value=[])
            ),
            "JSONCodec": json_codec,
            "Notes": notes,
            "Optional": __import__("typing").Optional,
            "RAG_UNAVAILABLE_DETAIL": self.gate.RAG_UNAVAILABLE_DETAIL,
            "RAGUnavailableError": self.gate.RAGUnavailableError,
            "Request": object,
            "log": mock.Mock(),
            "require_required_reranker": self.gate.require_required_reranker,
        }
        self.exec_patched_definitions(
            "backend/open_webui/tools/builtin.py",
            {"view_note", "search_notes"} | BUILTIN_GATE_HELPERS,
            namespace,
        )
        knowledge = [
            {"type": "note", "id": "model-note", "source": "model"},
            {"type": "note", "id": "folder-note", "source": "folder"},
            {"type": "note", "id": "chat-note", "source": "chat"},
        ]
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(RERANKING_FUNCTION=object()))
        )
        user = {"id": "fixture-user", "role": "user"}
        refusal = {
            "error": self.gate.RAG_UNAVAILABLE_DETAIL,
            "status": HTTPStatus.SERVICE_UNAVAILABLE,
        }

        def view(note_id):
            with mock.patch.dict(
                sys.modules, {"open_webui.models.access_grants": access_grants}
            ):
                return json_codec.loads(
                    asyncio.run(
                        namespace["view_note"](
                            note_id,
                            __request__=request,
                            __user__=user,
                            __model_knowledge__=knowledge,
                        )
                    )
                )

        def search():
            result = asyncio.run(
                namespace["search_notes"](
                    "seed cabinet",
                    count=5,
                    __request__=request,
                    __user__=user,
                    __model_knowledge__=knowledge,
                )
            )
            return [note["id"] for note in json_codec.loads(result)]

        self.gate.configure_required_reranker(True)
        for note_id in ("model-note", "folder-note"):
            with self.subTest(gate="closed", note=note_id):
                self.assertEqual(view(note_id), refusal)
        notes.get_note_by_id.assert_not_awaited()
        for note_id in ("chat-note", "own-note"):
            with self.subTest(gate="closed", note=note_id):
                self.assertIn(note_id, view(note_id)["content"])
        self.assertEqual(search(), ["chat-note", "own-note"])

        self.gate.qualify_required_reranker([0.91, 0.08])
        for note_id in stored:
            with self.subTest(gate="qualified", note=note_id):
                self.assertIn(note_id, view(note_id)["content"])
        self.assertEqual(search(), list(stored))

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
