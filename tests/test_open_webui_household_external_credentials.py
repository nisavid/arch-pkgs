import ast
import asyncio
import copy
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.open_webui_household_source_fixture import (
    materialize_exact_open_webui_source,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "packages" / "open-webui"
PATCH_0005 = PACKAGE_DIR / "0005-require-qualified-reranking.patch"
PATCH_0006 = PACKAGE_DIR / "0006-enforce-session-epoch.patch"
PATCH_0007 = PACKAGE_DIR / "0007-keep-rag-credentials-external.patch"
RAG_GATE = PACKAGE_DIR / "open-webui-rag-gate.py"

OPEN_WEBUI_COMMIT = "f9590b8017199e56d5e953657e6498e3cef1d246"
OPEN_WEBUI_SDIST_SHA256 = (
    "e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9"
)
EXTERNAL_KEYS = {
    "rag.openai.api_key",
    "rag.external_reranker_api_key",
}


class _QueryField:
    def __init__(self):
        self.name = ""

    def __set_name__(self, _owner, name):
        self.name = name

    def __get__(self, instance, _owner):
        return self if instance is None else instance.__dict__[self.name]

    def __set__(self, instance, value):
        instance.__dict__[self.name] = value

    def in_(self, values):
        return ("in", self.name, set(values))

    def like(self, pattern):
        return ("like", self.name, pattern.removesuffix("%"))


class _Statement:
    def __init__(self, kind, target):
        self.kind = kind
        self.target = target
        self.predicate = None

    def where(self, predicate):
        self.predicate = predicate
        return self


class _Result:
    def __init__(self, rows, rowcount=0):
        self.rows = rows
        self.rowcount = rowcount

    def all(self):
        return list(self.rows)

    def scalars(self):
        return self


class _Base:
    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)


class _Session:
    def __init__(self):
        self.model = None
        self.rows = {}
        self.commit_count = 0

    async def get(self, _model, key):
        return self.rows.get(key)

    def add(self, row):
        self.rows[row.key] = row

    async def delete(self, row):
        self.rows.pop(row.key, None)

    async def commit(self):
        self.commit_count += 1

    async def execute(self, statement):
        if statement.kind == "delete":
            selected = self._matching_rows(statement.predicate)
            for row in selected:
                self.rows.pop(row.key, None)
            return _Result([], rowcount=len(selected))

        selected = self._matching_rows(statement.predicate)
        if isinstance(statement.target, _QueryField):
            return _Result([(getattr(row, statement.target.name),) for row in selected])
        return _Result(selected)

    def _matching_rows(self, predicate):
        rows = list(self.rows.values())
        if predicate is None:
            return rows
        kind, name, expected = predicate
        if kind == "in":
            return [row for row in rows if getattr(row, name) in expected]
        return [row for row in rows if getattr(row, name).startswith(expected)]


class _DBContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


class _RuntimeConfig:
    def __init__(self, **values):
        self.__dict__.update(values)
        self.saved = 0

    def __getattr__(self, _name):
        return None

    async def save(self):
        self.saved += 1


class _NullForm:
    def __init__(self, **values):
        self.__dict__.update(values)

    def __getattr__(self, _name):
        return None


def _extract_async_function(path: Path, name: str, namespace: dict):
    parsed = ast.parse(path.read_text(encoding="utf-8"))
    node = copy.deepcopy(
        next(
            item
            for item in parsed.body
            if isinstance(item, ast.AsyncFunctionDef) and item.name == name
        )
    )
    node.decorator_list = []
    node.returns = None
    node.args.defaults = []
    node.args.kw_defaults = [None for _ in node.args.kw_defaults]
    for item in ast.walk(node):
        if isinstance(item, ast.arg):
            item.annotation = None
    exec(  # noqa: S102 - exact bound source function under an isolated namespace
        compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
            str(path),
            "exec",
        ),
        namespace,
    )
    return namespace[name]


class OpenWebUIExternalCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pristine_temporary, cls.upstream_source = (
            materialize_exact_open_webui_source()
        )
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.composed_source = Path(cls.temp_dir.name)
        if not PATCH_0007.is_file():
            raise RuntimeError("0007 external credential patch is missing")

        existing_paths = {
            "backend/open_webui/retrieval/models/external.py",
            "backend/open_webui/retrieval/utils.py",
            "backend/open_webui/utils/middleware.py",
            "backend/open_webui/tools/builtin.py",
            "backend/open_webui/routers/retrieval.py",
            "backend/open_webui/main.py",
            "backend/open_webui/__init__.py",
            "backend/open_webui/utils/auth.py",
            "backend/open_webui/models/config.py",
            "src/lib/apis/retrieval/index.ts",
            "src/lib/components/admin/Settings/Documents.svelte",
        }
        for relative in existing_paths:
            target = cls.composed_source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cls.upstream_source / relative, target)

        gate_target = cls.composed_source / "backend/open_webui/retrieval/rag_gate.py"
        shutil.copyfile(RAG_GATE, gate_target)

        commands = (
            (
                ["patch", "--batch", "--fuzz=0", "-Np1", "-i", str(PATCH_0005)],
                cls.composed_source,
            ),
            (
                ["patch", "--batch", "--fuzz=0", "-Np1", "-i", str(PATCH_0006)],
                cls.composed_source / "backend",
            ),
            (
                ["patch", "--batch", "--fuzz=0", "-Np1", "-i", str(PATCH_0007)],
                cls.composed_source,
            ),
        )
        cls.patch_results = [
            subprocess.run(
                command,
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            for command, cwd in commands
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        cls.pristine_temporary.cleanup()

    def test_patch_is_exact_bound_zero_fuzz_and_compiles_after_0005_and_0006(self):
        self.assertTrue(
            PATCH_0007.is_file(), "0007 external credential patch is missing"
        )
        patch_text = PATCH_0007.read_text(encoding="utf-8")
        self.assertIn(OPEN_WEBUI_COMMIT, patch_text)
        self.assertIn(OPEN_WEBUI_SDIST_SHA256, patch_text)
        self.assertEqual(
            [result.returncode for result in self.patch_results],
            [0, 0, 0],
            "\n".join(result.stderr + result.stdout for result in self.patch_results),
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "py_compile",
                "backend/open_webui/models/config.py",
                "backend/open_webui/routers/retrieval.py",
            ],
            cwd=self.composed_source,
            env={
                **os.environ,
                "PYTHONPYCACHEPREFIX": str(self.composed_source / ".pycache"),
            },
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )

    def _load_config_model(self):
        session = _Session()
        sqlalchemy = types.ModuleType("sqlalchemy")
        sqlalchemy.JSON = object()
        sqlalchemy.BigInteger = object()
        sqlalchemy.Text = object()
        sqlalchemy.Column = lambda *_args, **_kwargs: _QueryField()
        sqlalchemy.delete = lambda target: _Statement("delete", target)
        sqlalchemy.select = lambda target: _Statement("select", target)

        db_module = types.ModuleType("open_webui.internal.db")
        db_module.Base = _Base
        db_module.get_async_db = lambda: _DBContext(session)
        open_webui = types.ModuleType("open_webui")
        open_webui.__path__ = []
        internal = types.ModuleType("open_webui.internal")
        internal.__path__ = []
        module_name = "open_webui_external_config_fixture"
        model_path = self.composed_source / "backend/open_webui/models/config.py"
        spec = importlib.util.spec_from_file_location(module_name, model_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "sqlalchemy": sqlalchemy,
                "open_webui": open_webui,
                "open_webui.internal": internal,
                "open_webui.internal.db": db_module,
                module_name: module,
            },
        ):
            spec.loader.exec_module(module)
        session.model = module.Config
        return module, session

    def test_external_keys_are_purged_ignored_rotated_and_never_exported(self):
        config_module, session = self._load_config_model()
        Config = config_module.Config
        defaults_a = {
            "rag.openai.api_key": "env-embed-a",
            "rag.external_reranker_api_key": "env-rerank-a",
            "ui.theme": "env-theme",
            "oauth.client.secret": "oauth-a",
        }
        Config.configure(
            defaults=defaults_a,
            enable_persistent=True,
            enable_oauth_persistent=False,
        )
        for key, value in {
            "rag.openai.api_key": "stale-embed",
            "rag.external_reranker_api_key": "stale-rerank",
            "ui.theme": "persisted-theme",
        }.items():
            session.add(Config(key=key, value=value, updated_at=1))

        asyncio.run(Config.seed_defaults(defaults_a))
        self.assertGreater(session.commit_count, 0)
        self.assertTrue(EXTERNAL_KEYS.isdisjoint(session.rows))
        self.assertEqual(asyncio.run(Config.get("rag.openai.api_key")), "env-embed-a")
        self.assertEqual(
            asyncio.run(Config.get("rag.external_reranker_api_key")),
            "env-rerank-a",
        )

        asyncio.run(
            Config.upsert(
                {
                    "rag.openai.api_key": "admin-embed",
                    "rag.external_reranker_api_key": "admin-rerank",
                    "ui.theme": "updated-theme",
                    "oauth.client.secret": "oauth-updated",
                }
            )
        )
        self.assertTrue(EXTERNAL_KEYS.isdisjoint(session.rows))
        self.assertEqual(Config.DEFAULTS["rag.openai.api_key"], "env-embed-a")
        self.assertEqual(
            Config.DEFAULTS["rag.external_reranker_api_key"], "env-rerank-a"
        )
        self.assertEqual(Config.DEFAULTS["oauth.client.secret"], "oauth-updated")
        self.assertEqual(session.rows["ui.theme"].value, "updated-theme")

        exported = asyncio.run(Config.get_all())
        namespaced = asyncio.run(Config.get_namespace("rag"))
        self.assertTrue(EXTERNAL_KEYS.isdisjoint(exported))
        self.assertTrue(EXTERNAL_KEYS.isdisjoint(namespaced))
        self.assertEqual(exported["ui.theme"], "updated-theme")
        self.assertEqual(exported["oauth.client.secret"], "oauth-updated")

        defaults_b = {
            **defaults_a,
            "rag.openai.api_key": "env-embed-b",
            "rag.external_reranker_api_key": "env-rerank-b",
            "oauth.client.secret": "oauth-b",
        }
        Config.configure(
            defaults=defaults_b,
            enable_persistent=True,
            enable_oauth_persistent=False,
        )
        asyncio.run(Config.seed_defaults(defaults_b))
        values = asyncio.run(
            Config.get_many(
                "rag.openai.api_key",
                "rag.external_reranker_api_key",
                "ui.theme",
            )
        )
        self.assertEqual(values["rag.openai.api_key"], "env-embed-b")
        self.assertEqual(values["rag.external_reranker_api_key"], "env-rerank-b")
        self.assertEqual(values["ui.theme"], "updated-theme")

    def test_embedding_admin_update_cannot_replace_active_external_key_or_leak_it(self):
        router = self.composed_source / "backend/open_webui/routers/retrieval.py"
        config = _RuntimeConfig(
            RAG_EMBEDDING_ENGINE="openai",
            RAG_EMBEDDING_MODEL="zembed",
            RAG_EMBEDDING_BATCH_SIZE=1,
            ENABLE_ASYNC_EMBEDDING=True,
            RAG_EMBEDDING_CONCURRENT_REQUESTS=1,
            RAG_OPENAI_API_BASE_URL="http://env/embed",
            RAG_OPENAI_API_KEY="env-embed-secret",
            RAG_OLLAMA_BASE_URL="http://ollama",
            RAG_OLLAMA_API_KEY="ollama-secret",
            RAG_AZURE_OPENAI_BASE_URL="http://azure",
            RAG_AZURE_OPENAI_API_KEY="azure-secret",
            RAG_AZURE_OPENAI_API_VERSION="v1",
        )
        captured = {}

        async def get_config():
            return config

        async def unload(_request):
            return None

        namespace = {
            "get_retrieval_config": get_config,
            "unload_embedding_model": unload,
            "get_ef": lambda *_args: object(),
            "get_embedding_function": lambda *args, **_kwargs: captured.setdefault(
                "key", args[4]
            ),
            "log": SimpleNamespace(
                info=lambda *_args: None, exception=lambda *_args: None
            ),
        }
        get_endpoint = _extract_async_function(
            router, "get_embedding_config", namespace
        )
        update_endpoint = _extract_async_function(
            router, "update_embedding_config", namespace
        )
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        before = asyncio.run(get_endpoint(request, object()))
        form = _NullForm(
            openai_config=SimpleNamespace(
                url="http://updated/embed", key="admin-secret"
            ),
            RAG_EMBEDDING_ENGINE="openai",
            RAG_EMBEDDING_MODEL="zembed",
            RAG_EMBEDDING_BATCH_SIZE=2,
            ENABLE_ASYNC_EMBEDDING=True,
            RAG_EMBEDDING_CONCURRENT_REQUESTS=2,
        )
        after = asyncio.run(update_endpoint(request, form, object()))

        self.assertNotIn("key", before["openai_config"])
        self.assertNotIn("key", after["openai_config"])
        self.assertNotIn("env-embed-secret", repr(before) + repr(after))
        self.assertEqual(config.RAG_OPENAI_API_KEY, "env-embed-secret")
        self.assertEqual(captured["key"], "env-embed-secret")
        self.assertEqual(config.RAG_EMBEDDING_BATCH_SIZE, 2)

    def test_reranker_admin_update_cannot_replace_active_external_key_or_leak_it(self):
        router = self.composed_source / "backend/open_webui/routers/retrieval.py"
        config = _RuntimeConfig(
            RAG_RERANKING_ENGINE="external",
            RAG_RERANKING_MODEL="zerank",
            RAG_RERANKING_BATCH_SIZE=1,
            RAG_EXTERNAL_RERANKER_URL="http://env/rerank",
            RAG_EXTERNAL_RERANKER_API_KEY="env-rerank-secret",
            RAG_EXTERNAL_RERANKER_TIMEOUT=5,
            ENABLE_RAG_HYBRID_SEARCH=True,
            BYPASS_EMBEDDING_AND_RETRIEVAL=False,
            TOP_K=3,
        )
        captured = {}

        async def get_config():
            return config

        def get_rf(*args):
            captured["key"] = args[3]
            return object()

        namespace = {
            "get_retrieval_config": get_config,
            "get_rf": get_rf,
            "get_reranking_function": lambda *_args, **_kwargs: object(),
            "configure_required_reranker": lambda *_args: None,
            "log": SimpleNamespace(
                info=lambda *_args: None,
                error=lambda *_args: None,
                exception=lambda *_args: None,
            ),
            "DEVICE_TYPE": "cpu",
        }
        get_endpoint = _extract_async_function(router, "get_rag_config", namespace)
        update_endpoint = _extract_async_function(
            router, "update_rag_config", namespace
        )
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    rf=None,
                    RERANKING_FUNCTION=None,
                    YOUTUBE_LOADER_TRANSLATION=None,
                )
            )
        )
        before = asyncio.run(get_endpoint(request, object()))
        form = _NullForm(RAG_EXTERNAL_RERANKER_API_KEY="admin-secret", TOP_K=9)
        after = asyncio.run(update_endpoint(request, form, object()))

        self.assertNotIn("RAG_EXTERNAL_RERANKER_API_KEY", before)
        self.assertNotIn("RAG_EXTERNAL_RERANKER_API_KEY", after)
        self.assertNotIn("env-rerank-secret", repr(before) + repr(after))
        self.assertEqual(config.RAG_EXTERNAL_RERANKER_API_KEY, "env-rerank-secret")
        self.assertEqual(captured["key"], "env-rerank-secret")
        self.assertEqual(config.TOP_K, 9)

    def test_admin_document_controls_disclose_external_authority_without_editing(self):
        document = (
            self.composed_source / "src/lib/components/admin/Settings/Documents.svelte"
        ).read_text(encoding="utf-8")
        forbidden_controls = (
            "let OpenAIKey = ''",
            "key: OpenAIKey",
            "embeddingConfig.openai_config.key",
            "bind:value={OpenAIKey}",
            "bind:value={RAGConfig.RAG_EXTERNAL_RERANKER_API_KEY}",
        )
        for forbidden in forbidden_controls:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, document)

        notice = (
            "Managed externally by the service. Restart the service after rotating it."
        )
        self.assertEqual(document.count(notice), 2)
        scrub = "delete ragConfigUpdate.RAG_EXTERNAL_RERANKER_API_KEY;"
        submit = "const res = await updateRAGConfig(localStorage.token, {"
        self.assertIn(scrub, document)
        self.assertLess(document.index(scrub), document.index(submit))

        api_contract = (
            self.composed_source / "src/lib/apis/retrieval/index.ts"
        ).read_text(encoding="utf-8")
        openai_type = api_contract.split("type OpenAIConfigForm = {", 1)[1].split(
            "};", 1
        )[0]
        self.assertNotIn("key:", openai_type)
        self.assertIn("url: string;", openai_type)


if __name__ == "__main__":
    unittest.main()
