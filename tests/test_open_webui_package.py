import hashlib
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
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

        self.assertIn("pkgver=0.11.0", recipe)
        self.assertIn(
            "e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9",
            recipe,
        )
        self.assertIn(
            "71c266be87d0fb2cd79d9172d0e86a3b1b59d550d7054622b831344df07d361b",
            recipe,
        )
        self.assertIn("open-webui-private-requirements.lock", recipe)
        self.assertIn('python "${srcdir}/verify-open-webui-private-lock.py"', recipe)
        self.assertNotIn("'SKIP'", recipe)
        self.assertEqual(recipe.count("patch --fuzz=0"), 7)
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
            "57b3bc90e6ebca23c0cec1736e470fbb2fee1c6b05531551b8871f3cbdab185c",
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

        self.assertEqual(len(entries), 222)
        self.assertEqual(len({name.casefold().replace("_", "-") for name, _ in entries}), 222)
        self.assertIn(("qdrant-client", "1.18.0"), entries)
        self.assertIn(("portalocker", "3.2.0"), entries)
        self.assertEqual(
            hashlib.sha256(lock_bytes).hexdigest(),
            "df99fc265998cf7029d22b01faa81f3dc015d255754748e3e6512d84cce95007",
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

        self.assertIn("pkgrel=3", recipe)
        for asset, digest in (
            (
                "open-webui-npm-offline-closure-0.11.0.tar.zst",
                "6238b436c6669a311623d97724c6b2ada0e77090d0e5219860acc38c53fb32b1",
            ),
            (
                "open-webui-python-offline-closure-0.11.0-cp314-x86_64.tar.zst",
                "bcd3c5c651fc42e8e5a73a4c81f4b5760e82f6b39eb714caf999700bad4ed27c",
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
        self.assertEqual(len(constraints), 222)
        self.assertEqual(constraints, sorted(set(constraints)))
        self.assertEqual(len(providers), 21)
        self.assertEqual(providers, sorted(set(providers)))
        self.assertIn("portalocker==3.2.0", constraints)
        self.assertIn("qdrant-client==1.18.0", constraints)
        for binding in (
            "bf42de5c836d5afe5628533cf8369e856d5d09bfd00efef302c31df3fa249947",
            "x86_64-unknown-linux-gnu",
            "2026-08-18T06:25:20Z",
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
            "lemonade-inference-api-key",
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
        self.assertNotIn("qdrant-admin", service.casefold())
        self.assertNotIn("lemonade-admin", service.casefold())
        self.assertNotIn("qdrant-admin", wrapper.casefold())
        self.assertNotIn("lemonade-admin", wrapper.casefold())
        self.assertIn("RAG_EXTERNAL_RERANKER_API_KEY=$RAG_OPENAI_API_KEY", wrapper)
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
            "lemonade-inference-api-key": "lemonade-inference-only",
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
            "RAG_EXTERNAL_RERANKER_URL=http://127.0.0.1:8000/api/v1/rerank",
            "RAG_EXTERNAL_RERANKER_TIMEOUT=30",
            "RAG_EMBEDDING_QUERY_PREFIX=query",
            "RAG_EMBEDDING_CONTENT_PREFIX=document",
            "RAG_EMBEDDING_PREFIX_FIELD_NAME=input_type",
            "ENABLE_STAR_SESSIONS_MIDDLEWARE=true",
            "WEBSOCKET_MANAGER=redis",
        ):
            self.assertIn(setting, environment)
        self.assertNotIn("RAG_RERANKING_ENGINE=openai", environment)

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

        self.assertIn("Open WebUI 0.11.0", notes)
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
