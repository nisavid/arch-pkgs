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

OPEN_WEBUI_COMMIT = "8bd8b4fac5e059578ac0c74b3c18d11139f88b7d"
OPEN_WEBUI_SDIST_SHA256 = (
    "1f1a31668a0dee733953c29d6183d78dd78984e696aa8eb0f2083f5796497be0"
)
DBS = "backend/open_webui/retrieval/vector/dbs"
# Exact bytes of the two clients in the pinned 0.11.4 sdist.
PRISTINE_CLIENTS = {
    f"{DBS}/qdrant.py": (
        FIXTURE_ROOT / "open-webui-0.11.4-pristine-qdrant.py",
        "eee72a5402471f04ce0309fad3660dff2e45a7e9ef6de519c72d59d6fe425eed",
    ),
    f"{DBS}/qdrant_multitenancy.py": (
        FIXTURE_ROOT / "open-webui-0.11.4-pristine-qdrant-multitenancy.py",
        "afee2d19757088bd87db5719882897f516dbb16ed9cfed53dceb3b2711f58b8f",
    ),
}
STRICT_LIMIT = 1000
# More scroll calls than any test needs; a paging loop that exceeds it is stuck.
MAX_SCROLL_CALLS = 10


class LimitExceeded(Exception):
    pass


class ScrollDidNotStop(Exception):
    pass


def condition_matches(payload: dict, condition: tuple) -> bool:
    """Evaluate an AnyModels FieldCondition(key, MatchValue(value)) on a payload."""
    name, _, fields = condition
    if name != "FieldCondition" or fields["match"][0] != "MatchValue":
        raise ValueError(f"fake Qdrant cannot evaluate {condition!r}")
    value = payload
    for part in fields["key"].split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value == fields["match"][2]["value"]


def filter_matches(payload: dict, scroll_filter: tuple | None) -> bool:
    """Qdrant filter semantics: every must condition and any should condition.

    An empty should list is not modeled, and no client here sends one.
    """
    if scroll_filter is None:
        return True
    name, _, clauses = scroll_filter
    must, should = clauses.get("must", []), clauses.get("should")
    if name != "Filter" or not clauses.keys() <= {"must", "should"} or should == []:
        raise ValueError(f"fake Qdrant cannot evaluate {scroll_filter!r}")
    return all(condition_matches(payload, c) for c in must) and (
        should is None or any(condition_matches(payload, c) for c in should)
    )


