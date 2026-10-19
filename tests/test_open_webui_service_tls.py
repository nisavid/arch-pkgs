"""Package TLS policy and real client/server authentication regressions.

The integration cases require the package's qdrant-client, redis,
python-socketio, and starsessions dependencies. No running services or real
credentials are used: disposable listeners receive a synthetic canary only.
"""

import asyncio
import contextlib
import importlib.util
import json
import os
import shutil
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/open-webui"
SPEC = importlib.util.spec_from_file_location("open_webui_service_tls", PACKAGE / "open-webui-service-tls.py")
TLS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TLS)
CANARY = "synthetic-service-credential-canary"


def certificate(root, name, san="IP:127.0.0.1"):
    cert, key = root / f"{name}.pem", root / f"{name}.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=disposable-test", "-addext", f"subjectAltName={san}",
         "-keyout", str(key), "-out", str(cert)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return cert, key


def server_context(pair):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(*map(str, pair))
    return context


class Listener(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, tls_context, protocol):
        self.tls_context = tls_context
        self.protocol = protocol
        self.received = []
        self.failures = 0
        super().__init__(("127.0.0.1", 0), Handler)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        connection = self.request
        connection.settimeout(2)
        try:
            if self.server.tls_context is None:
                self.server.received.append(connection.recv(65536))
                return
            connection = self.server.tls_context.wrap_socket(connection, server_side=True)
            stream = connection.makefile("rb")
            if self.server.protocol == "http":
                data = b""
                while not data.endswith(b"\r\n\r\n"):
                    line = stream.readline()
                    if not line:
                        return
                    data += line
                self.server.received.append(data)
                body = json.dumps({"result": {"collections": []}, "status": "ok", "time": 0}).encode()
                connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
                return
            while line := stream.readline():
                if not line.startswith(b"*"):
                    return
                command = []
                for _ in range(int(line[1:])):
                    length = int(stream.readline()[1:])
                    command.append(stream.read(length))
                    stream.read(2)
                self.server.received.append(b" ".join(command))
                verb = command[0].upper()
                if verb == b"HELLO":
                    reply = b"%2\r\n+server\r\n+redis\r\n+proto\r\n:3\r\n"
                elif verb == b"PING":
                    reply = b"+PONG\r\n"
                elif verb == b"GET":
                    reply = b"$-1\r\n"
                elif verb == b"PUBLISH":
                    reply = b":1\r\n"
                else:
                    reply = b"+OK\r\n"
                connection.sendall(reply)
        except (ssl.SSLError, OSError, ValueError):
            self.server.failures += 1
        finally:
            connection.close()


@contextlib.contextmanager
def listening(tls_context, protocol):
    server = Listener(tls_context, protocol)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@unittest.skipUnless(shutil.which("openssl"), "openssl is required to generate disposable certificates")
