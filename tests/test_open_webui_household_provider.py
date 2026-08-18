import contextlib
import importlib.util
import io
import json
import math
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER = REPO_ROOT / "tools" / "fixtures" / "open-webui-household" / "provider.py"


def load_provider():
    spec = importlib.util.spec_from_file_location("open_webui_household_provider", PROVIDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load household provider fixture")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def probe_handler(status=200, headers=None, body=b"{}"):
    class ProbeHandler(BaseHTTPRequestHandler):
        hits = []

        def _respond(self):
            self.__class__.hits.append((self.command, self.path))
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _respond
        do_POST = _respond

        def log_message(self, _format, *_args):
            return

    return ProbeHandler


@contextlib.contextmanager
def running_probe(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class OpenWebUIHouseholdProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = load_provider()

    def test_zembed_formats_query_and_document_with_the_exact_suffix(self):
        self.assertEqual(
            self.provider.format_zembed_input("question", "query"),
            "<|im_start|>system\nquery<|im_end|>\n"
            "<|im_start|>user\nquestion<|im_end|>\n",
        )
        self.assertEqual(
            self.provider.format_zembed_input("passage", "document"),
            "<|im_start|>system\ndocument<|im_end|>\n"
            "<|im_start|>user\npassage<|im_end|>\n",
        )
        with self.assertRaises(self.provider.ProviderError):
            self.provider.format_zembed_input("passage", "unexpected")

    def test_model_catalog_exposes_only_the_chat_model(self):
        server = self.provider.ProviderHTTPServer(
            ("127.0.0.1", 0),
            "fixture-key",
            lambda _path, _payload: {},
            lambda _path, _payload: {},
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logs = io.StringIO()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/v1/models",
                headers={"Authorization": "Bearer fixture-key"},
            )
            with (
                contextlib.redirect_stderr(logs),
                urllib.request.urlopen(request, timeout=5) as response,
            ):
                catalog = json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(catalog["object"], "list")
        self.assertEqual(
            [model["id"] for model in catalog["data"]],
            [self.provider.CHAT_MODEL],
        )
        self.assertNotIn(self.provider.EMBEDDING_MODEL, json.dumps(catalog))
        self.assertNotIn(self.provider.RERANKING_MODEL, json.dumps(catalog))
        self.assertEqual(json.loads(logs.getvalue())["status"], 200)

    def test_backend_targets_are_restricted_to_explicit_loopback_http(self):
        for target in (
            "https://example.com",
            "http://192.168.1.2:8080",
            "http://localhost:8080",
            "http://127.0.0.1:8080/unexpected",
            "http://user:password@127.0.0.1:8080",
        ):
            with self.subTest(target=target):
                with self.assertRaises(self.provider.ProviderError):
                    self.provider._backend(target, 1.0)

        self.assertTrue(callable(self.provider._backend("http://127.0.0.1:8080", 1.0)))
        self.assertTrue(callable(self.provider._backend("http://[::1]:8080", 1.0)))

    def test_backend_calls_reject_redirects_and_ignore_proxy_environment(self):
        redirect_target = probe_handler()
        with running_probe(redirect_target) as target_server:
            redirect_source = probe_handler(
                status=302,
                headers={
                    "Location": (
                        f"http://127.0.0.1:{target_server.server_port}/escaped"
                    )
                },
            )
            with running_probe(redirect_source) as source_server:
                backend = self.provider._backend(
                    f"http://127.0.0.1:{source_server.server_port}", 1.0
                )
                with self.assertRaises(self.provider.ProviderError):
                    backend("/v1/embeddings", {})
        self.assertEqual(redirect_source.hits, [("POST", "/v1/embeddings")])
        self.assertEqual(redirect_target.hits, [])

        direct_target = probe_handler(status=503)
        proxy_target = probe_handler()
        with running_probe(direct_target) as direct_server, running_probe(
            proxy_target
        ) as proxy_server:
            proxy_url = f"http://127.0.0.1:{proxy_server.server_port}"
            with mock.patch.dict(
                os.environ,
                {
                    "http_proxy": proxy_url,
                    "HTTP_PROXY": proxy_url,
                    "no_proxy": "",
                    "NO_PROXY": "",
                },
            ):
                backend = self.provider._backend(
                    f"http://127.0.0.1:{direct_server.server_port}", 1.0
                )
                with self.assertRaises(self.provider.ProviderError):
                    backend("/v1/embeddings", {})
        self.assertEqual(direct_target.hits, [("POST", "/v1/embeddings")])
        self.assertEqual(proxy_target.hits, [])

    def test_embedding_adapter_binds_model_batch_and_backend_shape(self):
        seen = []

        def backend(path, payload):
            seen.append((path, payload))
            return {
                "data": [
                    {
                        "embedding": [1.0] + [0.0] * 2559,
                        "index": 0,
                        "object": "embedding",
                    }
                ],
                "usage": {"prompt_tokens": 9, "total_tokens": 9},
            }

        result = self.provider.adapt_embeddings(
            {
                "model": self.provider.EMBEDDING_MODEL,
                "input": ["Which key?"],
                "input_type": "query",
            },
            backend,
        )

        self.assertEqual(seen[0][0], "/v1/embeddings")
        self.assertEqual(
            seen[0][1]["input"],
            [
                "<|im_start|>system\nquery<|im_end|>\n"
                "<|im_start|>user\nWhich key?<|im_end|>\n"
            ],
        )
        self.assertEqual(result["model"], self.provider.EMBEDDING_MODEL)
        self.assertEqual(len(result["data"][0]["embedding"]), 2560)

        for mutation in (
            {"model": "wrong", "input": ["x"], "input_type": "query"},
            {"model": self.provider.EMBEDDING_MODEL, "input": ["a", "b"], "input_type": "query"},
            {"model": self.provider.EMBEDDING_MODEL, "input": ["x"], "input_type": "wrong"},
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(self.provider.ProviderError):
                    self.provider.adapt_embeddings(mutation, backend)

    def test_zerank_adapter_uses_selected_yes_logit_and_sigmoid_scale(self):
        logits = iter([-6.0, 17.0, -9.0])
        calls = []

        def backend(path, payload):
            calls.append((path, payload))
            return {
                "token_logits": [
                    {"id": self.provider.ZERANK_YES_TOKEN_ID, "token": "Yes", "logit": next(logits)}
                ]
            }

        result = self.provider.adapt_rerank(
            {
                "model": self.provider.RERANKING_MODEL,
                "query": "capital of France",
                "documents": [
                    "Berlin is the capital of Germany.",
                    "Paris is the capital of France.",
                    "A seed catalog.",
                ],
                "top_n": 3,
            },
            backend,
        )

        self.assertEqual([item["index"] for item in result["results"]], [1, 0, 2])
        self.assertAlmostEqual(result["results"][0]["relevance_score"], 1 / (1 + math.exp(-17 / 5)))
        self.assertTrue(all(path == "/completion" for path, _ in calls))
        self.assertTrue(all(call[1]["token_logits"] == [9454] for call in calls))
        self.assertEqual(
            calls[1][1]["prompt"],
            "<|im_start|>system\ncapital of France<|im_end|>\n"
            "<|im_start|>user\nParis is the capital of France.<|im_end|>\n"
            "<|im_start|>assistant\n",
        )

    def test_zerank_adapter_rejects_malformed_backend_and_nonfinite_scores(self):
        request = {
            "model": self.provider.RERANKING_MODEL,
            "query": "query",
            "documents": ["document"],
        }
        for response in (
            {},
            {"token_logits": "wrong"},
            {"token_logits": [{"id": 1, "logit": 3.0}]},
            {"token_logits": [{"id": 9454, "logit": float("nan")}]},
        ):
            with self.subTest(response=response):
                with self.assertRaises(self.provider.ProviderError):
                    self.provider.adapt_rerank(
                        request,
                        lambda _path, _payload, response=response: response,
                    )

    def test_zerank_adapter_maps_extreme_finite_logits_without_overflow(self):
        request = {
            "model": self.provider.RERANKING_MODEL,
            "query": "query",
            "documents": ["document"],
        }

        for logit, expected in ((-1e308, 0.0), (1e308, 1.0)):
            with self.subTest(logit=logit):
                result = self.provider.adapt_rerank(
                    request,
                    lambda _path, _payload, logit=logit: {
                        "token_logits": [
                            {
                                "id": self.provider.ZERANK_YES_TOKEN_ID,
                                "token": "Yes",
                                "logit": logit,
                            }
                        ]
                    },
                )
                self.assertEqual(result["results"][0]["relevance_score"], expected)

    def test_deterministic_chat_supports_normal_and_streaming_transport(self):
        request = {
            "model": self.provider.CHAT_MODEL,
            "messages": [{"role": "user", "content": "Which key opens the seed cabinet?"}],
        }
        normal = self.provider.chat_completion(request)
        self.assertEqual(normal["choices"][0]["message"]["content"], "The brass key opens the seed cabinet. [1]")

        events = list(self.provider.chat_completion_events({**request, "stream": True}))
        self.assertTrue(events[0].startswith("data: "))
        self.assertEqual(events[-1], "data: [DONE]\n\n")
        streamed = "".join(
            json.loads(event.removeprefix("data: ").strip())["choices"][0]["delta"].get(
                "content", ""
            )
            for event in events[:-1]
        )
        self.assertIn("brass key", streamed)

    def test_deterministic_chat_exposes_a_bounded_long_response_probe(self):
        request = {
            "model": self.provider.CHAT_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "Run the long response measurement.",
                }
            ],
        }

        normal = self.provider.chat_completion(request)
        text = normal["choices"][0]["message"]["content"]
        self.assertEqual(len(text.encode()), self.provider.LONG_RESPONSE_BYTES)

        events = list(self.provider.chat_completion_events({**request, "stream": True}))
        streamed = "".join(
            json.loads(event.removeprefix("data: ").strip())["choices"][0]["delta"].get(
                "content", ""
            )
            for event in events[:-1]
        )
        self.assertEqual(streamed, text)
        self.assertGreater(len(events), 2)

    def test_invalid_streaming_chat_is_rejected_before_success_headers(self):
        server = self.provider.ProviderHTTPServer(
            ("127.0.0.1", 0),
            "fixture-key",
            lambda _path, _payload: {},
            lambda _path, _payload: {},
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logs = io.StringIO()
        try:
            body = json.dumps(
                {
                    "model": "unexpected-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                }
            ).encode()
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": "Bearer fixture-key",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with (
                contextlib.redirect_stderr(logs),
                self.assertRaises(urllib.error.HTTPError) as raised,
            ):
                urllib.request.urlopen(request, timeout=5)
            try:
                error_body = json.load(raised.exception)
            finally:
                raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(error_body["error"]["message"], "unknown chat model")
        request_logs = [json.loads(line) for line in logs.getvalue().splitlines()]
        self.assertEqual([entry["status"] for entry in request_logs], [400])


if __name__ == "__main__":
    unittest.main()
