#!/usr/bin/env python3
"""Narrow measurement-only provider for the Open WebUI household fixture.

This sidecar is not a production inference gateway.  It adapts the exact
zembed and zerank wire contracts to two fixed, loopback-only llama.cpp
backends and supplies a deterministic chat model for transport measurements.
"""

from __future__ import annotations

import argparse
import hmac
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable


EMBEDDING_MODEL = "zembed-1-Q4_K_M-GGUF-Q4_K_M"
RERANKING_MODEL = "zerank-2-GGUF-Q8_0"
CHAT_MODEL = "household-chat-measurement-v1"
EMBEDDING_DIMENSIONS = 2560
ZERANK_YES_TOKEN_ID = 9454
ZERANK_LOGIT_SCALE = 5.0
MAX_REQUEST_BYTES = 4 * 1024 * 1024
LONG_RESPONSE_BYTES = 256 * 1024
STREAM_CHUNK_CHARACTERS = 4 * 1024

BackendCall = Callable[[str, dict[str, Any]], dict[str, Any]]


class ProviderError(ValueError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, request, response, code, message, headers):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "fixed inference backend redirects are disabled",
            headers,
            response,
        )

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderError(f"{name} must be a nonempty string")
    return value


def format_zembed_input(text: str, input_type: str) -> str:
    text = _required_string(text, "embedding input")
    if input_type not in {"query", "document"}:
        raise ProviderError("input_type must be query or document")
    return (
        f"<|im_start|>system\n{input_type}<|im_end|>\n"
        f"<|im_start|>user\n{text}<|im_end|>\n"
    )