class StrictScrollQdrant:
    """Fake Qdrant scroll_by with strict-mode request limits and scroll filters."""

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

        Every point belongs to tenant file-abc and has hash h. The two page
        overrides refer to positions in UUID order.
        """
        if ids is None:
            ids = [str(uuid.UUID(int=2 * index + 1)) for index in range(count)]
        if len(ids) != count:
            raise ValueError("count must match the number of IDs")
        self.points = sorted(
            (
                types.SimpleNamespace(
                    id=point_id,
                    payload={
                        "text": f"chunk {index}",
                        "metadata": {"n": index, "hash": "h"},
                        "tenant_id": "file-abc",
                    },
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
        matching = [
            point for point in self.points if filter_matches(point.payload, scroll_filter)
        ]
        lower_bound = uuid.UUID(offset) if offset is not None else None
        start = next(
            (
                index
                for index, point in enumerate(matching)
                if lower_bound is None or uuid.UUID(point.id) >= lower_bound
            ),
            len(matching),
        )
        fetched = matching[start : start + limit + 1]
        page = fetched[:limit]
        next_offset = fetched[limit].id if len(fetched) > limit else None
        if self.empty_page_at is not None and offset == self.empty_page_at:
            return [], matching[start + 1].id
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


def unexpected_call(*args, **kwargs):
    raise AssertionError("the paging tests do not exercise this helper")


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
        # 0.11.4 imports these for search() and inserts, which no test here calls.
        stub_module(
            "open_webui.retrieval.vector.utils",
            iter_filter_conditions=unexpected_call,
            process_metadata=unexpected_call,
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

    def call_with_one_guard_warning(self, name: str, call, reason: str, count: int):
        """Run call and check that it logs exactly one guard warning."""
        scrolled = {
            self.qdrant.__name__: "open-webui_file-abc",
            self.multitenancy.__name__: "open-webui_files",
        }[name]
        with self.assertLogs(name, "WARNING") as logs:
            result = call()
        self.assertEqual(len(logs.records), 1, logs.output)
        record = logs.records[0]
        self.assertEqual(
            (record.levelname, record.args), ("WARNING", (scrolled, reason, count))
        )
        self.assertNotIn("chunk", record.getMessage())  # no point payloads
        return result

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
                        with self.assertNoLogs(name, "WARNING"):
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
                    with self.assertNoLogs(name, "WARNING"):
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

    def test_scroll_stops_and_warns_when_qdrant_repeats_its_offset(self):
        for name, client in self.clients():
            for method, call in (
                ("get", lambda: client.get("file-abc")),
                ("query", lambda: client.query("file-abc", {"hash": "h"})),
                ("query limit", lambda: client.query("file-abc", {"hash": "h"}, limit=5000)),
            ):
                with self.subTest(client=name, method=method):
                    # The second page reports offset 1000 again instead of 2000.
                    client.client.load(2500, repeat_offset_at=1000)
                    result = self.call_with_one_guard_warning(
                        name, call, "repeated offset", 2000
                    )
                    self.assertIsNotNone(result)
                    self.assertEqual(
                        result.ids,
                        [[point.id for point in client.client.points[:2000]]],
                    )
                    self.assertEqual(client.client.limits, [1000, 1000])
            with self.subTest(client=name, method="query reaching its limit"):
                # Reaching the caller limit ends paging normally, without a warning.
                client.client.load(2500, repeat_offset_at=1000)
                with self.assertNoLogs(name, "WARNING"):
                    result = client.query("file-abc", {"hash": "h"}, limit=2000)
                self.assertIsNotNone(result)
                self.assertEqual(
                    result.ids, [[point.id for point in client.client.points[:2000]]]
                )
                self.assertEqual(client.client.limits, [1000, 1000])

    def test_scroll_stops_and_warns_on_empty_page_with_next_offset(self):
        for name, client in self.clients():
            for method, call in (
                ("get", lambda: client.get("file-abc")),
                ("query", lambda: client.query("file-abc", {"hash": "h"})),
                ("query limit", lambda: client.query("file-abc", {"hash": "h"}, limit=5000)),
            ):
                with self.subTest(client=name, method=method):
                    # The third page is empty but still reports a next offset.
                    client.client.load(2500, empty_page_at=2000)
                    result = self.call_with_one_guard_warning(
                        name, call, "empty page", 2000
                    )
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

    def test_filtered_reads_return_exactly_the_matching_points(self):
        # Every third point has another tenant and every fifth another hash.
        # Each read matches more than 1,000 points, so the page boundary falls
        # inside the matching set, and a filtered read skips nonmatching points
        # on both pages.
        count = 1999
        same_tenant = [index % 3 != 1 for index in range(count)]
        same_hash = [index % 5 != 2 for index in range(count)]
        matches = {
            (self.qdrant.__name__, "get"): [True] * count,
            (self.qdrant.__name__, "query"): same_hash,
            (self.multitenancy.__name__, "get"): same_tenant,
            (self.multitenancy.__name__, "query"): [
                tenant and hash_ for tenant, hash_ in zip(same_tenant, same_hash)
            ],
        }
        for name, client in self.clients():
            for method, call, limit, limits in (
                ("get", lambda: client.get("file-abc"), None, [1000, 1000]),
                ("query", lambda: client.query("file-abc", {"hash": "h"}), None, [1000, 1000]),
                (
                    "query",
                    lambda: client.query("file-abc", {"hash": "h"}, limit=1500),
                    1500,
                    [1000, 500],
                ),
            ):
                with self.subTest(client=name, method=method, limit=limit):
                    client.client.load(count)
                    for point, tenant, hash_ in zip(
                        client.client.points, same_tenant, same_hash
                    ):
                        if not tenant:
                            point.payload["tenant_id"] = "file-xyz"
                        if not hash_:
                            point.payload["metadata"]["hash"] = "x"
                    matching = [
                        point.id
                        for point, match in zip(client.client.points, matches[name, method])
                        if match
                    ]
                    with self.assertNoLogs(name, "WARNING"):
                        result = call()
                    self.assertIsNotNone(result)
                    self.assertEqual(result.ids, [matching[:limit]])
                    # Qdrant's limit counts matching points, and the second page
                    # starts at the 1001st of them.
                    self.assertEqual(client.client.limits, limits)
                    self.assertEqual(client.client.offsets, [None, matching[1000]])


if __name__ == "__main__":
    unittest.main()
