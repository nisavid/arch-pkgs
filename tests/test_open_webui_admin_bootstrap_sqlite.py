"""Real ORM/SQLite coverage for the package administrator insertion boundary.

Import the complete, byte-bound upstream Users/Auths modules. Only unrelated
application configuration, throttling, and image validation are isolated; SQL
queries, ORM models, inserts, commits, and upstream session contexts are real.
This is not a full installed-application or Uvicorn acceptance test.
"""
import ast
import contextlib
import importlib.util
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import JSON, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from tests.open_webui_household_source_fixture import materialize_exact_open_webui_source
from tests.test_open_webui_admin_bootstrap import PACKAGE_DIR, _materialize_supplement


def module(name):
    return types.ModuleType(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


class AdminBootstrapSQLiteTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary, source = materialize_exact_open_webui_source()
        cls.addClassCleanup(cls.temporary.cleanup)
        _materialize_supplement(source)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-Np1', '-i',
                        str(PACKAGE_DIR / '0011-require-admin-bootstrap.patch')],
                       cwd=source, check=True, capture_output=True)
        db = module('open_webui.internal.db')
        db.Base = declarative_base()
        db.JSONField = JSON  # Imported but unused by both upstream model modules.
        db.AsyncSession = AsyncSession
        db.asynccontextmanager = contextlib.asynccontextmanager
        # Execute the original session context implementations, rather than
        # replacing their reuse/closure behavior with a test double.
        tree = ast.parse((source / 'backend/open_webui/internal/db.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                 and node.name in {'get_async_db', 'get_async_db_context'}]
        assert len(nodes) == 2
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'upstream-db-contexts', 'exec'), db.__dict__)
        env = module('open_webui.env')
        env.DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL = 0
        misc = module('open_webui.utils.misc')
        misc.throttle = lambda _interval: lambda function: function
        validate = module('open_webui.utils.validate')
        validate.validate_image_url = lambda value: value
        isolated = {name: module(name) for name in (
            'open_webui', 'open_webui.models', 'open_webui.internal', 'open_webui.utils')}
        isolated.update({db.__name__: db, env.__name__: env,
                         misc.__name__: misc, validate.__name__: validate})
        cls.modules = mock.patch.dict(sys.modules, isolated)
        cls.modules.start()
        cls.addClassCleanup(cls.modules.stop)
        cls.db = db
        cls.users = load('open_webui.models.users', source / 'backend/open_webui/models/users.py')
        cls.auths = load('open_webui.models.auths', source / 'backend/open_webui/models/auths.py')

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine('sqlite+aiosqlite:///' + str(Path(self.directory.name) / 'users.db'))
        self.db.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, autoflush=False, expire_on_commit=False)
        self.db.DATABASE_ENABLE_SESSION_SHARING = True
        async with self.engine.begin() as connection:
            await connection.run_sync(self.db.Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.directory.cleanup()

    async def counts(self):
        # Observe persisted state from a separate session, not returned models.
        async with self.db.AsyncSessionLocal() as session:
            counts = []
            for table in (self.users.User, self.auths.Auth):
                result = await session.execute(select(func.count()).select_from(table))
                counts.append(result.scalar_one())
            return tuple(counts)

    async def seed(self, role):
        # Trusted fixture setup uses the real User DAL, like bearer-authorized
        # provisioning. It deliberately creates no authentication row.
        return await self.users.Users.insert_new_user('seed', 'Existing', 'seed@example.invalid', role=role)

    async def test_empty_database_rejects_ordinary_insert_without_persisted_rows(self):
        for shared in (False, True):
            with self.subTest(session_sharing=shared):
                self.db.DATABASE_ENABLE_SESSION_SHARING = shared
                async with self.db.AsyncSessionLocal() as session:
                    result = await self.auths.Auths.insert_new_auth(
                        'remote@example.invalid', 'hash', 'Remote', db=session)
                    self.assertIsNone(result)
                    self.assertEqual(list(session.new), [])
                self.assertEqual(await self.counts(), (0, 0))

    async def test_pending_only_database_rejects_even_requested_admin_role(self):
        await self.seed('pending')
        self.assertIsNone(await self.users.Users.get_super_admin_user())
        self.assertTrue(await self.users.Users.has_users())
        for shared in (False, True):
            with self.subTest(session_sharing=shared):
                self.db.DATABASE_ENABLE_SESSION_SHARING = shared
                async with self.db.AsyncSessionLocal() as session:
                    result = await self.auths.Auths.insert_new_auth(
                        'remote@example.invalid', 'hash', 'Remote', role='admin', db=session)
                    self.assertIsNone(result)
                    self.assertEqual(list(session.new), [])
                self.assertEqual(await self.counts(), (1, 0))

    async def test_admin_present_preserves_normal_insert_and_auth_linkage(self):
        await self.seed('admin')
        for shared in (False, True):
            with self.subTest(session_sharing=shared):
                self.db.DATABASE_ENABLE_SESSION_SHARING = shared
                email = f'user-{shared}@example.invalid'
                async with self.db.AsyncSessionLocal() as session:
                    user = await self.auths.Auths.insert_new_auth(email, 'stored-hash', 'Household', db=session)
                self.assertEqual(user.role, 'pending')
                async with self.db.AsyncSessionLocal() as observer:
                    stored_user = await observer.get(self.users.User, user.id)
                    stored_auth = await observer.get(self.auths.Auth, user.id)
                    self.assertEqual((stored_user.email, stored_user.role), (email, 'pending'))
                    self.assertEqual((stored_auth.email, stored_auth.password, stored_auth.active),
                                     (email, 'stored-hash', True))
        self.assertEqual(await self.counts(), (3, 2))

    async def test_initial_admin_requires_empty_database_and_persists_both_rows(self):
        self.assertIsNone(await self.auths.Auths.insert_new_auth(
            'wrong@example.invalid', 'hash', 'Wrong', role='pending', initial_admin=True))
        self.assertEqual(await self.counts(), (0, 0))
        admin = await self.auths.Auths.insert_new_auth(
            'admin@example.invalid', 'bootstrap-hash', 'Administrator', role='admin', initial_admin=True)
        self.assertEqual(await self.counts(), (1, 1))
        persisted = await self.users.Users.get_super_admin_user()
        self.assertEqual((persisted.id, persisted.email, persisted.role),
                         (admin.id, 'admin@example.invalid', 'admin'))
        self.assertIsNone(await self.auths.Auths.insert_new_auth(
            'second@example.invalid', 'hash', 'Second', role='admin', initial_admin=True))
        self.assertEqual(await self.counts(), (1, 1))

    async def test_initial_admin_cannot_replace_nonadmin_only_database(self):
        await self.seed('pending')
        self.assertIsNone(await self.auths.Auths.insert_new_auth(
            'admin@example.invalid', 'hash', 'Administrator', role='admin', initial_admin=True))
        self.assertEqual(await self.counts(), (1, 0))
