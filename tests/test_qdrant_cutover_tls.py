"""Exercise the real cutover curl boundary with disposable local listeners."""

import http.server
import os
from pathlib import Path
import shutil
import socketserver
import ssl
import subprocess
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/qdrant_production_cutover.zsh"
SECRET = "synthetic-cutover-credential-never-a-production-key"


def certificate(directory, name, san="IP:127.0.0.1"):
    cert, key = directory / f"{name}.pem", directory / f"{name}.key"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
        "-nodes", "-days", "1", "-subj", f"/CN={name}", "-addext", f"subjectAltName={san}",
        "-keyout", str(key), "-out", str(cert),
    ], check=True, capture_output=True)
    return cert, key


class Listener:
    def __init__(self, cert=None, key=None, redirect=None, port=0):
        self.requests = []
        self.raw = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def handle_one_request(self):
                # Record even a TLS ClientHello sent to a plaintext imposter.
                super().handle_one_request()
                outer.raw.append(getattr(self, "raw_requestline", b""))

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                outer.requests.append((self.command, self.path, dict(self.headers), body))
                self.send_response(302 if redirect else 200)
                if redirect:
                    self.send_header("Location", redirect)
                self.end_headers()
                self.wfile.write(b'{"result":{"name":"test.snapshot"},"version":"1.19.1"}')

            do_GET = do_POST = do_PUT = do_DELETE = respond

            def log_message(self, *args):
                pass

        class Server(http.server.ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

            def handle_error(self, *args):
                pass

        self.server = Server(("127.0.0.1", port), Handler)
        if cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@unittest.skipUnless(shutil.which("zsh") and shutil.which("openssl") and shutil.which("curl"), "zsh/openssl/curl required")
class CutoverTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.cert, cls.key = certificate(cls.directory, "intended")
        cls.foreign_cert, cls.foreign_key = certificate(cls.directory, "imposter")
        cls.wrong_cert, cls.wrong_key = certificate(cls.directory, "wrong-name", "DNS:wrong.invalid")
        cls.expired = cls.directory / "expired.pem"
        subprocess.run([
            "openssl", "x509", "-in", str(cls.cert), "-signkey", str(cls.key),
            "-days", "-1", "-out", str(cls.expired),
        ], check=True, capture_output=True)
        cls.functions = SCRIPT.read_text().split("(( $# )) || { usage; exit 2; }")[0]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_request(self, listener, command, ca=None, use_tls=1, extra_env=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "headers").write_text(f"api-key: {SECRET}\n")
            (path / "qdrant.env").write_text(f"QDRANT__SERVICE__API_KEY={SECRET}\n")
            (path / "private").mkdir()
            program = self.functions + '\nurl=$TEST_URL\ntls_ca=$TEST_CA\nuse_tls=$TEST_TLS\nconfig_dir=$TEST_DIR\nprivate_dir=$TEST_DIR/private\n' + command
            return subprocess.run(["zsh", "-c", program], text=True, capture_output=True, timeout=15,
                env={**os.environ, "TEST_URL": f"https://127.0.0.1:{listener.port}", "TEST_CA": str(ca or self.cert),
                     "TEST_DIR": directory, "TEST_TLS": str(use_tls), **(extra_env or {})})

    def assert_no_secret(self, listener):
        self.assertNotIn(SECRET, repr(listener.requests))
        self.assertNotIn(SECRET.encode(), b"".join(listener.raw))

    def test_original_plaintext_path_exposes_header(self):
        with tempfile.TemporaryDirectory() as directory, Listener() as listener:
            header = Path(directory) / "header"
            header.write_text(f"api-key: {SECRET}\n")
            result = subprocess.run(["curl", "-q", "--noproxy", "*", "-sS", "-m", "2", "-H", f"@{header}",
                f"http://127.0.0.1:{listener.port}/collections"], capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn(SECRET, repr(listener.requests))

    def test_intended_peer_receives_json_and_write_headers(self):
        with Listener(self.cert, self.key) as listener:
            result = self.run_request(listener, 'http_json /collections "$TEST_DIR/headers"; http_code PUT /collections/test "$TEST_DIR/headers" "{}"')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([r[0] for r in listener.requests], ["GET", "PUT"])
            self.assertTrue(all(r[2].get("api-key") == SECRET for r in listener.requests))

    def test_imposters_never_receive_credentials(self):
        for cert, key, ca in ((None, None, self.cert), (self.foreign_cert, self.foreign_key, self.cert),
                              (self.wrong_cert, self.wrong_key, self.wrong_cert), (self.expired, self.key, self.expired)):
            with self.subTest(cert=cert), Listener(cert, key) as listener:
                result = self.run_request(listener, 'http_json /collections "$TEST_DIR/headers"', ca=ca)
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_secret(listener)

    def test_headers_select_tls_even_during_legacy_stage(self):
        with Listener() as listener:
            result = self.run_request(listener, 'http_json /collections "$TEST_DIR/headers"', use_tls=0)
            self.assertNotEqual(result.returncode, 0)
            self.assert_no_secret(listener)

    def test_unrelated_extra_trust_root_cannot_replace_pinned_peer(self):
        with tempfile.TemporaryDirectory() as directory:
            roots = Path(directory)
            shutil.copyfile(self.foreign_cert, roots / "foreign.pem")
            subprocess.run(["openssl", "rehash", str(roots)], check=True, capture_output=True)
            with Listener(self.foreign_cert, self.foreign_key) as listener:
                # Model an additional system trust root. Certificate validation
                # alone accepts it; the independent service-key pin must not.
                before = subprocess.run([
                    "curl", "-q", "--noproxy", "*", "--cacert", str(self.cert),
                    "--capath", str(roots), "-sS", f"https://127.0.0.1:{listener.port}/",
                ], capture_output=True)
                self.assertEqual(before.returncode, 0, before.stderr)
                listener.requests.clear()
                result = self.run_request(listener,
                    'qdrant_curl "$TEST_DIR/headers" /collections --capath "$TEST_EXTRA_ROOTS" -sS -m 2',
                    extra_env={"TEST_EXTRA_ROOTS": str(roots)})
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_secret(listener)

    def test_admin_header_refuses_unverified_peer(self):
        with Listener(self.foreign_cert, self.foreign_key) as listener:
            result = self.run_request(listener, 'admin_header')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TLS identity verification failed", result.stderr)
            self.assertNotIn(SECRET, result.stdout + result.stderr)
            self.assert_no_secret(listener)

    def test_replacement_listener_is_verified_on_next_request(self):
        with Listener(self.cert, self.key) as intended:
            port = intended.port
            result = self.run_request(intended, 'http_json /collections "$TEST_DIR/headers"')
            self.assertEqual(result.returncode, 0, result.stderr)
        with Listener(self.foreign_cert, self.foreign_key, port=port) as replacement:
            result = self.run_request(replacement, 'http_json /collections "$TEST_DIR/headers"')
            self.assertNotEqual(result.returncode, 0)
            self.assert_no_secret(replacement)

    @unittest.skipUnless(shutil.which("jq"), "jq required for snapshot workflow")
    def test_snapshot_create_download_upload_and_cleanup_use_tls(self):
        with Listener(self.cert, self.key) as listener:
            result = self.run_request(listener, 'snapshot_restore_drill "$TEST_DIR/headers"')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([r[0] for r in listener.requests], ["POST", "GET", "POST", "DELETE", "DELETE"])
            self.assertTrue(all(r[2].get("api-key") == SECRET for r in listener.requests))
        with Listener(self.foreign_cert, self.foreign_key) as listener:
            self.assertNotEqual(self.run_request(listener, 'snapshot_restore_drill "$TEST_DIR/headers"').returncode, 0)
            self.assert_no_secret(listener)

    def test_curl_config_proxy_and_redirect_cannot_redirect_credentials(self):
        with tempfile.TemporaryDirectory() as home, Listener() as imposter:
            target = f"http://127.0.0.1:{imposter.port}/capture"
            Path(home, ".curlrc").write_text(f'insecure\nlocation\nurl = "{target}"\n')
            with Listener(self.cert, self.key, redirect=target) as intended:
                result = self.run_request(intended, 'http_json /collections "$TEST_DIR/headers"', extra_env={
                    "CURL_HOME": home, "https_proxy": target, "ALL_PROXY": target, "NO_PROXY": ""})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(intended.requests), 1)
                self.assertEqual(imposter.requests, [])
                self.assert_no_secret(imposter)

    def test_cli_rejects_plaintext_and_ambiguous_origins(self):
        for url in ("http://127.0.0.1:6333", "https://127.0.0.1:6333/path", "https://u@127.0.0.1:6333", "https://127.0.0.1:6333?x", "https://127.0.0.1:99999"):
            result = subprocess.run(["zsh", str(SCRIPT), "verify", "--url", url], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--url must be", result.stderr)


if __name__ == "__main__":
    unittest.main()
