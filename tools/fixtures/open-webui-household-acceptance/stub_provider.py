#!/usr/bin/env python3
"""Keyless, loopback-only, deterministic Lemonade stand-in for the kit rehearsal.

The rehearsal is kit debugging only: it is never trial evidence.  This stub
serves the Lemonade routes Open WebUI and the scenario module use, with the
v1 deterministic embedding and rerank helpers, so the whole kit can run
without the shared Lemonade.  It requires no key and logs whether any request
carried an Authorization header, plus the first bytes of every embedding
input so the rehearsal can check that Open WebUI applied the settings
prefixes.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import measure_open_webui_household as v1  # noqa: E402

EMBEDDING_MODEL = "zembed-1-Q4_K_M-GGUF-Q4_K_M"
RERANKING_MODEL = "zerank-2-GGUF-Q8_0"
CHAT_MODEL = "household-chat-stub-v1"
MODELS = (EMBEDDING_MODEL, RERANKING_MODEL, CHAT_MODEL)
QUERY_HEAD = "<|im_start|>system\nquery<|im_end|>\n<|im_start|>user\n"
DOCUMENT_HEAD = "<|im_start|>system\ndocument<|im_end|>\n<|im_start|>user\n"
LOGGED_PREFIX_CHARACTERS = 48
MAX_REQUEST_BYTES = 4 * 1024 * 1024
DEFAULT_PORT = 23305


class StubError(ValueError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


def split_head(text: str) -> tuple[str, str]:
    """Return (input_type, text without the zembed head)."""

    if text.startswith(QUERY_HEAD):
        return "query", text[len(QUERY_HEAD) :]
    if text.startswith(DOCUMENT_HEAD):
        return "document", text[len(DOCUMENT_HEAD) :]
    return "document", text


def embeddings(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("model") != EMBEDDING_MODEL:
        raise StubError("unknown embedding model")
    inputs = request.get("input")
    if isinstance(inputs, str):
        inputs = [inputs]
    if not isinstance(inputs, list) or not inputs or not all(isinstance(item, str) for item in inputs):
        raise StubError("input must be a string or a nonempty array of strings")
    data = []
    for index, text in enumerate(inputs):
        input_type, body = split_head(text)
        data.append(
            {
                "object": "embedding",
                "index": index,
                "embedding": v1.deterministic_embedding(body, input_type=input_type),
            }
        )
    return {"object": "list", "model": EMBEDDING_MODEL, "data": data}


def rerank(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("model") != RERANKING_MODEL:
        raise StubError("unknown reranking model")
    query = request.get("query")
    documents = request.get("documents")
    if not isinstance(query, str) or not query:
        raise StubError("query must be a nonempty string")
    if not isinstance(documents, list) or not documents or not all(isinstance(item, str) for item in documents):
        raise StubError("documents must be a nonempty array of strings")
    scored = v1.deterministic_rerank(query, documents)
    top_n = request.get("top_n", len(documents))
    if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= len(documents):
        raise StubError("top_n must select at least one supplied document")
    return {
        "model": RERANKING_MODEL,
        "results": [
            {"index": item["index"], "relevance_score": item["score"]} for item in scored[:top_n]
        ],
    }


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", text) if item.strip()]


def chat_answer(request: dict[str, Any]) -> str:
    """Quote the retrieved-context sentence that best matches the question."""

    if request.get("model") != CHAT_MODEL:
        raise StubError("unknown chat model")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        raise StubError("messages must be a nonempty array")
    contents = [
        (item.get("role"), item["content"])
        for item in messages
        if isinstance(item, dict) and isinstance(item.get("content"), str)
    ]
    users = [content for role, content in contents if role == "user"]
    if not users:
        raise StubError("messages must include a user message")
    everything = "\n".join(content for _, content in contents)
    context = re.search(r"<context>(.*?)</context>", everything, re.DOTALL)
    query = re.search(r"<user_query>(.*?)</user_query>", everything, re.DOTALL)
    if context is not None:
        candidates = re.sub(r"<[^>]+>", "\n", context.group(1))
    else:
        candidates = "\n".join(content for content in (c for _, c in contents) if content is not users[-1])
    question = v1._tokens(query.group(1) if query is not None else users[-1])
    best, best_score = "Synthetic household stub response.", 0
    for sentence in _sentences(candidates):
        score = len(v1._tokens(sentence) & question)
        if score > best_score and not sentence.endswith("?"):
            best, best_score = sentence, score
    return best


def chat_completion(request: dict[str, Any]) -> dict[str, Any]:
    text = chat_answer(request)
    return {
        "id": "chatcmpl-household-stub",
        "object": "chat.completion",
        "created": 0,
        "model": CHAT_MODEL,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": len(text.split()), "total_tokens": len(text.split())},
    }


def chat_events(request: dict[str, Any]) -> Iterable[str]:
    text = chat_answer(request)
    for delta, finish in (({"content": text}, None), ({}, "stop")):
        event = {
            "id": "chatcmpl-household-stub",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": CHAT_MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        yield "data: " + json.dumps(event, separators=(",", ":")) + "\n\n"
    yield "data: [DONE]\n\n"


def model_catalog() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": model, "object": "model", "created": 0, "owned_by": "household-stub"}
            for model in MODELS
        ],
    }


def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "household-stub",
        "all_models_loaded": [{"model_name": model} for model in MODELS],
    }


def log_event(event: dict[str, Any]) -> None:
    print(json.dumps(event, separators=(",", ":"), ensure_ascii=False), file=sys.stderr, flush=True)


class StubRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, status: HTTPStatus, value: Any) -> None:
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _request_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not raw_length.isascii() or not raw_length.isdecimal():
            raise StubError("Content-Length is required", HTTPStatus.LENGTH_REQUIRED)
        if int(raw_length) > MAX_REQUEST_BYTES:
            raise StubError("request body is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            value = json.loads(self.rfile.read(int(raw_length)))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StubError("request body must be JSON") from error
        if not isinstance(value, dict):
            raise StubError("request body must be an object")
        return value

    def _log_request(self, status: int, extra: dict[str, Any] | None = None) -> None:
        log_event(
            {
                "event": "stub_request",
                "method": self.command,
                "path": self.path,
                "status": status,
                "authorization_present": "Authorization" in self.headers,
                **(extra or {}),
            }
        )

    def do_GET(self) -> None:  # noqa: N802
        routes = {"/api/v1/health": health, "/api/v1/models": model_catalog}
        route = routes.get(self.path.split("?", 1)[0])
        if route is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
            self._log_request(HTTPStatus.NOT_FOUND)
            return
        self._json(HTTPStatus.OK, route())
        self._log_request(HTTPStatus.OK)

    def do_POST(self) -> None:  # noqa: N802
        extra: dict[str, Any] = {}
        try:
            request = self._request_json()
            path = self.path.split("?", 1)[0]
            if path == "/api/v1/embeddings":
                inputs = request.get("input")
                extra["input_heads"] = [
                    item[:LOGGED_PREFIX_CHARACTERS]
                    for item in ([inputs] if isinstance(inputs, str) else inputs or [])
                    if isinstance(item, str)
                ]
                self._json(HTTPStatus.OK, embeddings(request))
            elif path == "/api/v1/rerank":
                self._json(HTTPStatus.OK, rerank(request))
            elif path == "/api/v1/chat/completions" and request.get("stream") is True:
                chunks = list(chat_events(request))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                for chunk in chunks:
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
                self.close_connection = True
            elif path == "/api/v1/chat/completions":
                self._json(HTTPStatus.OK, chat_completion(request))
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
                self._log_request(HTTPStatus.NOT_FOUND, extra)
                return
            self._log_request(HTTPStatus.OK, extra)
        except StubError as error:
            self._json(error.status, {"error": {"message": str(error)}})
            self._log_request(error.status, extra)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class _IPv6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "::1"])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        server_class = _IPv6Server if args.host == "::1" else ThreadingHTTPServer
        server = server_class((args.host, args.port), StubRequestHandler)
        server.daemon_threads = True
        log_event({"event": "stub_listening", "port": args.port})
        server.serve_forever(poll_interval=0.1)
        return 0
    except OSError as error:
        print(f"open-webui-household-stub: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
