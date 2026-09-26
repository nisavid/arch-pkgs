import contextlib
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import socketserver
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
OPEN_WEBUI = REPO_ROOT / "packages" / "open-webui"
RAPIDOCR = REPO_ROOT / "packages" / "python-rapidocr"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class OpenWebUIPackageContractTests(unittest.TestCase):
    def test_recipe_binds_exact_release_and_frozen_closures(self):
        recipe = read(OPEN_WEBUI / "PKGBUILD")

        self.assertIn("pkgver=0.11.4", recipe)
        self.assertIn(
            "1f1a31668a0dee733953c29d6183d78dd78984e696aa8eb0f2083f5796497be0",
            recipe,
        )
        self.assertIn(
            "e4c2b02607ae984ec8ec08f3f9e02a8de06b1226af0f2df37fe2fab7f9d52523",
            recipe,
        )
        self.assertIn("open-webui-private-requirements.lock", recipe)
        self.assertIn('python "${srcdir}/verify-open-webui-private-lock.py"', recipe)
        self.assertNotIn("'SKIP'", recipe)
        self.assertEqual(recipe.count("patch --fuzz=0"), 8)
        for provenance_asset in (
            "open-webui-private-constraints.txt",
            "open-webui-system-providers.txt",
            "generate-open-webui-private-lock.zsh",
            "verify-open-webui-private-lock.py",
        ):
            self.assertIn(provenance_asset, recipe)
        self.assertIn("'python-packaging'", recipe)
        for asset in (
            "0005-require-qualified-reranking.patch",
            "0006-enforce-session-epoch.patch",
            "0007-keep-rag-credentials-external.patch",
            "0008-page-qdrant-scroll.patch",
            "open-webui-rag-gate.py",
            "open-webui-session-epoch-ledger.py",
        ):
            self.assertIn(asset, recipe)
        self.assertIn(
            'backend/open_webui/retrieval/rag_gate.py',
            recipe,
        )
        self.assertIn(
            '${pkgdir}/usr/lib/open-webui/open-webui-session-epoch-ledger',
            recipe,
        )
        self.assertIn("--require-hashes", recipe)
        self.assertGreaterEqual(recipe.count("--no-deps"), 2)
        self.assertIn("npm ci", read(OPEN_WEBUI / "0003-build-frozen-frontend.patch"))
        self.assertIn(
            "0ab15d00cda8a7dca4499d11960ea4532db5827ad5f55975c1062f6434cfbe9a",
            recipe,
        )
        self.assertIn("LC_ALL=C sort -z", recipe)
        self.assertNotIn("rapidocr-onnxruntime", recipe)
        self.assertIn("'python-rapidocr'", recipe)

    def test_augmented_native_qdrant_lock_is_complete_and_hashed(self):
        lock_path = OPEN_WEBUI / "open-webui-private-requirements.lock"
        lock_bytes = lock_path.read_bytes()
        lock = lock_bytes.decode()
        entries = re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9._-]*)==([^ \\\n]+)", lock)

        self.assertEqual(len(entries), 200)
        self.assertEqual(len({name.casefold().replace("_", "-") for name, _ in entries}), 200)
        self.assertIn(("qdrant-client", "1.18.0"), entries)
        self.assertIn(("portalocker", "3.2.0"), entries)
        self.assertEqual(
            hashlib.sha256(lock_bytes).hexdigest(),
            "8a3532e0b4e30a0edcbdb8255e915fca70ec583690266e17169ad48dbac6a1f5",
        )
        for block in re.split(r"(?m)(?=^[A-Za-z0-9][A-Za-z0-9._-]*==)", lock):
            if re.search(r"(?m)^[A-Za-z0-9][A-Za-z0-9._-]*==", block):
                self.assertIn("--hash=sha256:", block)

        externalized = {
            "accelerate",
            "av",
            "ctranslate2",
            "faster-whisper",
            "numpy",
            "onnxruntime",
            "opencv-python",
            "opencv-python-headless",
            "pandas",
            "pillow",
            "pyarrow",
            "pyclipper",
            "rapidocr",
            "scikit-learn",
            "scipy",
            "sentence-transformers",
            "sentencepiece",
            "shapely",
            "tokenizers",
            "torch",
            "transformers",
        }
        self.assertTrue(externalized.isdisjoint({name for name, _ in entries}))

    def test_offline_dependency_bundles_are_makepkg_sources_and_only_build_inputs(self):
        recipe = read(OPEN_WEBUI / "PKGBUILD")
        frontend_patch = read(OPEN_WEBUI / "0003-build-frozen-frontend.patch")
        source_info = subprocess.run(
            ["makepkg", "--printsrcinfo"],
            cwd=OPEN_WEBUI,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        self.assertIn("pkgrel=1", recipe)
        for asset, digest in (
            (
                "open-webui-npm-offline-closure-0.11.4.tar.zst",
                "617abc7d60da12f080faa690de989fff38eb4cd40b519256cce35a48086b9438",
            ),
            (
                "open-webui-python-offline-closure-0.11.4-cp314-x86_64.tar.zst",
                "005be1c5605e5291b37ccc789454f8f37ec894302bc064fcfcae5e1b4a9a0f13",
            ),
        ):
            self.assertIn(asset, source_info)
            self.assertIn(digest, source_info)
            self.assertIn(f"noextract = {asset}", source_info)
        for asset in (
            "npm-offline-closure.py",
            "npm-offline-closure-manifest.json",
            "python-offline-closure.py",
        ):
            self.assertIn(asset, recipe)
        self.assertIn('npm-offline-closure.py" seed', recipe)
        self.assertIn('python-offline-closure.py" verify-archive', recipe)
        self.assertIn("NPM_CONFIG_OFFLINE=true", recipe)
        self.assertIn("npm, 'ci', '--offline'", frontend_patch)
        for argument in (
            "--offline",
            "--no-index",
            '--find-links "${srcdir}/open-webui-python-offline-closure/wheelhouse"',
        ):
            self.assertIn(argument, recipe)

    def test_private_lock_has_reproducible_package_local_provenance(self):
        lock = read(OPEN_WEBUI / "open-webui-private-requirements.lock")
        constraints = read(OPEN_WEBUI / "open-webui-private-constraints.txt").splitlines()
        providers = read(OPEN_WEBUI / "open-webui-system-providers.txt").splitlines()
        generator = read(OPEN_WEBUI / "generate-open-webui-private-lock.zsh")
        verifier = read(OPEN_WEBUI / "verify-open-webui-private-lock.py")

        self.assertTrue(lock.startswith("# Generated by generate-open-webui-private-lock.zsh"))
        self.assertEqual(len(constraints), 200)
        self.assertEqual(constraints, sorted(set(constraints)))
        self.assertEqual(len(providers), 21)
        self.assertEqual(providers, sorted(set(providers)))
        self.assertIn("portalocker==3.2.0", constraints)
        self.assertIn("qdrant-client==1.18.0", constraints)
        for binding in (
            "f0c49cfa1936887c3447cb4c33cbbfdd2064aa0937140ec1c0520523efae5392",
            "x86_64-unknown-linux-gnu",
            "2026-09-21T19:31:44Z",
            "--generate-hashes",
            "--default-index https://pypi.org/simple",
            "--no-header",
            "--no-annotate",
        ):
            self.assertIn(binding, generator)
        self.assertIn('/usr/bin/env -i "${clean_environment[@]}"', generator)
        self.assertIn("EXPECTED_EXTERNALIZED", verifier)
        self.assertIn("EXPECTED_QDRANT_CLOSURE", verifier)
        self.assertTrue(os.access(OPEN_WEBUI / "generate-open-webui-private-lock.zsh", os.X_OK))

        spec = importlib.util.spec_from_file_location(
            "verify_open_webui_private_lock",
            OPEN_WEBUI / "verify-open-webui-private-lock.py",
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        verifier_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier_module)
        self.assertEqual(
            verifier_module.parse_constraints(
                OPEN_WEBUI / "open-webui-private-constraints.txt"
            ),
            verifier_module.parse_hashed_requirements(
                OPEN_WEBUI / "open-webui-private-requirements.lock"
            ),
        )

    def test_private_lock_verifier_rejects_a_locked_but_unrelated_root_swap(self):
        spec = importlib.util.spec_from_file_location(
            "verify_open_webui_private_lock_closure",
            OPEN_WEBUI / "verify-open-webui-private-lock.py",
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        lock = {
            "package": [
                {
                    "name": "open-webui",
                    "dependencies": [
                        {"name": "direct-root", "extra": ["feature"]},
                        {"name": "system-provider"},
                    ],
                    "optional-dependencies": {"all": [{"name": "qdrant-client"}]},
                },
                {
                    "name": "direct-root",
                    "version": "1.0",
                    "dependencies": [{"name": "transitive"}],
                    "optional-dependencies": {
                        "feature": [{"name": "feature-dependency"}]
                    },
                },
                {"name": "transitive", "version": "2.0"},
                {"name": "feature-dependency", "version": "3.0"},
                {"name": "system-provider", "version": "4.0"},
                {
                    "name": "qdrant-client",
                    "version": "1.18.0",
                    "dependencies": [{"name": "portalocker"}],
                },
                {"name": "portalocker", "version": "3.2.0"},
                {"name": "unrelated-locked-package", "version": "9.9"},
            ]
        }
        closure = verifier.target_private_closure(lock, ("system-provider",))
        self.assertEqual(
            closure,
            {
                "direct-root": "1.0",
                "feature-dependency": "3.0",
                "portalocker": "3.2.0",
                "qdrant-client": "1.18.0",
                "transitive": "2.0",
            },
        )

        swapped = dict(closure)
        del swapped["direct-root"]
        swapped["unrelated-locked-package"] = "9.9"
        with self.assertRaisesRegex(verifier.VerificationError, "closure"):
            verifier.verify_exact_closure(closure, swapped)

    def test_provider_boundary_rejects_missing_system_file_inventories(self):
        verifier_path = OPEN_WEBUI / "verify-open-webui-provider-boundary.py"
        spec = importlib.util.spec_from_file_location(
            "verify_open_webui_provider_boundary", verifier_path
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        class DistributionWithoutFiles:
            entry_points = ()

            def __init__(self, files):
                self.files = files

        for inventory in (None, ()):
            with self.subTest(inventory=inventory), mock.patch.object(
                verifier.importlib.metadata,
                "distribution",
                return_value=DistributionWithoutFiles(inventory),
            ), self.assertRaisesRegex(RuntimeError, "file inventory"):
                verifier.provider_payload()

    def test_private_install_drops_uv_build_metadata(self):
        recipe = read(OPEN_WEBUI / "PKGBUILD")

        self.assertIn('rm -f "${_site}/.lock"', recipe)
        self.assertIn(
            'find "${_site}" -type f -name uv_cache.json -delete',
            recipe,
        )

    def test_source_patches_are_narrow_and_runtime_is_uds_only(self):
        python_patch = read(OPEN_WEBUI / "0001-support-python-3.14.patch")
        provider_patch = read(OPEN_WEBUI / "0002-use-system-ml-stack.patch")
        uds_patch = read(OPEN_WEBUI / "0004-support-unix-socket.patch")
        service = read(OPEN_WEBUI / "open-webui.service")
        environment = read(OPEN_WEBUI / "open-webui.env")

        self.assertIn('< 3.15.0a1', python_patch)
        self.assertNotIn("pydantic", python_patch.casefold())
        self.assertNotIn("psycopg", python_patch.casefold())
        for dependency in ("transformers", "sentence-transformers", "rapidocr", "onnxruntime"):
            self.assertIn(f'-    "{dependency}', provider_patch)
        self.assertIn("--uds", uds_patch)
        self.assertIn("RuntimeDirectory=open-webui", service)
        self.assertIn("RuntimeDirectoryMode=0750", service)
        self.assertIn("serve --uds /run/open-webui/open-webui.sock", service)
        self.assertNotIn("--host", service)
        self.assertNotIn("--port", service)
        self.assertNotIn("OPEN_WEBUI_HOST", environment)
        self.assertNotIn("OPEN_WEBUI_PORT", environment)
        self.assertIn("STATIC_DIR=/var/lib/open-webui/static", environment)

    def test_runtime_credentials_are_automatic_and_fail_closed(self):
        service = read(OPEN_WEBUI / "open-webui.service")
        wrapper = read(OPEN_WEBUI / "open-webui-wrapper")

        for credential in (
            "webui-secret-key",
            "oauth-client-info-encryption-key",
            "oauth-session-token-encryption-key",
            "valkey-url",
            "qdrant-runtime-api-key",
        ):
            self.assertIn(f"LoadCredentialEncrypted={credential}:", service)
            self.assertIn(credential, wrapper)
        self.assertIn(
            "LoadCredential=session-epoch:/var/lib/open-webui-session-epoch/current",
            service,
        )
        self.assertIn(
            'CREDENTIAL_NAME = "session-epoch"',
            read(OPEN_WEBUI / "0006-enforce-session-epoch.patch"),
        )
        self.assertIn("CREDENTIALS_DIRECTORY", wrapper)
        self.assertIn("exit 78", wrapper)
        # The service loads exactly these credentials: no administrative
        # identity, and Open WebUI stores no secret for its model connections.
        self.assertEqual(
            re.findall(r"(?m)^LoadCredential(?:Encrypted)?=([^:]+):", service),
            [
                "webui-secret-key",
                "oauth-client-info-encryption-key",
                "oauth-session-token-encryption-key",
                "valkey-url",
                "qdrant-runtime-api-key",
                "session-epoch",
            ],
        )
        self.assertEqual(
            re.findall(r"(?m)^\s*load_credential (\S+) ", wrapper),
            [
                "webui-secret-key",
                "oauth-client-info-encryption-key",
                "oauth-session-token-encryption-key",
                "valkey-url",
                "qdrant-runtime-api-key",
                "admin-email",
                "admin-name",
                "admin-bootstrap-password",
            ],
        )
        self.assertNotIn("RAG_OPENAI_API_KEY", wrapper)
        self.assertNotIn("RAG_EXTERNAL_RERANKER_API_KEY", wrapper)
        self.assertIn("IPAddressDeny=any", service)
        self.assertIn("IPAddressAllow=localhost", service)

    def test_stable_signing_and_encryption_authorities_must_be_distinct(self):
        wrapper = OPEN_WEBUI / "open-webui-wrapper"
        credential_values = {
            "webui-secret-key": "repeated-stable-secret",
            "oauth-client-info-encryption-key": "repeated-stable-secret",
            "oauth-session-token-encryption-key": "independent-session-secret",
            "valkey-url": "redis://open-webui@127.0.0.1:6379/0",
            "qdrant-runtime-api-key": "qdrant-runtime-only",
        }
        with tempfile.TemporaryDirectory() as directory:
            credential_directory = Path(directory)
            for credential_name, value in credential_values.items():
                (credential_directory / credential_name).write_text(value, encoding="utf-8")
            result = subprocess.run(
                ["/bin/sh", str(wrapper), "--version"],
                env={**os.environ, "CREDENTIALS_DIRECTORY": directory},
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 78)
        self.assertIn("must be pairwise distinct", result.stderr)
        for value in credential_values.values():
            self.assertNotIn(value, result.stderr)

    def test_household_defaults_close_signup_and_server_code_installation(self):
        environment = read(OPEN_WEBUI / "open-webui.env")

        for setting in (
            "WEBUI_AUTH=true",
            "ENABLE_SIGNUP=false",
            "DEFAULT_USER_ROLE=pending",
            "WEBUI_SESSION_COOKIE_SECURE=true",
            "WEBUI_SESSION_COOKIE_SAME_SITE=strict",
            "ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS=false",
            "ENABLE_VERSION_UPDATE_CHECK=false",
            "OFFLINE_MODE=true",
            "ENABLE_API_KEYS=false",
            "UVICORN_WORKERS=1",
            "ENABLE_PROFILE_IMAGE_URL_FORWARDING=false",
            "ENABLE_CODE_EXECUTION=false",
            "ENABLE_CODE_INTERPRETER=false",
            "ENABLE_AUTOMATIONS=false",
            "ENABLE_CALENDAR=false",
            "ENABLE_EVALUATION_ARENA_MODELS=false",
            "ENABLE_RETRIEVAL_QUERY_GENERATION=false",
            "VECTOR_DB=qdrant",
            "QDRANT_COLLECTION_PREFIX=open-webui-rag-v1",
            "ENABLE_QDRANT_MULTITENANCY_MODE=true",
            "RAG_RERANKING_ENGINE=external",
            "RAG_RERANKING_MODEL=zerank-2-GGUF",
            "ENABLE_RAG_HYBRID_SEARCH=true",
            "ENABLE_OLLAMA_API=false",
            "OPENAI_API_BASE_URLS=http://127.0.0.1:13305/api/v1",
            "OPENAI_API_KEYS=",
            "RAG_OPENAI_API_BASE_URL=http://127.0.0.1:13305/api/v1",
            "RAG_EXTERNAL_RERANKER_URL=http://127.0.0.1:13305/api/v1/rerank",
            "RAG_EXTERNAL_RERANKER_TIMEOUT=30",
            "ENABLE_STAR_SESSIONS_MIDDLEWARE=true",
            "WEBSOCKET_MANAGER=redis",
        ):
            self.assertIn(setting, environment)
        self.assertNotIn("RAG_RERANKING_ENGINE=openai", environment)

    def test_embedding_prefixes_are_the_zembed_wrapper_heads(self):
        environment = read(OPEN_WEBUI / "open-webui.env")
        provider_path = REPO_ROOT / "tools" / "fixtures" / "open-webui-household" / "provider.py"
        spec = importlib.util.spec_from_file_location("open_webui_household_provider", provider_path)
        provider = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(provider)

        # No JSON discriminator: the wrapper heads travel as text prefixes.
        self.assertNotIn("RAG_EMBEDDING_PREFIX_FIELD_NAME", environment)
        for setting, input_type in (
            ("RAG_EMBEDDING_QUERY_PREFIX", "query"),
            ("RAG_EMBEDDING_CONTENT_PREFIX", "document"),
        ):
            # systemd reads a double-quoted EnvironmentFile value across lines.
            match = re.search(rf'^{setting}="([^"]*)"$', environment, re.MULTILINE)
            self.assertIsNotNone(match, setting)
            prefix = match.group(1)
            # Open WebUI 0.11.4 joins a text prefix as f"{prefix}{text}".
            text = "household canary"
            self.assertTrue(
                provider.format_zembed_input(text, input_type).startswith(f"{prefix}{text}"),
                setting,
            )
            self.assertEqual(prefix, f"<|im_start|>system\n{input_type}<|im_end|>\n<|im_start|>user\n")

    def test_session_epoch_state_is_root_owned_and_outside_restore_state(self):
        tmpfiles = read(OPEN_WEBUI / "open-webui.tmpfiles")
        service = read(OPEN_WEBUI / "open-webui.service")

        self.assertIn(
            "d /var/lib/open-webui-session-epoch 0700 root root -",
            tmpfiles,
        )
        self.assertIn(
            "LoadCredential=session-epoch:/var/lib/open-webui-session-epoch/current",
            service,
        )
        self.assertNotIn("StateDirectory=open-webui-session-epoch", service)

    def test_operator_notes_describe_only_the_disposable_candidate(self):
        notes = read(OPEN_WEBUI / "README.md")

        self.assertIn("Open WebUI 0.11.4", notes)
        self.assertIn("not approved for production activation or publication", notes)
        self.assertIn("/run/open-webui/open-webui.sock", notes)
        self.assertIn("open-webui-session-epoch-ledger reserve", notes)
        self.assertIn("open-webui-commission-admin", notes)
        for collection in ("memories", "knowledge", "files", "web-search", "hash-based"):
            self.assertIn(f"open-webui-rag-v1_{collection}", notes)
        self.assertIn("create or reset collections", notes)
        self.assertIn("closure archives are immutable", notes)
        self.assertIn("`makepkg` sources", notes)
        self.assertIn("npm ci --offline", notes)
        self.assertIn("uv --offline --no-index --require-hashes", notes)
        self.assertIn("integrated provider, restore, and rollback evidence", notes)
        self.assertNotIn("0.9.5", notes)
        self.assertNotIn("127.0.0.1:8080", notes)
        self.assertNotIn("enable --now", notes)

    def test_tailnet_sidecar_is_unprivileged_nameless_and_private(self):
        recipe = read(OPEN_WEBUI / "PKGBUILD")
        values = {}
        section = None
        unit_lines = read(OPEN_WEBUI / "open-webui-tailnet.service").splitlines()
        self.assertFalse([line for line in unit_lines if line.rstrip().endswith("\\")])
        for line in unit_lines:
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("["):
                section = line.strip("[]")
                continue
            key, _, value = line.partition("=")
            values.setdefault((section, key.strip()), []).append(value.strip())

        self.assertIn("'open-webui-tailnet.service'", recipe)
        self.assertIn(
            '"${pkgdir}/usr/lib/systemd/system/open-webui-tailnet.service"',
            recipe,
        )
        self.assertRegex(recipe, r"'tailscale: [^']+'")
        self.assertNotIn("'tailscale'", recipe.split("optdepends=")[0])
        for section, key, value in (
            ("Unit", "After", "network-online.target"),
            ("Unit", "Wants", "network-online.target"),
            ("Service", "DynamicUser", "yes"),
            ("Service", "SupplementaryGroups", "open-webui-proxy"),
            ("Service", "StateDirectory", "open-webui-tailnet"),
            ("Service", "RuntimeDirectory", "open-webui-tailnet"),
            ("Service", "Environment", "TS_NO_LOGS_NO_SUPPORT=true"),
            ("Service", "ProtectSystem", "strict"),
            ("Service", "ProtectHome", "yes"),
            ("Service", "NoNewPrivileges", "yes"),
            ("Service", "CapabilityBoundingSet", ""),
            ("Service", "AmbientCapabilities", ""),
            ("Service", "IPAddressDeny", "127.0.0.1 ::1"),
            ("Service", "Restart", "on-failure"),
            (
                "Service",
                "ExecStart",
                "/usr/bin/tailscaled"
                " --statedir=%S/open-webui-tailnet"
                " --socket=%t/open-webui-tailnet/tailscaled.sock"
                " --tun=userspace-networking --port=0",
            ),
        ):
            self.assertEqual(values.get((section, key)), [value], key)
        pinned_service_keys = {
            "DynamicUser",
            "Environment",
            "CapabilityBoundingSet",
            "AmbientCapabilities",
            "IPAddressDeny",
        }
        keys = [key for _, key in values]
        for key in pinned_service_keys:
            self.assertEqual(keys.count(key), 1, key)
        self.assertEqual([key for key in keys if key.startswith("Exec")], ["ExecStart"])
        self.assertFalse(
            set(keys)
            & {"User", "Group", "UnsetEnvironment", "EnvironmentFile", "IPAddressAllow"}
        )
        for (_, key), entries in values.items():
            for entry in entries:
                for forbidden in ("--hostname", "tag:", ".ts.net"):
                    self.assertNotIn(forbidden, entry, key)

    def test_commissioning_helper_uses_uds_and_never_accepts_secret_arguments(self):
        helper = read(OPEN_WEBUI / "open-webui-commission-admin")

        self.assertIn("AF_UNIX", helper)
        self.assertIn("CREDENTIALS_DIRECTORY", helper)
        self.assertIn("/api/v1/auths/signin", helper)
        self.assertIn("/api/v1/auths/update/password", helper)
        self.assertIn("/api/v1/users/", helper)
        self.assertIn("/api/config", helper)
        self.assertIn('credential("admin-name")', helper)
        self.assertIn('intended.get("name")', helper)
        self.assertNotIn("argparse", helper)
        self.assertNotRegex(helper, r"sys\.argv\[[1-9]")


def load_commissioning_helper():
    path = OPEN_WEBUI / "open-webui-commission-admin"
    loader = importlib.machinery.SourceFileLoader(
        "open_webui_commission_admin", str(path)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeClock:
    """A wall clock that moves only when the code under test sleeps."""

    def __init__(self, now: float):
        self.now = now

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("sleep length must be non-negative")
        self.now += seconds


class FakeOpenWebUI:
    """The 0.11.4 auth routes the helper calls, served on a real Unix socket.

    A password change records its whole second and rejects every token whose
    whole-second iat is at or before it, as upstream is_valid_token does in
    backend/open_webui/utils/auth.py.
    """

    def __init__(self, clock: FakeClock, email: str, name: str, password: str):
        self.clock = clock
        self.email = email
        self.name = name
        self.password = password
        self.revoked_at: int | None = None
        self.requests: list[tuple[str, str, int]] = []

    def respond(self, method, path, token, payload):
        if method == "POST" and path == "/api/v1/auths/signin":
            if payload != {"email": self.email, "password": self.password}:
                return 400, {"detail": "incorrect credentials"}
            return 200, {"token": f"admin:{int(self.clock.time())}"}
        if token is None or not token.startswith("admin:"):
            return 401, {"detail": "Not authenticated"}
        issued_at = int(token.removeprefix("admin:"))
        if self.revoked_at is not None and issued_at <= self.revoked_at:
            return 401, {"detail": "Invalid token"}
        if method == "POST" and path == "/api/v1/auths/update/password":
            if payload is None or payload.get("password") != self.password:
                return 400, {"detail": "incorrect password"}
            self.password = payload["new_password"]
            self.revoked_at = int(self.clock.time())
            return 200, True
        if method == "GET" and path == "/api/v1/users/":
            user = {"email": self.email, "name": self.name, "role": "admin"}
            return 200, {"total": 1, "users": [user]}
        if method == "GET" and path == "/api/config":
            return 200, {"features": {"enable_signup": False}}
        return 404, {"detail": "Not Found"}

    def handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _dispatch(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length)) if length else None
                authorization = self.headers.get("Authorization", "")
                token = authorization.removeprefix("Bearer ") or None
                status, body = fake.respond(self.command, self.path, token, payload)
                fake.requests.append((self.command, self.path, status))
                encoded = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            do_GET = _dispatch
            do_POST = _dispatch

            def log_message(self, _format, *_args):
                return

        return Handler


@contextlib.contextmanager
def serving_unix_socket(socket_path: Path, handler):
    server = socketserver.ThreadingUnixStreamServer(str(socket_path), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class CommissioningHelperTests(unittest.TestCase):
    def test_final_session_outlives_the_password_change_revocation(self):
        helper = load_commissioning_helper()
        # Start mid-second so every request before the helper's wait falls in
        # the second that the password change revokes.
        start = 1_790_000_000.25
        clock = FakeClock(start)
        server = FakeOpenWebUI(
            clock, "admin@example.invalid", "Administrator", "bootstrap-secret"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials = root / "credentials"
            credentials.mkdir()
            for name, value in (
                ("admin-email", "Admin@Example.invalid"),
                ("admin-name", "Administrator"),
                ("admin-bootstrap-password", "bootstrap-secret"),
                ("admin-final-password", "final-secret"),
            ):
                (credentials / name).write_text(f"{value}\n", encoding="utf-8")
            socket_path = root / "open-webui.sock"
            environment = {
                "CREDENTIALS_DIRECTORY": str(credentials),
                "OPEN_WEBUI_SOCKET": str(socket_path),
            }
            with (
                serving_unix_socket(socket_path, server.handler()),
                mock.patch.dict(os.environ, environment),
                mock.patch.object(helper, "time", clock),
                contextlib.redirect_stdout(open(os.devnull, "w")),
            ):
                self.assertEqual(helper.main(), 0)

        self.assertEqual(server.password, "final-secret")
        self.assertNotIn(401, [status for _, _, status in server.requests])
        self.assertEqual(
            server.requests[-2:],
            [("GET", "/api/v1/users/", 200), ("GET", "/api/config", 200)],
        )
        # The helper waits out only the rest of the revoked second.
        self.assertLess(clock.now - start, 1.0)


class RapidOCRPackageContractTests(unittest.TestCase):
    def test_recipe_binds_commit_models_and_successor_boundary(self):
        recipe = read(RAPIDOCR / "PKGBUILD")

        self.assertIn("pkgname=python-rapidocr", recipe)
        self.assertIn("pkgver=3.9.2", recipe)
        self.assertIn("095232a4c94f7f0e6600ba5bba1177010ad696d4", recipe)
        for digest in (
            "be524502995f5a2628b777daa6cf37d207aa7a6d9d3488c942338ff3698aef5f",
            "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
            "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
            "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
        ):
            self.assertIn(digest, recipe)
        self.assertIn("'python-onnxruntime'", recipe)
        self.assertIn("conflicts=('python-rapidocr-onnxruntime')", recipe)
        self.assertIn("replaces=('python-rapidocr-onnxruntime')", recipe)
        self.assertNotIn("provides=", recipe)
        self.assertNotIn("'SKIP'", recipe)
        self.assertIn("patch --fuzz=0", recipe)
        self.assertNotIn("/etc/rapidocr", recipe)
        self.assertIn("rapidocr/models", recipe)


if __name__ == "__main__":
    unittest.main()
