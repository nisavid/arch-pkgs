"""Run byte-bound ingestion/authorization/deletion bodies with local provider fakes."""
import ast
import asyncio
import copy
import hashlib
import logging
import re
import shutil
import subprocess
import types
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from tests.open_webui_household_source_fixture import materialize_exact_open_webui_source
from tests.test_open_webui_qdrant_paging import AnyModels, PRISTINE_CLIENTS, filter_matches

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/open-webui'
PATCH = PACKAGE / '0012-bind-url-collections-to-owner.patch'
ROUTER = 'backend/open_webui/routers/retrieval.py'
UTILS = 'backend/open_webui/retrieval/utils.py'
QDRANT = 'backend/open_webui/retrieval/vector/dbs/qdrant_multitenancy.py'


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


def definitions(path, names, namespace, owner=None):
    tree = ast.parse(path.read_text())
    body = tree.body
    if owner:
        body = next(n for n in body if isinstance(n, ast.ClassDef) and n.name == owner).body
    selected = []
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names:
            n = copy.deepcopy(n)
            n.decorator_list = []
            for a in ast.walk(n):
                if isinstance(a, ast.arg):
                    a.annotation = None
            n.returns = None
            selected.append(n)
    if {n.name for n in selected} != names:
        raise AssertionError(f'missing source definitions in {path}: {names}')
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), str(path), 'exec'), namespace)


class Runtime:
    def __init__(self, source):
        self.rows, self.calls = {}, []
        self.owner = NS(id='00000000-0000-0000-0000-000000000001', role='user')
        self.other = NS(id='00000000-0000-0000-0000-000000000002', role='user')
        self.config = NS(
            BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL=False,
            FILE_MAX_SIZE=None, ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER=False,
            TEXT_SPLITTER='character', CHUNK_SIZE=1000, CHUNK_OVERLAP=0,
            RAG_EMBEDDING_ENGINE='openai', RAG_EMBEDDING_MODEL='local-test',
            RAG_OPENAI_API_BASE_URL='http://embedding.invalid', RAG_OPENAI_API_KEY='',
            RAG_EMBEDDING_BATCH_SIZE=1, ENABLE_ASYNC_EMBEDDING=True,
            RAG_EMBEDDING_CONCURRENT_REQUESTS=1,
        )
        self.knowledge = NS(check_access_by_user_id=AsyncMock(return_value=False),
                            get_knowledge_by_id=AsyncMock(return_value=None))
        self.file_access = AsyncMock(return_value=False)
        self.ns = dict(
            hashlib=hashlib, re=re, asyncio=asyncio, uuid=uuid, log=logging.getLogger(__name__),
            HTTPException=HTTPException, status=NS(HTTP_403_FORBIDDEN=403, HTTP_400_BAD_REQUEST=400),
            ERROR_MESSAGES=NS(ACCESS_PROHIBITED='forbidden', DEFAULT=lambda *a: str(a)),
            Depends=lambda x: None, Query=lambda value, **kw: value,
            get_verified_user=object(), get_retrieval_config=AsyncMock(return_value=self.config),
            Knowledges=self.knowledge, has_access_to_file=self.file_access,
            ENABLE_RETRIEVAL_UNSCOPED_COLLECTIONS=False,
            _SAFE_COLLECTION_NAME_RE=re.compile(r'^[A-Za-z0-9_-]{1,255}$'),
            calculate_sha256_string=lambda s: hashlib.sha256(s.encode()).hexdigest(),
            get_content_from_url=AsyncMock(side_effect=self.content),
            YoutubeTranscriptError=type('YoutubeTranscriptError', (Exception,), {}),
            RecursiveCharacterTextSplitter=lambda **kw: NS(split_documents=lambda docs: docs),
            sanitize_text_for_db=lambda s: s, RAG_EMBEDDING_TIMEOUT=5,
            RAG_EMBEDDING_CONTENT_PREFIX='', get_embedding_function=lambda *a, **kw: self.embed,
            is_youtube_url=lambda url: 'youtube.com' in url,
            _fetch_url=AsyncMock(return_value={'kind': 'web'}),
        )
        utils_names = {'_is_safe_collection_name', 'filter_accessible_collections'}
        if 'def get_url_collection_name' in (source / UTILS).read_text():
            utils_names |= {'_url_collection_owner_prefix', 'get_url_collection_name'}
        definitions(source / UTILS, utils_names, self.ns)
        vector_ns = dict(models=AnyModels(), TENANT_ID_FIELD='tenant_id', log=logging.getLogger(__name__))
        definitions(source / QDRANT, {'_tenant_filter'}, vector_ns)
        definitions(source / QDRANT, {'_get_collection_and_tenant_id', 'delete_collection'}, vector_ns, 'QdrantClient')
        self.vector = NS(
            HASH_BASED_COLLECTION='hash-based', KNOWLEDGE_COLLECTION='knowledge',
            MEMORY_COLLECTION='memory', FILE_COLLECTION='files', WEB_SEARCH_COLLECTION='web-search',
        )
        self.vector._get_collection_and_tenant_id = types.MethodType(vector_ns['_get_collection_and_tenant_id'], self.vector)
        self.vector.delete_collection = types.MethodType(vector_ns['delete_collection'], self.vector)
        self.vector.client = NS(collection_exists=lambda **kw: True, delete=self.delete)
        self.vector.has_collection = self.has_collection
        self.vector.insert = self.insert
        self.ns['get_vector_db_client'] = lambda: self.vector
        self.ns['run_in_threadpool'] = asyncio.to_thread
        definitions(source / ROUTER, {'_validate_collection_access', 'save_docs_to_vector_db', 'process_web', 'process_url'}, self.ns)

    async def content(self, request, url):
        # A remote document cannot confer ownership via its metadata.
        return request.content, [NS(page_content=request.content, metadata={'created_by': 'loader-spoof'})]

    async def embed(self, texts, **kw):
        return [[1.0, 0.0] for _ in texts]

    def key(self, name):
        return self.vector._get_collection_and_tenant_id(name)

    def has_collection(self, collection_name):
        self.calls.append(('has', collection_name))
        return bool(self.rows.get(self.key(collection_name)))

    def insert(self, collection_name, items):
        self.calls.append(('insert', collection_name))
        self.rows.setdefault(self.key(collection_name), []).extend(items)

    def delete(self, collection_name, points_selector):
        selector = points_selector[2]['filter']
        self.calls.append(('delete', collection_name))
        for key in self.rows:
            if key[0] == collection_name and filter_matches({'tenant_id': key[1]}, selector):
                self.rows[key] = []

    async def ingest(self, user, *, name=None, content='first', overwrite=True,
                     process=True, entry='process_web', url='https://example.invalid/article'):
        request = NS(content=content, app=NS(state=NS(ef=None, main_loop=asyncio.get_running_loop())))
        kwargs = dict(process=process, user=user)
        if entry == 'process_web':
            kwargs['overwrite'] = overwrite
        return await self.ns[entry](request, NS(url=url, collection_name=name), **kwargs)


class URLCollectionOwnershipTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp, cls.source = materialize_exact_open_webui_source()
        for relative, (fixture, digest) in PRISTINE_CLIENTS.items():
            if hashlib.sha256(fixture.read_bytes()).hexdigest() != digest:
                raise AssertionError('client source fixture digest mismatch')
            target = cls.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fixture, target)
        # Apply the preceding package patches that touch these exact files.
        for patch in ('0005-require-qualified-reranking.patch',
                      '0007-keep-rag-credentials-external.patch', '0008-page-qdrant-scroll.patch',
                      '0009-authenticate-service-peers.patch'):
            subprocess.run(['git', 'apply', '--include='+ROUTER, '--include='+UTILS,
                            '--include='+QDRANT, str(PACKAGE / patch)], cwd=cls.source, check=True,
                           capture_output=True)
        cls.before = Runtime(cls.source)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-Np1', '-i', str(PATCH)],
                       cwd=cls.source, check=True, capture_output=True)
        # Parse the complete patched modules, not just extracted functions.
        for relative in (ROUTER, UTILS, QDRANT):
            compile((cls.source / relative).read_text(), relative, 'exec')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    async def asyncSetUp(self):
        self.rt = Runtime(self.source)

    async def test_original_path_replaces_other_users_data(self):
        rt = self.before
        first = await rt.ingest(rt.owner)
        second = await rt.ingest(rt.other, content='second')
        self.assertEqual(first['collection_name'], second['collection_name'])
        self.assertEqual([r['text'] for r in rt.rows[rt.key(first['collection_name'])]], ['second'])
        self.assertTrue(any(op == 'delete' for op, _ in rt.calls))

    async def test_two_users_same_url_are_isolated_for_web_and_url_dispatchers(self):
        for entry, url in [('process_web', 'https://example.invalid/article'),
                           ('process_url', 'https://example.invalid/article'),
                           ('process_url', 'https://youtube.com/watch?v=test')]:
            for name in (None, ''):
                with self.subTest(entry=entry, name=name, url=url):
                    rt = Runtime(self.source)
                    first = await rt.ingest(rt.owner, entry=entry, name=name, url=url)
                    second = await rt.ingest(rt.other, entry=entry, name=name, url=url, content='second')
                    a, b = first['collection_name'], second['collection_name']
                    self.assertNotEqual(a, b)
                    self.assertEqual(len(a), 63)
                    self.assertEqual(rt.key(a), ('hash-based', a))
                    self.assertEqual([r['text'] for r in rt.rows[rt.key(a)]], ['first'])
                    self.assertEqual([r['text'] for r in rt.rows[rt.key(b)]], ['second'])
                    self.assertEqual(rt.rows[rt.key(a)][0]['metadata']['created_by'], rt.owner.id)

    async def test_explicit_foreign_collection_cannot_overwrite_append_or_read(self):
        rt = self.rt
        name = (await rt.ingest(rt.owner))['collection_name']
        for unscoped in (False, True):
            rt.ns['ENABLE_RETRIEVAL_UNSCOPED_COLLECTIONS'] = unscoped
            for overwrite in (True, False):
                rt.calls.clear()
                with self.assertRaises(HTTPException) as error:
                    await rt.ingest(rt.other, name=name, overwrite=overwrite)
                self.assertEqual(error.exception.status_code, 403)
                self.assertEqual(rt.calls, [])
            allowed = await rt.ns['filter_accessible_collections']({name}, rt.other)
            self.assertEqual(allowed, set())
        self.assertEqual(await rt.ns['filter_accessible_collections']({name}, rt.owner), {name})

    async def test_owner_reuse_overwrite_append_and_no_processing(self):
        rt = self.rt
        name = (await rt.ingest(rt.owner))['collection_name']
        again = await rt.ingest(rt.owner, content='replacement')
        self.assertEqual(again['collection_name'], name)
        self.assertEqual([r['text'] for r in rt.rows[rt.key(name)]], ['replacement'])
        await rt.ingest(rt.owner, name=name, content='append', overwrite=False)
        self.assertEqual([r['text'] for r in rt.rows[rt.key(name)]], ['replacement', 'append'])
        rt.calls.clear()
        self.assertNotIn('collection_name', await rt.ingest(rt.other, name=name, process=False))
        self.assertEqual(rt.calls, [])
        rt.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True
        self.assertIsNone((await rt.ingest(rt.owner))['collection_name'])
        self.assertEqual(rt.calls, [])

    async def test_reserved_names_reject_malformed_variants_and_bind_complete_identity(self):
        rt = self.rt
        mint = rt.ns['get_url_collection_name']
        owner = NS(id='x'*200+'a', role='user')
        other = NS(id='x'*200+'b', role='user')
        name = mint(owner.id, 'same-url')
        self.assertEqual(len(name), 63)
        self.assertNotEqual(name, mint(other.id, 'same-url'))
        self.assertNotEqual(name, mint(owner.id, 'same-url/'))
        rt.ns['ENABLE_RETRIEVAL_UNSCOPED_COLLECTIONS'] = True
        malformed = {name+'\n', name[:-1], name+'a', name.upper(), 'url-not-an-owner'}
        self.assertEqual(await rt.ns['filter_accessible_collections'](malformed, owner), set())
        self.assertEqual(await rt.ns['filter_accessible_collections']({name}, other), set())

    async def test_backend_normalized_aliases_cannot_bypass_reserved_namespace(self):
        rt = self.rt
        name = (await rt.ingest(rt.owner))['collection_name']
        # Milvus: '-' -> '_'. Weaviate: same, strip edge '_', capitalize.
        aliases = {name.replace('-', '_'), name.replace('-', '_', 1),
                   name.capitalize(), '_' + name + '_', '-' + name + '-',
                   '_' + name.replace('-', '_').capitalize() + '_'}
        self.assertTrue(all(
            alias.replace('-', '_').strip('_')[0].upper()
            + alias.replace('-', '_').strip('_')[1:]
            == name.replace('-', '_').capitalize()
            for alias in aliases
        ))
        rt.ns['ENABLE_RETRIEVAL_UNSCOPED_COLLECTIONS'] = True
        for alias in aliases:
            with self.subTest(alias=alias):
                rt.calls.clear()
                with self.assertRaises(HTTPException) as error:
                    await rt.ingest(rt.other, name=alias)
                self.assertEqual(error.exception.status_code, 403)
                self.assertEqual(rt.calls, [])

    async def test_explicit_shared_knowledge_file_and_admin_permissions_remain(self):
        rt = self.rt
        rt.knowledge.check_access_by_user_id.side_effect = lambda name, user, permission: name == 'shared-kb' and permission == 'write'
        rt.file_access.side_effect = lambda file_id, access_type, user: file_id == 'shared-file' and access_type == 'write'
        for name in ('shared-kb', 'file-shared-file'):
            await rt.ingest(rt.owner, name=name)
            await rt.ingest(rt.other, name=name, overwrite=False)
            self.assertEqual(len(rt.rows[rt.key(name)]), 2)
        rt.knowledge.check_access_by_user_id.side_effect = None
        rt.knowledge.check_access_by_user_id.return_value = False
        rt.calls.clear()
        with self.assertRaises(HTTPException):
            await rt.ingest(rt.other, name='shared-kb')
        self.assertEqual(rt.calls, [])
        name = (await rt.ingest(rt.owner))['collection_name']
        admin = NS(id='admin', role='admin')
        await rt.ingest(admin, name=name, content='admin replacement')
        self.assertEqual([r['text'] for r in rt.rows[rt.key(name)]], ['admin replacement'])

    def test_web_and_youtube_remain_the_same_registered_handler(self):
        tree = ast.parse((self.source / ROUTER).read_text())
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'process_web')
        paths = {d.args[0].value for d in handler.decorator_list if isinstance(d, ast.Call)}
        self.assertEqual(paths, {'/process/web', '/process/youtube'})


if __name__ == '__main__':
    unittest.main()