class TLSFixtures:
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.legitimate = certificate(cls.root, "legitimate")
        cls.impostor = certificate(cls.root, "impostor")
        cls.wrong_name = certificate(cls.root, "wrong-name", "IP:127.0.0.2")
        cls.expired = certificate(cls.root, "expired")
        subprocess.run(
            ["openssl", "x509", "-in", str(cls.expired[0]), "-signkey", str(cls.expired[1]),
             "-days", "-1", "-out", str(cls.expired[0])],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        (cls.root / "invalid.pem").write_text("not a certificate")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def environment(self, cert=None):
        return {
            "QDRANT_URI": "https://127.0.0.1:6333",
            "QDRANT_CA_CERT": str((cert or self.legitimate)[0]),
            "VALKEY_CA_CERT": str((cert or self.legitimate)[0]),
            "REDIS_URL": f"rediss://open-webui:{CANARY}@127.0.0.1:6379/0",
        }


class PolicyTests(TLSFixtures, unittest.TestCase):
    def test_all_redis_consumers_receive_required_verification(self):
        with mock.patch.dict(os.environ, self.environment(), clear=True):
            TLS.configure_environment()
            self.assertEqual(os.environ["REDIS_URL"], os.environ["WEBSOCKET_REDIS_URL"])
            query = parse_qs(urlsplit(os.environ["REDIS_URL"]).query)
            self.assertEqual(query, {"ssl_cert_reqs": ["required"], "ssl_check_hostname": ["true"], "ssl_ca_certs": [str(self.legitimate[0])]})

    def test_invalid_transport_options_fail_without_printing_credentials(self):
        cases = [
            {"QDRANT_URI": "http://127.0.0.1:6333"},
            {"QDRANT_URI": f"https://{CANARY}@127.0.0.1:6333"},
            {"REDIS_URL": f"redis://:{CANARY}@127.0.0.1:6379"},
            {"REDIS_URL": f"rediss://:{CANARY}@localhost:6379"},
            {"QDRANT_CA_CERT": str(self.root / "missing")},
            {"VALKEY_CA_CERT": str(self.root / "missing")},
            {"VALKEY_CA_CERT": str(self.root / "invalid.pem")},
            {"QDRANT_CA_CERT": str(self.root / "invalid.pem")},
            {"REDIS_CLUSTER": "true"}, {"WEBSOCKET_REDIS_CLUSTER": "true"},
            {"REDIS_SENTINEL_HOSTS": "127.0.0.1"}, {"WEBSOCKET_SENTINEL_HOSTS": "127.0.0.1"},
            {"WEBSOCKET_REDIS_OPTIONS": '{"ssl":false}'}, {"QDRANT_PREFER_GRPC": "true"},
        ]
        for query in ("ssl_cert_reqs=none", "ssl_check_hostname=false", "ssl_ca_certs=/tmp/other", "ssl_ca_data=other", "host=other", "ssl_cert_reqs=required&ssl_cert_reqs=none", "ssl_exclude_verify_flags=32"):
            cases.append({"REDIS_URL": self.environment()["REDIS_URL"] + "?" + query})
        for override in cases:
            with self.subTest(override=list(override)), mock.patch.dict(os.environ, self.environment() | override, clear=True):
                with self.assertRaises(TLS.ServiceTLSConfigurationError) as raised:
                    TLS.configure_environment()
                self.assertNotIn(CANARY, str(raised.exception))

    def test_qdrant_has_an_explicit_verifying_context_and_no_proxy_or_redirects(self):
        with mock.patch.dict(os.environ, self.environment(), clear=True):
            options = TLS.qdrant_client_options(os.environ["QDRANT_URI"])
        self.assertIs(options["verify"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(options["verify"].check_hostname)
        self.assertFalse(options["trust_env"])
        self.assertFalse(options["follow_redirects"])
        self.assertTrue(options["https"])
        self.assertFalse(options["prefer_grpc"])

    def test_startup_failure_precedes_application_import(self):
        wrapper = (PACKAGE / "open-webui-wrapper").read_text()
        self.assertLess(wrapper.index("configure_or_exit();"), wrapper.index("from open_webui import app"))
        result = subprocess.run(
            [sys.executable, "-c", "import importlib.util; s=importlib.util.spec_from_file_location('tls', " + repr(str(PACKAGE / "open-webui-service-tls.py")) + "); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.configure_or_exit(); raise AssertionError('application imported')"],
            env=self.environment() | {"REDIS_URL": f"redis://:{CANARY}@127.0.0.1:6379"}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 78)
        self.assertNotIn(CANARY, result.stderr)
        self.assertNotIn("application imported", result.stderr)

    def test_both_actual_qdrant_constructors_use_policy_after_paging_patch(self):
        import ast
        fixture = ROOT / "tools/fixtures/open-webui-household"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("qdrant", "qdrant_multitenancy"):
                target = root / f"backend/open_webui/retrieval/vector/dbs/{name}.py"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((fixture / f"open-webui-0.11.4-pristine-{name.replace('_', '-')}.py").read_bytes())
            for patch in ("0008-page-qdrant-scroll.patch", "0009-authenticate-service-peers.patch"):
                subprocess.run(["patch", "--fuzz=0", "-Np1", "-i", str(PACKAGE / patch)], cwd=root, check=True, capture_output=True)
            for name in ("qdrant", "qdrant_multitenancy"):
                tree = ast.parse((root / f"backend/open_webui/retrieval/vector/dbs/{name}.py").read_text())
                cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "QdrantClient")
                constructor = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
                cls.bases = []
                cls.body = [constructor]
                capture = mock.Mock()
                namespace = {"Qclient": capture, "qdrant_client_options": TLS.qdrant_client_options,
                             "QDRANT_URI": "https://127.0.0.1:6333", "QDRANT_API_KEY": CANARY,
                             "QDRANT_PREFER_GRPC": False, "QDRANT_COLLECTION_PREFIX": "test",
                             "QDRANT_ON_DISK": False, "QDRANT_GRPC_PORT": 6334,
                             "QDRANT_TIMEOUT": 1, "QDRANT_HNSW_M": 16}
                exec(compile(ast.Module(body=[cls], type_ignores=[]), name, "exec"), namespace)
                with mock.patch.dict(os.environ, self.environment(), clear=True):
                    namespace["QdrantClient"]()
                    options = capture.call_args.kwargs
                    self.assertTrue(options["https"])
                    self.assertTrue(options["verify"].check_hostname)
                    namespace["QDRANT_PREFER_GRPC"] = True
                    with self.assertRaises(TLS.ServiceTLSConfigurationError):
                        namespace["QdrantClient"]()
                self.assertEqual(capture.call_count, 1)


CLIENT_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("redis", "qdrant_client", "socketio", "starsessions"))


@unittest.skipUnless(CLIENT_DEPENDENCIES, "requires qdrant-client, redis, python-socketio, and starsessions")
class ClientHandshakeTests(TLSFixtures, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Exercise the installed package's exact redis-py patch in an isolated
        # copy, leaving the test runner's dependencies unchanged.
        source = Path(importlib.util.find_spec("redis").origin).parent
        cls.redis_site = cls.root / "patched-dependencies"
        shutil.copytree(source, cls.redis_site / "redis")
        subprocess.run(
            ["patch", "--fuzz=0", "-Np1", "-i", str(PACKAGE / "0010-isolate-explicit-redis-trust.patch")],
            cwd=cls.redis_site, check=True, capture_output=True,
        )
        cls.module_prefixes = ("redis", "socketio", "starsessions")
        cls.saved_modules = {name: module for name, module in sys.modules.items()
                             if name.split(".")[0] in cls.module_prefixes}
        for name in cls.saved_modules:
            del sys.modules[name]
        sys.path.insert(0, str(cls.redis_site))

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.redis_site))
        for name in list(sys.modules):
            if name.split(".")[0] in cls.module_prefixes:
                del sys.modules[name]
        sys.modules.update(cls.saved_modules)
        super().tearDownClass()

    def test_qdrant_rejects_plaintext_untrusted_wrong_name_and_reconnect_impostor(self):
        from qdrant_client import QdrantClient
        from qdrant_client.http.exceptions import ResponseHandlingException
        for peer, trusted in ((None, self.legitimate), (self.impostor, self.legitimate), (self.wrong_name, self.wrong_name), (self.expired, self.expired)):
            with self.subTest(peer=peer), listening(server_context(peer) if peer else None, "http") as server, mock.patch.dict(os.environ, self.environment(trusted) | {"SSL_CERT_FILE": str(self.impostor[0])}, clear=True):
                client = QdrantClient(**TLS.qdrant_client_options(f"https://127.0.0.1:{server.server_address[1]}"), api_key=CANARY, timeout=1, check_compatibility=False)
                with self.assertRaises(ResponseHandlingException):
                    client.get_collections()
                client.close()
                self.assertNotIn(CANARY.encode(), b"".join(server.received))
        with listening(server_context(self.legitimate), "http") as server, mock.patch.dict(os.environ, self.environment() | {"SSL_CERT_FILE": str(self.impostor[0])}, clear=True):
            client = QdrantClient(**TLS.qdrant_client_options(f"https://127.0.0.1:{server.server_address[1]}"), api_key=CANARY, timeout=1, check_compatibility=False)
            self.assertEqual(client.get_collections().collections, [])
            self.assertIn(CANARY.encode(), b"".join(server.received))
            server.received.clear()
            server.tls_context = server_context(self.impostor)
            with self.assertRaises(ResponseHandlingException):
                client.get_collections()
            client.close()
            self.assertNotIn(CANARY.encode(), b"".join(server.received))

    def test_sync_async_socketio_and_session_redis_authenticate_every_connection(self):
        import redis
        import redis.asyncio
        from socketio import AsyncRedisManager
        from starsessions.stores.redis import RedisStore
        from redis.backoff import NoBackoff
        from redis.retry import Retry
        from redis.asyncio.retry import Retry as AsyncRetry

        for consumer in ("sync", "async", "socketio", "sessions"):
            for peer, trusted, legitimate in ((None, self.legitimate, False), (self.impostor, self.legitimate, False), (self.wrong_name, self.wrong_name, False), (self.expired, self.expired, False), (self.legitimate, self.legitimate, True)):
                with self.subTest(consumer=consumer, peer=peer), listening(server_context(peer) if peer else None, "redis") as server, mock.patch.dict(os.environ, self.environment(trusted) | {"SSL_CERT_FILE": str(self.impostor[0])}, clear=True):
                    url = TLS.redis_url(f"rediss://open-webui:{CANARY}@127.0.0.1:{server.server_address[1]}/0?socket_timeout=1&socket_connect_timeout=1")
                    if consumer == "sync":
                        client = redis.Redis.from_url(url, retry=Retry(NoBackoff(), 0))
                        try:
                            if legitimate:
                                self.assertTrue(client.ping())
                                self.assertIn(CANARY.encode(), b"".join(server.received))
                                client.connection_pool.disconnect()
                                server.received.clear()
                                server.tls_context = server_context(self.impostor)
                            with self.assertRaises(redis.exceptions.ConnectionError):
                                client.ping()
                        finally:
                            client.close()
                    else:
                        async def attempt():
                            if consumer == "socketio":
                                manager = AsyncRedisManager(url, redis_options={"retry": AsyncRetry(NoBackoff(), 0)})
                                manager._redis_connect()
                                client = manager.redis
                            elif consumer == "sessions":
                                client = RedisStore(url=url)._connection
                                client.connection_pool.connection_kwargs["retry"] = AsyncRetry(NoBackoff(), 0)
                            else:
                                client = redis.asyncio.Redis.from_url(url, retry=AsyncRetry(NoBackoff(), 0))
                            try:
                                if legitimate:
                                    self.assertTrue(await client.ping())
                                    self.assertIn(CANARY.encode(), b"".join(server.received))
                                    await client.connection_pool.disconnect()
                                    server.received.clear()
                                    server.tls_context = server_context(self.impostor)
                                with self.assertRaises(redis.exceptions.ConnectionError):
                                    await client.ping()
                            finally:
                                await client.aclose()
                        asyncio.run(attempt())
                    self.assertNotIn(CANARY.encode(), b"".join(server.received))


if __name__ == "__main__":
    unittest.main()
