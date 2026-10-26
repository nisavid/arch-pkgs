"""Exercise the package's first-admin boundary without importing the app stack."""

import ast
import asyncio
import contextlib
import copy
import hashlib
import inspect
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
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
FIXTURE = (
    REPO_ROOT / "tools/fixtures/open-webui-household"
    / "open-webui-0.11.4-pristine-admin-bootstrap.tar.gz"
)
FIXTURE_SHA256 = "bfc9b408144a5ba687bdead9c104a30962934c1605b4250bbea41baf0d7d8af5"
OPEN_WEBUI_COMMIT = "8bd8b4fac5e059578ac0c74b3c18d11139f88b7d"
OPEN_WEBUI_SDIST_SHA256 = (
    "1f1a31668a0dee733953c29d6183d78dd78984e696aa8eb0f2083f5796497be0"
)
# Supplemental fixture: these four byte-exact files come from the SHA256-verified
# 0.11.4 sdist pinned by PKGBUILD above. The existing patch-preimages bundle is
# retained unchanged. Regenerate this bundle using Python tarfile GNU_FORMAT:
# sorted files and parent directories, uid/gid/mtime 0, empty uname/gname,
# file mode 0644, directory mode 0755; gzip.GzipFile(filename='', mtime=0,
# compresslevel=6). The hashes also independently bind each extracted file.
SOURCE_HASHES = {
    "backend/open_webui/models/users.py":
        "95b114836c90096d70939df96aa93a4a372190be77abbb7b6a3713ced92e7bc5",
    "backend/open_webui/internal/db.py":
        "be9c668ef7931249d20ede563dc9fa0a646cfefa5c9f39ff557d64b78d28b284",
    "backend/open_webui/models/auths.py":
        "5248a142249bee1dc9e92b2e876e32a162fec3633c69ed210c7f806bc6176b1e",
    "backend/open_webui/routers/auths.py":
        "4be0ed8e69bba85c0392fdddf006efe5592c322a4973c669120a0a0c3c2424c7",
}
PATCH = PACKAGE_DIR / "0011-require-admin-bootstrap.patch"
ADMIN_ENV = ("WEBUI_ADMIN_EMAIL", "WEBUI_ADMIN_NAME", "WEBUI_ADMIN_PASSWORD")
ADMIN_CREDENTIALS = {
    "admin-email": "Admin@Example.invalid",
    "admin-name": "Household Administrator",
    "admin-bootstrap-password": "synthetic-bootstrap-password",
}
STABLE_CREDENTIALS = {
    "webui-secret-key": "synthetic-signing-key",
    "oauth-client-info-encryption-key": "synthetic-client-encryption-key",
    "oauth-session-token-encryption-key": "synthetic-session-encryption-key",
    "valkey-url": "redis://synthetic.invalid/0",
    "qdrant-runtime-api-key": "synthetic-vector-key",
}


