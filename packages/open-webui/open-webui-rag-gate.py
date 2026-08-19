"""Fail-closed readiness gate for the household Open WebUI RAG boundary."""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Any

RAG_UNAVAILABLE_DETAIL = (
    "Document retrieval is temporarily unavailable while its inference "
    "provider is unhealthy."
)
RAG_QUALIFICATION_QUERY = "What color is a clear daytime sky?"
RAG_QUALIFICATION_DOCUMENTS = (
    "A clear daytime sky is blue.",
    "Bananas are yellow.",
)


class RAGUnavailableError(RuntimeError):
    """Stable public failure for a required but unqualified RAG provider."""

    status_code = 503

    def __init__(self) -> None:
        super().__init__(RAG_UNAVAILABLE_DETAIL)


def _finite_score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RAGUnavailableError()
    score = float(value)
    if not math.isfinite(score):
        raise RAGUnavailableError()
    return score


def validate_rerank_scores(scores: Any, document_count: int) -> list[float]:
    """Return exact, finite per-document scores or fail the RAG boundary."""

    if (
        isinstance(document_count, bool)
        or not isinstance(document_count, int)
        or document_count < 1
    ):
        raise RAGUnavailableError()
    if hasattr(scores, "tolist"):
        scores = scores.tolist()
    if not isinstance(scores, Sequence) or isinstance(scores, (str, bytes)):
        raise RAGUnavailableError()
    if len(scores) != document_count:
        raise RAGUnavailableError()
    return [_finite_score(score) for score in scores]


def validate_external_rerank_results(results: Any, document_count: int) -> list[float]:
    """Validate an external response as one finite score for every exact index."""

    if not isinstance(results, list) or len(results) != document_count:
        raise RAGUnavailableError()

    scores_by_index: dict[int, float] = {}
    for result in results:
        if not isinstance(result, dict):
            raise RAGUnavailableError()
        index = result.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise RAGUnavailableError()
        if index < 0 or index >= document_count or index in scores_by_index:
            raise RAGUnavailableError()
        scores_by_index[index] = _finite_score(result.get("relevance_score"))

    if set(scores_by_index) != set(range(document_count)):
        raise RAGUnavailableError()
    return [scores_by_index[index] for index in range(document_count)]


class _RequiredRerankerGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # This package's RAG boundary is mandatory, not an admin option.
        self._required = True
        self._ready = False

    def configure(self, required: bool) -> None:
        if not isinstance(required, bool):
            raise TypeError("required must be a boolean")
        with self._lock:
            # Reconfiguration always invalidates readiness. Passing False must
            # not turn full-context/vector bypasses into an escape hatch.
            self._required = True
            self._ready = False

    def close(self) -> None:
        with self._lock:
            if self._required:
                self._ready = False

    def qualify(self, scores: Any) -> None:
        try:
            validated = validate_rerank_scores(scores, len(RAG_QUALIFICATION_DOCUMENTS))
            if validated[0] <= validated[1]:
                raise RAGUnavailableError()
        except RAGUnavailableError:
            self.close()
            raise

        with self._lock:
            if self._required:
                self._ready = True

    def require(self, reranking_function: Any) -> None:
        with self._lock:
            if not self._required:
                return
            ready = self._ready
        if reranking_function is None or not ready:
            self.close()
            raise RAGUnavailableError()

    def require_mode(
        self,
        reranking_function: Any,
        *,
        full_context: bool,
        hybrid_search: bool,
        bypass_embedding_and_retrieval: bool,
    ) -> None:
        self.require(reranking_function)
        with self._lock:
            required = self._required
        if required and (
            full_context or hybrid_search is not True or bypass_embedding_and_retrieval
        ):
            raise RAGUnavailableError()


_REQUIRED_RERANKER_GATE = _RequiredRerankerGate()


def configure_required_reranker(required: bool) -> None:
    _REQUIRED_RERANKER_GATE.configure(required)


def qualify_required_reranker(scores: Any) -> None:
    _REQUIRED_RERANKER_GATE.qualify(scores)


def close_required_reranker() -> None:
    _REQUIRED_RERANKER_GATE.close()


def require_required_reranker(reranking_function: Any) -> None:
    _REQUIRED_RERANKER_GATE.require(reranking_function)


def require_safe_retrieval_mode(
    reranking_function: Any,
    *,
    full_context: bool = False,
    hybrid_search: bool = True,
    bypass_embedding_and_retrieval: bool = False,
) -> None:
    """Reject modes that would skip the household's required reranker.

    This candidate deliberately disables full-context, non-hybrid, and
    embedding/retrieval-bypass file modes while a reranker is required.  A
    qualified provider makes reranked retrieval available; it does not make
    bypass paths safe.
    """

    _REQUIRED_RERANKER_GATE.require_mode(
        reranking_function,
        full_context=full_context,
        hybrid_search=hybrid_search,
        bypass_embedding_and_retrieval=bypass_embedding_and_retrieval,
    )


def require_file_rag_ready(
    files: Any,
    reranking_function: Any,
    *,
    full_context: bool = False,
    hybrid_search: bool = True,
    bypass_embedding_and_retrieval: bool = False,
) -> None:
    """Guard attached-file chat without affecting an ordinary no-file chat."""

    if not files:
        return
    require_safe_retrieval_mode(
        reranking_function,
        full_context=full_context,
        hybrid_search=hybrid_search,
        bypass_embedding_and_retrieval=bypass_embedding_and_retrieval,
    )
