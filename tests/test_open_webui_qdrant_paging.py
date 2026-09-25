import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "packages" / "open-webui"
FIXTURE_ROOT = REPO_ROOT / "tools" / "fixtures" / "open-webui-household"
QDRANT_CONFIG = REPO_ROOT / "packages" / "qdrant" / "qdrant.config.yaml"
PATCH_0008 = PACKAGE_DIR / "0008-page-qdrant-scroll.patch"

OPEN_WEBUI_COMMIT = "f9590b8017199e56d5e953657e6498e3cef1d246"
OPEN_WEBUI_SDIST_SHA256 = (
    "e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9"
)
DBS = "backend/open_webui/retrieval/vector/dbs"
# Exact bytes of the two clients in the pinned 0.11.0 sdist.
PRISTINE_CLIENTS = {
    f"{DBS}/qdrant.py": (
        FIXTURE_ROOT / "open-webui-0.11.0-pristine-qdrant.py",
        "173e172f9ed71300dc0dd8dbd959c85c110d842270b69c6852934cf86e9978f8",
    ),
    f"{DBS}/qdrant_multitenancy.py": (
        FIXTURE_ROOT / "open-webui-0.11.0-pristine-qdrant-multitenancy.py",
        "83b86f56b695160497246ba351a7e12afeec22463154741d73e1395ad81ea8ac",
    ),
}
STRICT_LIMIT = 1000
# More scroll calls than any test needs; a paging loop that exceeds it is stuck.
MAX_SCROLL_CALLS = 10


class LimitExceeded(Exception):
    pass


class ScrollDidNotStop(Exception):
    pass