def _materialize_supplement(source_root):
    if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != FIXTURE_SHA256:
        raise RuntimeError("Open WebUI admin-bootstrap fixture digest mismatch")
    expected = set(SOURCE_HASHES)
    for name in SOURCE_HASHES:
        expected.update(str(parent) for parent in Path(name).parents if str(parent) != ".")
    with tarfile.open(FIXTURE, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(expected) or {member.name for member in members} != expected:
            raise RuntimeError("Open WebUI admin-bootstrap fixture member set mismatch")
        if any(
            not (member.isfile() if member.name in SOURCE_HASHES else member.isdir())
            for member in members
        ):
            raise RuntimeError("Open WebUI admin-bootstrap fixture contains an unsafe member")
        archive.extractall(source_root, filter="data")
    for name, digest in SOURCE_HASHES.items():
        if hashlib.sha256((source_root / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Open WebUI fixture source digest mismatch: {name}")


def _function(path, name, namespace, owner=None):
    """Compile the real function body; replace only imports/types/decorators."""
    parsed = ast.parse(path.read_text(encoding="utf-8"))
    body = parsed.body
    if owner:
        body = next(node for node in body if isinstance(node, ast.ClassDef) and node.name == owner).body
    node = copy.deepcopy(next(node for node in body if isinstance(node, ast.AsyncFunctionDef) and node.name == name))
    node.decorator_list = []
    node.returns = None
    for item in ast.walk(node):
        if isinstance(item, ast.arg):
            item.annotation = None
    exec(  # noqa: S102 - byte-bound upstream source under isolated dependencies
        compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), "exec"),
        namespace,
    )
    return namespace[name]


class _Session:
    def __init__(self):
        self.credentials = []
        self.users = []
        self.writes = []

    def add(self, credential):
        self.credentials.append(credential)
        self.writes.append("credential.add")

    async def commit(self):
        self.writes.append("commit")

    async def rollback(self):
        self.writes.append("rollback")


class _DBContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


class _Users:
    def __init__(self, session):
        self.session = session
        self.calls = []
        self.admin_lookup_error = None
        self.has_users_error = None

    async def get_super_admin_user(self, db=None):
        self.calls.append(("get_super_admin_user", db))
        if self.admin_lookup_error:
            raise self.admin_lookup_error
        return next((user for user in self.session.users if user.role == "admin"), None)

    async def has_users(self, db=None):
        self.calls.append(("has_users", db))
        if self.has_users_error:
            raise self.has_users_error
        return bool(self.session.users)

    async def insert_new_user(self, user_id, name, email, image, role, *, oauth, db):
        if db is not self.session:
            raise AssertionError("User and auth inserts must share the checked session")
        self.session.writes.append("user.insert")
        user = SimpleNamespace(id=user_id, name=name, email=email, profile_image_url=image, role=role, oauth=oauth)
        self.session.users.append(user)
        return user

    async def get_num_users(self, db=None):
        return len(self.session.users)

    async def update_user_role_by_id(self, user_id, role, db=None):
        self.session.writes.append("user.promote")
        user = await self.get_user_by_id(user_id, db=db)
        user.role = role

    async def get_user_by_id(self, user_id, db=None):
        return next((user for user in self.session.users if user.id == user_id), None)

    async def get_user_by_email(self, email, db=None):
        return next((user for user in self.session.users if user.email == email), None)


class _Config:
    def __init__(self):
        self.values = {
            "ui.default_user_role": "pending", "ui.enable_signup": True,
            "ui.enable_login_form": True, "ui.default_group_id": None,
        }
        self.writes = []

    async def get(self, name, default=None):
        return self.values.get(name, default)

    async def upsert(self, values):
        self.writes.append(dict(values))
        self.values.update(values)


class _HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code


class _Runtime:
    def __init__(self, source):
        self.session = _Session()
        self.users = _Users(self.session)
        self.config = _Config()
        self.uuid4 = mock.Mock(return_value="synthetic-new-user-id")
        self.hash_password = mock.AsyncMock(return_value="synthetic-password-hash")
        self.publish = mock.AsyncMock()
        self.groups = mock.AsyncMock()
        self.namespace = {
            "Users": self.users, "Config": self.config, "Auth": SimpleNamespace,
            "uuid": SimpleNamespace(uuid4=self.uuid4), "log": mock.Mock(),
            "get_async_db_context": self.context, "IntegrityError": type("IntegrityError", (Exception,), {}),
            "get_password_hash": self.hash_password, "HTTPException": _HTTPException,
            "ERROR_MESSAGES": SimpleNamespace(CREATE_USER_ERROR="create-user-error", ACCESS_PROHIBITED="access-prohibited", INVALID_EMAIL_FORMAT="invalid-email", EMAIL_TAKEN="email-taken"),
            "EVENTS": SimpleNamespace(USER_CREATED="user-created", AUTH_SIGNUP="auth-signup"),
            "publish_event": self.publish, "apply_default_group_assignment": self.groups,
            "create_session_response": mock.AsyncMock(return_value="session-response"),
            "validate_email_format": lambda _email: True,
            "validate_password": lambda _password: True,
            "WEBUI_AUTH": True, "ENABLE_INITIAL_ADMIN_SIGNUP": True,
            "Depends": lambda *_args: None, "get_async_session": None,
            "status": SimpleNamespace(HTTP_403_FORBIDDEN=403, HTTP_400_BAD_REQUEST=400),
        }
        method = _function(source / "backend/open_webui/models/auths.py", "insert_new_auth", self.namespace, owner="AuthsTable")
        self.auths = SimpleNamespace(insert_new_auth=types.MethodType(method, SimpleNamespace()))
        self.namespace["Auths"] = self.auths
        self.create_admin = _function(source / "backend/open_webui/utils/auth.py", "create_admin_user", self.namespace)
        _function(source / "backend/open_webui/routers/auths.py", "signup_handler", self.namespace)
        self.signup = _function(source / "backend/open_webui/routers/auths.py", "signup", self.namespace)

    def context(self, db=None):
        if db is not None and db is not self.session:
            raise AssertionError("Unexpected database session")
        return _DBContext(self.session)

    def existing_user(self, role):
        user = SimpleNamespace(id=f"existing-{role}", email=f"{role}@example.invalid", name="Existing", role=role)
        self.session.users.append(user)
        return user


class AdminBootstrapSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary, cls.source = materialize_exact_open_webui_source()
        cls.addClassCleanup(cls.temporary.cleanup)
        _materialize_supplement(cls.source)
        cls.pristine_temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.pristine_temporary.cleanup)
        cls.pristine = Path(cls.pristine_temporary.name)
        shutil.copytree(cls.source, cls.pristine, dirs_exist_ok=True)
        cls.patch_results = []
        for name, cwd in (
            ("0005-require-qualified-reranking.patch", cls.source),
            ("0006-enforce-session-epoch.patch", cls.source / "backend"),
            ("0007-keep-rag-credentials-external.patch", cls.source),
            (PATCH.name, cls.source),
        ):
            result = subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-Np1", "-i", str(PACKAGE_DIR / name)],
                cwd=cwd, text=True, capture_output=True, timeout=30, check=False,
            )
            cls.patch_results.append(result)
            if result.returncode:
                raise RuntimeError(f"{name} did not apply exactly:\n{result.stdout}{result.stderr}")

    def setUp(self):
        self.runtime = _Runtime(self.source)

    def assert_no_writes(self):
        self.assertEqual(self.runtime.session.writes, [])
        self.assertEqual(self.runtime.session.credentials, [])
        self.assertEqual(self.runtime.config.writes, [])
        self.runtime.uuid4.assert_not_called()

    def test_exact_bound_patch_applies_after_household_patches_and_compiles(self):
        patch = PATCH.read_text(encoding="utf-8")
        self.assertIn(f"X-Open-WebUI-Commit: {OPEN_WEBUI_COMMIT}", patch)
        self.assertIn(f"X-Open-WebUI-Sdist-SHA256: {OPEN_WEBUI_SDIST_SHA256}", patch)
        self.assertEqual([result.returncode for result in self.patch_results], [0, 0, 0, 0])
        for relative in (*SOURCE_HASHES, "backend/open_webui/utils/auth.py", "backend/open_webui/main.py"):
            compile((self.source / relative).read_text(encoding="utf-8"), relative, "exec")

    def test_pristine_upstream_reproduces_first_signup_becoming_administrator(self):
        runtime = _Runtime(self.pristine)
        form = SimpleNamespace(email="Remote@Example.invalid", password="remote-secret", name="Remote", profile_image_url="/user.png")
        result = asyncio.run(runtime.signup(SimpleNamespace(), SimpleNamespace(), form, runtime.session))
        self.assertEqual(result, "session-response")
        self.assertEqual([user.role for user in runtime.session.users], ["admin"])
        self.assertIn("user.promote", runtime.session.writes)

    def test_ordinary_insert_rejects_empty_or_nonadmin_only_database_before_staging(self):
        for existing in (None, "pending", "user"):
            for requested_role in ("pending", "admin"):
                with self.subTest(existing=existing, requested_role=requested_role):
                    self.runtime = _Runtime(self.source)
                    if existing:
                        self.runtime.existing_user(existing)
                    before = list(self.runtime.session.users)
                    result = asyncio.run(self.runtime.auths.insert_new_auth("remote@example.invalid", "hash", "Remote", role=requested_role, db=self.runtime.session))
                    self.assertIsNone(result)
                    self.assertEqual(self.runtime.session.users, before)
                    self.assertEqual(self.runtime.users.calls, [("get_super_admin_user", self.runtime.session)])
                    self.assert_no_writes()

    def test_admin_lookup_exception_fails_closed_without_staging(self):
        self.runtime.users.admin_lookup_error = RuntimeError("database lookup failed")
        with self.assertRaisesRegex(RuntimeError, "database lookup failed"):
            asyncio.run(self.runtime.auths.insert_new_auth("remote@example.invalid", "hash", "Remote", db=self.runtime.session))
        self.assert_no_writes()

    def test_initialized_database_preserves_all_existing_positional_call_arguments(self):
        self.runtime.existing_user("admin")
        oauth = {"provider": "synthetic"}
        user = asyncio.run(self.runtime.auths.insert_new_auth("new@example.invalid", "hash", "New", "/profile.png", "user", oauth, self.runtime.session))
        self.assertEqual((user.email, user.role, user.profile_image_url, user.oauth), ("new@example.invalid", "user", "/profile.png", oauth))
        self.assertEqual(self.runtime.users.calls, [("get_super_admin_user", self.runtime.session)])
        self.assertEqual(self.runtime.session.writes, ["credential.add", "user.insert", "commit"])
        signature = inspect.signature(self.runtime.auths.insert_new_auth)
        self.assertEqual(signature.parameters["initial_admin"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(signature.parameters["initial_admin"].default, False)

    def test_initial_admin_opt_in_requires_admin_role_and_no_existing_users(self):
        for existing, role in ((None, "pending"), (None, "user"), ("pending", "admin"), ("user", "admin"), ("admin", "admin")):
            with self.subTest(existing=existing, role=role):
                self.runtime = _Runtime(self.source)
                if existing:
                    self.runtime.existing_user(existing)
                before = list(self.runtime.session.users)
                result = asyncio.run(self.runtime.auths.insert_new_auth("admin@example.invalid", "hash", "Admin", role=role, db=self.runtime.session, initial_admin=True))
                self.assertIsNone(result)
                self.assertEqual(self.runtime.session.users, before)
                self.assert_no_writes()

    def test_initial_admin_empty_database_check_failure_does_not_stage_rows(self):
        self.runtime.users.has_users_error = RuntimeError("database lookup failed")
        with self.assertRaisesRegex(RuntimeError, "database lookup failed"):
            asyncio.run(self.runtime.auths.insert_new_auth("admin@example.invalid", "hash", "Admin", role="admin", db=self.runtime.session, initial_admin=True))
        self.assertEqual(self.runtime.users.calls, [("has_users", self.runtime.session)])
        self.assert_no_writes()

    def test_complete_credentials_create_exactly_one_initial_administrator(self):
        user = asyncio.run(self.runtime.create_admin("Admin@Example.invalid", "protected-password", "Administrator"))
        self.assertEqual((user.email, user.role, user.name), ("admin@example.invalid", "admin", "Administrator"))
        self.runtime.hash_password.assert_awaited_once_with("protected-password")
        self.assertEqual(self.runtime.session.writes, ["credential.add", "user.insert", "commit"])
        self.assertEqual(self.runtime.users.calls, [("has_users", None), ("has_users", self.runtime.session)])
        self.assertEqual(self.runtime.session.credentials[0].password, "synthetic-password-hash")

    def test_incomplete_or_existing_database_bootstrap_does_not_hash_or_write(self):
        for email, password, existing in (("", "password", None), ("admin@example.invalid", "", None), ("admin@example.invalid", "password", "pending"), ("admin@example.invalid", "password", "admin")):
            with self.subTest(email=email, password=bool(password), existing=existing):
                self.runtime = _Runtime(self.source)
                if existing:
                    self.runtime.existing_user(existing)
                self.assertIsNone(asyncio.run(self.runtime.create_admin(email, password)))
                self.runtime.hash_password.assert_not_awaited()
                self.assert_no_writes()

    def test_real_signup_endpoint_cannot_promote_a_remote_first_account(self):
        for existing in (None, "pending"):
            for default_role in ("pending", "admin"):
                with self.subTest(existing=existing, default_role=default_role):
                    self.runtime = _Runtime(self.source)
                    if existing:
                        self.runtime.existing_user(existing)
                    self.runtime.config.values["ui.default_user_role"] = default_role
                    form = SimpleNamespace(email="Remote@Example.invalid", password="remote-secret", name="Remote", profile_image_url="/user.png")
                    with self.assertRaises(_HTTPException) as error:
                        asyncio.run(self.runtime.signup(SimpleNamespace(), SimpleNamespace(), form, self.runtime.session))
                    self.assertEqual(error.exception.status_code, 500)
                    self.runtime.groups.assert_not_awaited()
                    self.runtime.publish.assert_not_awaited()
                    self.runtime.namespace["create_session_response"].assert_not_awaited()
                    self.assert_no_writes()

    def test_real_signup_still_adds_a_pending_user_when_an_admin_exists(self):
        self.runtime.existing_user("admin")
        form = SimpleNamespace(email="New@Example.invalid", password="new-secret", name="New", profile_image_url="/user.png")
        self.assertEqual(asyncio.run(self.runtime.signup(SimpleNamespace(), SimpleNamespace(), form, self.runtime.session)), "session-response")
        self.assertEqual([user.role for user in self.runtime.session.users], ["admin", "pending"])
        self.assertNotIn("user.promote", self.runtime.session.writes)

    def _lifespan(self, *, email="", password="", name="Administrator", hash_error=None):
        namespace = dict(self.runtime.namespace)
        namespace.update({
            "asyncio": asyncio, "THREAD_POOL_SIZE": 0, "INSTANCE_ID": "test-instance",
            "start_logger": mock.Mock(), "RESET_CONFIG_ON_START": False,
            "LICENSE_KEY": "", "WEBUI_ADMIN_EMAIL": email,
            "WEBUI_ADMIN_PASSWORD": password, "WEBUI_ADMIN_NAME": name,
            "SAFE_MODE": False, "get_redis_client": mock.Mock(return_value=None),
            "WEBSOCKET_MANAGER": "", "REDIS_TASK_TTL": 0,
            "EVENTS": SimpleNamespace(SYSTEM_STARTUP_STARTED="starting", SYSTEM_STARTUP_COMPLETED="ready", SYSTEM_SHUTDOWN_STARTED="stopping", SYSTEM_SHUTDOWN_COMPLETED="stopped"),
        })
        for name in ("import_legacy_config_json", "seed_registered_defaults", "initialize_runtime_config", "migrate_legacy_webhook_config", "install_tool_and_function_dependencies", "periodic_usage_pool_cleanup", "periodic_session_pool_cleanup"):
            namespace[name] = mock.AsyncMock()
        if hash_error:
            self.runtime.hash_password.side_effect = hash_error
        automations = types.ModuleType("open_webui.utils.automations")
        automations.scheduler_worker_loop = mock.AsyncMock()
        session_pool = types.ModuleType("open_webui.utils.session_pool")
        session_pool.close_session = mock.AsyncMock()
        lifecycle = _function(self.source / "backend/open_webui/main.py", "lifespan", namespace)
        app = SimpleNamespace(state=SimpleNamespace(startup_complete=False))

        async def run():
            with mock.patch.dict(sys.modules, {"open_webui.utils.automations": automations, "open_webui.utils.session_pool": session_pool}):
                async with contextlib.asynccontextmanager(lifecycle)(app):
                    self.assertTrue(app.state.startup_complete)
            return app

        return run, app, namespace

    def test_lifespan_rejects_empty_and_nonadmin_databases_before_readiness_or_workers(self):
        for existing in (None, "pending", "user"):
            with self.subTest(existing=existing):
                self.runtime = _Runtime(self.source)
                if existing:
                    self.runtime.existing_user(existing)
                run, app, namespace = self._lifespan()
                with self.assertRaisesRegex(RuntimeError, "requires an administrator"):
                    asyncio.run(run())
                self.assertFalse(app.state.startup_complete)
                namespace["install_tool_and_function_dependencies"].assert_not_awaited()
                namespace["get_redis_client"].assert_not_called()
                self.assertFalse(hasattr(app.state, "scheduler_worker_loop"))
                self.assert_no_writes()

    def test_lifespan_admin_lookup_exception_fails_before_readiness(self):
        self.runtime.users.admin_lookup_error = RuntimeError("database lookup failed")
        run, app, namespace = self._lifespan()
        with self.assertRaisesRegex(RuntimeError, "database lookup failed"):
            asyncio.run(run())
        self.assertFalse(app.state.startup_complete)
        namespace["get_redis_client"].assert_not_called()
        self.assert_no_writes()

    def test_lifespan_accepts_commissioned_restart_without_bootstrap_inputs(self):
        self.runtime.existing_user("admin")
        run, app, _namespace = self._lifespan()
        asyncio.run(run())
        self.assertTrue(app.state.startup_complete)
        self.runtime.hash_password.assert_not_awaited()
        self.assertEqual(self.runtime.users.calls, [("get_super_admin_user", None)])
        self.assert_no_writes()

    def test_lifespan_bootstraps_before_guard_and_closes_signup(self):
        run, app, _namespace = self._lifespan(email="Admin@Example.invalid", password="protected-password")
        asyncio.run(run())
        self.assertTrue(app.state.startup_complete)
        self.assertEqual([user.role for user in self.runtime.session.users], ["admin"])
        self.assertEqual(self.runtime.config.writes, [{"ui.enable_signup": False}])
        self.assertEqual(self.runtime.users.calls[-1], ("get_super_admin_user", None))

    def test_failed_or_partial_bootstrap_never_reaches_lifespan_yield(self):
        for email, password, error in (("admin@example.invalid", "", None), ("", "password", None), ("admin@example.invalid", "password", RuntimeError("hash failed"))):
            with self.subTest(email=bool(email), password=bool(password), error=error):
                self.runtime = _Runtime(self.source)
                run, app, namespace = self._lifespan(email=email, password=password, hash_error=error)
                with self.assertRaisesRegex(RuntimeError, "requires an administrator"):
                    asyncio.run(run())
                self.assertFalse(app.state.startup_complete)
                namespace["get_redis_client"].assert_not_called()
                self.assert_no_writes()


class AdminBootstrapWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.credentials = self.root / "credentials"
        self.credentials.mkdir()
        for name, value in STABLE_CREDENTIALS.items():
            (self.credentials / name).write_text(value, encoding="utf-8")
        modules = self.root / "modules"
        modules.mkdir()
        (modules / "open_webui_service_tls.py").write_text("def configure_or_exit(): pass\n", encoding="utf-8")
        (modules / "open_webui.py").write_text(
            "import json, os\n"
            "def app():\n"
            f"    print(json.dumps({{name: os.environ.get(name) for name in {ADMIN_ENV!r}}}))\n",
            encoding="utf-8",
        )
        self.environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "CREDENTIALS_DIRECTORY": str(self.credentials), "PYTHONPATH": str(modules)}
        # The test host need not provide Arch's /usr/bin/python. Redirect only
        # that final executable; the real POSIX wrapper's credential logic and
        # Python -c entrypoint are retained and run by /bin/sh.
        self.wrapper = self.root / "open-webui-wrapper"
        self.wrapper.write_text(
            (PACKAGE_DIR / "open-webui-wrapper").read_text(encoding="utf-8").replace("/usr/bin/python", shlex.quote(sys.executable)),
            encoding="utf-8",
        )

    def _snapshot(self):
        result = {}
        for path in self.credentials.iterdir():
            result[path.name] = ("symlink", os.readlink(path)) if path.is_symlink() else ("file", path.read_bytes())
        return result, (PACKAGE_DIR / "open-webui-wrapper").read_bytes(), PATCH.read_bytes()

    def _run(self, ambient=True):
        before = self._snapshot()
        environment = dict(self.environment)
        if ambient:
            environment.update(dict(zip(ADMIN_ENV, ("Ambient@Example.invalid", "Ambient Admin", "ambient-secret"))))
        result = subprocess.run(["/bin/sh", str(self.wrapper)], env=environment, text=True, capture_output=True, timeout=20, check=False)
        self.assertEqual(self._snapshot(), before, "wrapper rejection/launch must not modify sources or credentials")
        return result

    def _assert_rejected(self, result):
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertEqual(result.stdout, "", "Python app entrypoint must not be reached")
        for value in (*ADMIN_CREDENTIALS.values(), *STABLE_CREDENTIALS.values(), "ambient-secret"):
            self.assertNotIn(value, result.stderr)

    def test_ambient_admin_values_are_removed_without_protected_bootstrap_credentials(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), dict.fromkeys(ADMIN_ENV))

    def test_complete_protected_credentials_replace_ambient_values(self):
        for name, value in ADMIN_CREDENTIALS.items():
            (self.credentials / name).write_text(value, encoding="utf-8")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), dict(zip(ADMIN_ENV, ADMIN_CREDENTIALS.values())))

    def test_any_partial_admin_credential_set_rejects_even_with_ambient_values(self):
        for name, value in ADMIN_CREDENTIALS.items():
            with self.subTest(credential=name):
                path = self.credentials / name
                path.write_text(value, encoding="utf-8")
                self._assert_rejected(self._run())
                path.unlink()

    def test_dangling_admin_credential_symlink_counts_as_partial_bootstrap(self):
        for name in ADMIN_CREDENTIALS:
            with self.subTest(credential=name):
                path = self.credentials / name
                path.symlink_to(self.credentials / "missing-target")
                self._assert_rejected(self._run())
                path.unlink()

    def test_empty_admin_credential_rejects_complete_bootstrap(self):
        for name, value in ADMIN_CREDENTIALS.items():
            (self.credentials / name).write_text(value, encoding="utf-8")
        (self.credentials / "admin-bootstrap-password").write_text("", encoding="utf-8")
        self._assert_rejected(self._run())


if __name__ == "__main__":
    unittest.main()