def _finite_vector(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != EMBEDDING_DIMENSIONS:
        raise ProviderError("embedding backend returned the wrong dimensions", HTTPStatus.BAD_GATEWAY)
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ProviderError("embedding backend returned a non-finite vector", HTTPStatus.BAD_GATEWAY)
        vector.append(float(item))
    return vector


def adapt_embeddings(request: dict[str, Any], backend: BackendCall) -> dict[str, Any]:
    if request.get("model") != EMBEDDING_MODEL:
        raise ProviderError("unknown embedding model")
    input_type = request.get("input_type")
    inputs = request.get("input")
    if isinstance(inputs, str):
        inputs = [inputs]
    if not isinstance(inputs, list) or len(inputs) != 1:
        raise ProviderError("the measurement contract requires embedding batch size 1")
    formatted = [format_zembed_input(inputs[0], input_type)]
    response = backend(
        "/v1/embeddings",
        {"model": EMBEDDING_MODEL, "input": formatted},
    )
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ProviderError("embedding backend returned malformed data", HTTPStatus.BAD_GATEWAY)
    vector = _finite_vector(data[0].get("embedding"))
    result = {
        "object": "list",
        "model": EMBEDDING_MODEL,
        "data": [{"object": "embedding", "index": 0, "embedding": vector}],
    }
    usage = response.get("usage")
    if isinstance(usage, dict):
        result["usage"] = usage
    return result


def format_zerank_prompt(query: str, document: str) -> str:
    return (
        f"<|im_start|>system\n{_required_string(query, 'query')}<|im_end|>\n"
        f"<|im_start|>user\n{_required_string(document, 'document')}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _selected_yes_logit(response: Any) -> float:
    values = response.get("token_logits") if isinstance(response, dict) else None
    if not isinstance(values, list):
        raise ProviderError("zerank backend omitted token_logits", HTTPStatus.BAD_GATEWAY)
    for item in values:
        if not isinstance(item, dict) or item.get("id") != ZERANK_YES_TOKEN_ID:
            continue
        logit = item.get("logit")
        if isinstance(logit, bool) or not isinstance(logit, (int, float)) or not math.isfinite(logit):
            raise ProviderError("zerank backend returned a non-finite Yes logit", HTTPStatus.BAD_GATEWAY)
        return float(logit)
    raise ProviderError("zerank backend omitted the selected Yes token", HTTPStatus.BAD_GATEWAY)


def adapt_rerank(request: dict[str, Any], backend: BackendCall) -> dict[str, Any]:
    if request.get("model") != RERANKING_MODEL:
        raise ProviderError("unknown reranking model")
    query = _required_string(request.get("query"), "query")
    documents = request.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ProviderError("documents must be a nonempty array")
    if len(documents) > 128:
        raise ProviderError("too many reranking documents")
    top_n = request.get("top_n", len(documents))
    if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= len(documents):
        raise ProviderError("top_n must select at least one supplied document")

    scored: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        prompt = format_zerank_prompt(query, document)
        response = backend(
            "/completion",
            {
                "prompt": prompt,
                "n_predict": 1,
                "temperature": 0,
                "token_logits": [ZERANK_YES_TOKEN_ID],
            },
        )
        logit = _selected_yes_logit(response)
        scaled_logit = logit / ZERANK_LOGIT_SCALE
        if scaled_logit >= 0:
            relevance_score = 1.0 / (1.0 + math.exp(-scaled_logit))
        else:
            scaled_exponential = math.exp(scaled_logit)
            relevance_score = scaled_exponential / (1.0 + scaled_exponential)
        scored.append(
            {
                "index": index,
                "raw_logit": logit,
                "relevance_score": relevance_score,
            }
        )
    scored.sort(key=lambda item: (-item["raw_logit"], item["index"]))
    return {
        "model": RERANKING_MODEL,
        "results": [
            {"index": item["index"], "relevance_score": item["relevance_score"]}
            for item in scored[:top_n]
        ],
    }


def _chat_text(request: dict[str, Any]) -> str:
    if request.get("model") != CHAT_MODEL:
        raise ProviderError("unknown chat model")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ProviderError("messages must be a nonempty array")
    user_messages = [
        item.get("content")
        for item in messages
        if isinstance(item, dict) and item.get("role") == "user" and isinstance(item.get("content"), str)
    ]
    if not user_messages:
        raise ProviderError("messages must include a user message")
    if "long response measurement" in user_messages[-1].lower():
        return "L" * LONG_RESPONSE_BYTES
    if "seed cabinet" in user_messages[-1].lower():
        return "The brass key opens the seed cabinet. [1]"
    return "Synthetic household transport response."


def chat_completion(request: dict[str, Any]) -> dict[str, Any]:
    text = _chat_text(request)
    return {
        "id": "chatcmpl-household-measurement",
        "object": "chat.completion",
        "created": 0,
        "model": CHAT_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": len(text.split()), "total_tokens": len(text.split())},
    }


def chat_completion_events(request: dict[str, Any]) -> Iterable[str]:
    text = _chat_text(request)
    yield from _chat_completion_events_for_text(text)


def _chat_completion_events_for_text(text: str) -> Iterable[str]:
    for offset in range(0, len(text), STREAM_CHUNK_CHARACTERS):
        content = text[offset : offset + STREAM_CHUNK_CHARACTERS]
        event = {
            "id": "chatcmpl-household-measurement",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": CHAT_MODEL,
            "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
        }
        yield "data: " + json.dumps(event, separators=(",", ":")) + "\n\n"
    final = {
        "id": "chatcmpl-household-measurement",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": CHAT_MODEL,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield "data: " + json.dumps(final, separators=(",", ":")) + "\n\n"
    yield "data: [DONE]\n\n"


def _backend(base_url: str, timeout: float) -> BackendCall:
    try:
        parsed = urllib.parse.urlsplit(base_url)
        port = parsed.port
    except ValueError as error:
        raise ProviderError("backend URL must be an explicit loopback HTTP endpoint") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderError("backend URL must be an explicit loopback HTTP endpoint")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ProviderError("backend timeout must be a positive finite number")
    host = f"[{parsed.hostname}]" if parsed.hostname == "::1" else parsed.hostname
    base_url = f"http://{host}:{port}"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectRedirects(),
    )

    def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            error.close()
            raise ProviderError(
                f"fixed inference backend failed: {error}",
                HTTPStatus.BAD_GATEWAY,
            ) from error
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise ProviderError(f"fixed inference backend failed: {error}", HTTPStatus.BAD_GATEWAY) from error
        if not isinstance(result, dict):
            raise ProviderError("fixed inference backend returned non-object JSON", HTTPStatus.BAD_GATEWAY)
        return result

    return post


def model_catalog() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": CHAT_MODEL,
                "object": "model",
                "created": 0,
                "owned_by": "household-measurement",
            }
        ],
    }


class ProviderHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        api_key: str,
        embedding_backend: BackendCall,
        reranking_backend: BackendCall,
    ):
        super().__init__(address, ProviderRequestHandler)
        self.api_key = api_key
        self.embedding_backend = embedding_backend
        self.reranking_backend = reranking_backend


class ProviderRequestHandler(BaseHTTPRequestHandler):
    server: ProviderHTTPServer
    protocol_version = "HTTP/1.1"

    def _json_response(self, status: HTTPStatus, value: Any) -> None:
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = "Bearer " + self.server.api_key
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied.encode(), expected.encode())

    def _require_authorized(self) -> bool:
        if self._authorized():
            return True
        self._json_response(HTTPStatus.UNAUTHORIZED, {"error": {"message": "unauthorized"}})
        return False

    def _request_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not raw_length.isascii() or not raw_length.isdecimal():
            raise ProviderError("Content-Length is required", HTTPStatus.LENGTH_REQUIRED)
        length = int(raw_length)
        if length > MAX_REQUEST_BYTES:
            raise ProviderError("request body is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("request body must be JSON") from error
        if not isinstance(value, dict):
            raise ProviderError("request body must be an object")
        return value

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json_response(
                HTTPStatus.OK,
                {"status": "ok", "shape": "measurement-only-fixed-provider"},
            )
            return
        if self.path == "/v1/models" and self._require_authorized():
            self._json_response(HTTPStatus.OK, model_catalog())
            return
        if self.path != "/v1/models":
            self._json_response(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_authorized():
            return
        try:
            request = self._request_json()
            if self.path == "/v1/embeddings":
                self._json_response(
                    HTTPStatus.OK,
                    adapt_embeddings(request, self.server.embedding_backend),
                )
            elif self.path == "/v1/rerank":
                self._json_response(
                    HTTPStatus.OK,
                    adapt_rerank(request, self.server.reranking_backend),
                )
            elif self.path == "/v1/chat/completions":
                if request.get("stream") is True:
                    text = _chat_text(request)
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache, no-store")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for event in _chat_completion_events_for_text(text):
                        self.wfile.write(event.encode())
                        self.wfile.flush()
                else:
                    self._json_response(HTTPStatus.OK, chat_completion(request))
            else:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
        except ProviderError as error:
            self._json_response(error.status, {"error": {"message": str(error)}})

    def log_request(self, code: int | str = "-", _size: int | str = "-") -> None:
        print(
            json.dumps(
                {
                    "event": "provider_request",
                    "method": self.command,
                    "path": self.path,
                    "status": int(code) if isinstance(code, int) else code,
                },
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "::1"])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--embedding-backend", required=True)
    parser.add_argument("--reranking-backend", required=True)
    parser.add_argument("--backend-timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        api_key = args.api_key_file.read_text(encoding="utf-8").strip()
        if not api_key:
            raise ValueError("API key file must be nonempty")
        server = ProviderHTTPServer(
            (args.host, args.port),
            api_key,
            _backend(args.embedding_backend, args.backend_timeout),
            _backend(args.reranking_backend, args.backend_timeout),
        )
        server.serve_forever(poll_interval=0.1)
        return 0
    except (OSError, ValueError) as error:
        print(f"open-webui-household-provider: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