class StrictScrollQdrant:
    """Fake Qdrant scroll_by with strict-mode request limits."""

    def __init__(self, *args, **kwargs):
        self.points = []
        self.limits = []
        self.filters = []
        self.offsets = []
        self.repeat_offset_at = None
        self.empty_page_at = None

    def load(
        self,
        count: int,
        repeat_offset_at: int | None = None,
        empty_page_at: int | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Hold UUID-ID points, with optional misbehaving pages.

        The two page overrides refer to positions in UUID order.
        """
        if ids is None:
            ids = [str(uuid.UUID(int=2 * index + 1)) for index in range(count)]
        if len(ids) != count:
            raise ValueError("count must match the number of IDs")
        self.points = sorted(
            (
                types.SimpleNamespace(
                    id=point_id,
                    payload={"text": f"chunk {index}", "metadata": {"n": index}},
                )
                for index, point_id in enumerate(ids)
            ),
            key=lambda point: uuid.UUID(point.id),
        )
        self.limits = []
        self.filters = []
        self.offsets = []
        self.repeat_offset_at = (
            self.points[repeat_offset_at].id if repeat_offset_at is not None else None
        )
        self.empty_page_at = (
            self.points[empty_page_at].id if empty_page_at is not None else None
        )

    def collection_exists(self, *args, **kwargs):
        return True

    def scroll(
        self, collection_name, scroll_filter=None, limit=10, offset=None, **kwargs
    ):
        if len(self.limits) >= MAX_SCROLL_CALLS:
            raise ScrollDidNotStop(f"more than {MAX_SCROLL_CALLS} scroll calls")
        self.limits.append(limit)
        self.filters.append(scroll_filter)
        self.offsets.append(offset)
        if limit < 1:
            raise LimitExceeded(f"Limit must be greater than 0: {limit}")
        if limit > STRICT_LIMIT:
            raise LimitExceeded(f'Limit exceeded {limit} > {STRICT_LIMIT} for "limit"')
        lower_bound = uuid.UUID(offset) if offset is not None else None
        start = next(
            (
                index
                for index, point in enumerate(self.points)
                if lower_bound is None or uuid.UUID(point.id) >= lower_bound
            ),
            len(self.points),
        )
        fetched = self.points[start : start + limit + 1]
        page = fetched[:limit]
        next_offset = fetched[limit].id if len(fetched) > limit else None
        if self.empty_page_at is not None and offset == self.empty_page_at:
            return [], self.points[start + 1].id
        if self.repeat_offset_at is not None and offset == self.repeat_offset_at:
            return page, offset
        return page, next_offset


class AnyModels:
    def __getattr__(self, name):
        return lambda *args, **kwargs: (name, args, kwargs)


def model(name: str, **kwargs) -> tuple:
    """What AnyModels returns for ``models.<name>(**kwargs)``."""
    return (name, (), kwargs)


class GetResult:
    def __init__(self, ids, documents, metadatas):
        self.ids = ids
        self.documents = documents
        self.metadatas = metadatas


def stub_module(name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def stub_modules() -> dict[str, types.ModuleType]:
    modules = (
        stub_module("grpc"),
        stub_module(
            "open_webui.config",
            QDRANT_API_KEY=None,
            QDRANT_COLLECTION_PREFIX="open-webui",
            QDRANT_GRPC_PORT=6334,
            QDRANT_HNSW_M=16,
            QDRANT_ON_DISK=False,
            QDRANT_PREFER_GRPC=False,
            QDRANT_TIMEOUT=5,
            QDRANT_URI="http://qdrant.invalid:6333",
        ),
        stub_module(
            "open_webui.retrieval.vector.main",
            GetResult=GetResult,
            SearchResult=GetResult,
            VectorDBBase=object,
            VectorItem=dict,
        ),
        stub_module("qdrant_client", QdrantClient=StrictScrollQdrant),
        stub_module("qdrant_client.http.models", PointStruct=dict),
        stub_module("qdrant_client.http.exceptions", UnexpectedResponse=Exception),
        stub_module("qdrant_client.models", models=AnyModels()),
    )
    return {module.__name__: module for module in modules}


def load_client_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path.name}")
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, stub_modules()):
        spec.loader.exec_module(module)
    return module


def patched_files(patch_text: str) -> set[str]:
    return {
        match.removeprefix("b/")
        for match in re.findall(r"(?m)^\+\+\+ (\S+)", patch_text)
    }


class OpenWebUIQdrantPagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temp_dir.name)
        for relative, (fixture, _) in PRISTINE_CLIENTS.items():
            target = cls.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fixture, target)
        cls.patch_result = subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-Np1", "-i", str(PATCH_0008)],
            cwd=cls.source,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if cls.patch_result.returncode != 0:
            return
        cls.qdrant = load_client_module(
            "open_webui_patched_qdrant", cls.source / DBS / "qdrant.py"
        )
        cls.multitenancy = load_client_module(
            "open_webui_patched_qdrant_multitenancy",
            cls.source / DBS / "qdrant_multitenancy.py",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def assert_patch_applied(self):
        self.assertEqual(
            self.patch_result.returncode,
            0,
            self.patch_result.stderr + self.patch_result.stdout,
        )

    def clients(self):
        self.assert_patch_applied()
        for module in (self.qdrant, self.multitenancy):
            client = module.QdrantClient()
            yield module.__name__, client

    def test_pristine_fixtures_are_the_pinned_upstream_bytes(self):
        for fixture, digest in PRISTINE_CLIENTS.values():
            self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), digest)

    def test_fake_rejects_invalid_requested_limits(self):
        client = StrictScrollQdrant()
        client.load(1)
        for limit in (0, -1, 1001):
            with self.subTest(limit=limit), self.assertRaises(LimitExceeded):
                client.scroll("file-abc", limit=limit)
        self.assertEqual(client.limits, [0, -1, 1001])

    def test_patch_is_bound_to_pinned_source_and_applies_after_0001_to_0007(self):
        patch_text = PATCH_0008.read_text(encoding="utf-8")
        self.assertIn(OPEN_WEBUI_COMMIT, patch_text)
        self.assertIn(OPEN_WEBUI_SDIST_SHA256, patch_text)
        self.assert_patch_applied()
        self.assertEqual(patched_files(patch_text), set(PRISTINE_CLIENTS))
        # 0001-0007 never touch the Qdrant clients, so applying 0008 to the
        # pristine files is the same as applying it after them.
        for earlier in sorted(PACKAGE_DIR.glob("000[1-7]-*.patch")):
            touched = patched_files(earlier.read_text(encoding="utf-8"))
            self.assertFalse(
                {path.removeprefix("backend/") for path in PRISTINE_CLIENTS}
                & {path.removeprefix("backend/") for path in touched},
                earlier.name,
            )

    def test_page_size_stays_within_packaged_qdrant_query_limit(self):
        self.assert_patch_applied()
        configured = re.search(
            r"(?m)^\s+max_query_limit:\s*(\d+)\s*$",
            QDRANT_CONFIG.read_text(encoding="utf-8"),
        )
        if configured is None:
            self.fail(f"no max_query_limit in {QDRANT_CONFIG.name}")
        for module in (self.qdrant, self.multitenancy):
            self.assertEqual(module.SCROLL_PAGE_SIZE, 1000)
            self.assertLessEqual(module.SCROLL_PAGE_SIZE, int(configured.group(1)))

    def test_get_and_unlimited_query_return_every_point(self):
        expected_limits = {
            0: [1000],
            1: [1000],
            999: [1000],
            1000: [1000],
            1001: [1000, 1000],
            2500: [1000, 1000, 1000],
        }
        for name, client in self.clients():
            for count in (0, 1, 999, 1000, 1001, 2500):
                for method, call in (
                    ("get", lambda: client.get("file-abc")),
                    ("query", lambda: client.query("file-abc", {"hash": "h"})),
                ):
                    with self.subTest(client=name, method=method, count=count):
                        client.client.load(count)
                        result = call()
                        self.assertIsNotNone(result)
                        self.assertEqual(
                            result.ids, [[point.id for point in client.client.points]]
                        )
                        self.assertEqual(
                            result.documents[0][-1:],
                            [f"chunk {count - 1}"] if count else [],
                        )
                        self.assertEqual(client.client.limits, expected_limits[count])

    def test_query_with_explicit_limit_returns_leading_points(self):
        for name, client in self.clients():
            for count, limit, expected, limits in (
                (2500, 1, 1, [1]),
                (2500, 999, 999, [999]),
                (2500, 1000, 1000, [1000]),
                (2500, 1500, 1500, [1000, 500]),
                (2500, 5000, 2500, [1000, 1000, 1000]),
                (1001, 1001, 1001, [1000, 1]),
                (0, 1000, 0, [1000]),
                (2500, 0, 0, []),
                (2500, -1, 0, []),
            ):
                with self.subTest(client=name, count=count, limit=limit):
                    client.client.load(count)
                    result = client.query("file-abc", {"hash": "h"}, limit=limit)
                    self.assertIsNotNone(result)
                    self.assertEqual(
                        result.ids,
                        [[point.id for point in client.client.points[:expected]]],
                    )
                    self.assertEqual(client.client.limits, limits)

    def test_scroll_uses_uuid_lower_bound_across_a_nonadjacent_page_boundary(self):
        ids = [str(uuid.UUID(int=index + 1)) for index in range(1000)]
        ids.append(str(uuid.UUID(int=10000)))
        for name, client in self.clients():
            with self.subTest(client=name):
                client.client.load(len(ids), ids=list(reversed(ids)))
                result = client.get("file-abc")
                self.assertIsNotNone(result)
                self.assertEqual(result.ids, [ids])
                self.assertEqual(client.client.limits, [1000, 1000])
                self.assertEqual(client.client.offsets, [None, ids[1000]])
                self.assertGreater(
                    uuid.UUID(ids[1000]).int - uuid.UUID(ids[999]).int, 1
                )

    def test_scroll_stops_when_qdrant_repeats_its_offset(self):
        for name, client in self.clients():
            for method, call in (
                ("get", lambda: client.get("file-abc")),
                ("query", lambda: client.query("file-abc", {"hash": "h"})),
                ("query limit", lambda: client.query("file-abc", {"hash": "h"}, limit=5000)),
            ):
                with self.subTest(client=name, method=method):
                    # The second page reports offset 1000 again instead of 2000.
                    client.client.load(2500, repeat_offset_at=1000)
                    result = call()
                    self.assertIsNotNone(result)
                    self.assertEqual(
                        result.ids,
                        [[point.id for point in client.client.points[:2000]]],
                    )
                    self.assertEqual(client.client.limits, [1000, 1000])

    def test_scroll_stops_on_empty_page_with_next_offset(self):
        for name, client in self.clients():
            for method, call in (
                ("get", lambda: client.get("file-abc")),
                ("query", lambda: client.query("file-abc", {"hash": "h"})),
                ("query limit", lambda: client.query("file-abc", {"hash": "h"}, limit=5000)),
            ):
                with self.subTest(client=name, method=method):
                    # The third page is empty but still reports a next offset.
                    client.client.load(2500, empty_page_at=2000)
                    result = call()
                    self.assertIsNotNone(result)
                    self.assertEqual(
                        result.ids,
                        [[point.id for point in client.client.points[:2000]]],
                    )
                    self.assertEqual(client.client.limits, [1000, 1000, 1000])

    def test_every_page_gets_the_filter_the_pristine_code_builds(self):
        self.assert_patch_applied()
        hash_match = model(
            "FieldCondition", key="metadata.hash", match=model("MatchValue", value="h")
        )
        tenant_match = model(
            "FieldCondition", key="tenant_id", match=model("MatchValue", value="file-abc")
        )
        expected = {
            (self.qdrant.__name__, "query"): model("Filter", should=[hash_match]),
            (self.qdrant.__name__, "get"): None,
            (self.multitenancy.__name__, "query"): model(
                "Filter", must=[tenant_match, hash_match]
            ),
            (self.multitenancy.__name__, "get"): model("Filter", must=[tenant_match]),
        }
        for name, client in self.clients():
            for method, call in (
                ("get", lambda: client.get("file-abc")),
                ("query", lambda: client.query("file-abc", {"hash": "h"})),
            ):
                with self.subTest(client=name, method=method):
                    client.client.load(2500)
                    call()
                    self.assertEqual(client.client.filters, [expected[name, method]] * 3)


if __name__ == "__main__":
    unittest.main()
