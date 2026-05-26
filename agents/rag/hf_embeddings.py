"""HuggingFace Inference API client for sentence embeddings.

Configuration (environment variables):
    HUGGINGFACE_TOKEN     — required for non-trivial usage (free tier needs auth)
    HF_EMBEDDING_MODEL    — model id (default: sentence-transformers/all-MiniLM-L6-v2)
    HF_INFERENCE_BASE_URL — override base URL
    HF_INFERENCE_TIMEOUT  — HTTP timeout seconds (default: 30)

Usage:
    client = HFEmbeddingsClient.from_env()
    if client:
        vectors = client.embed_texts(["hello", "world"])
        # vectors is List[List[float]] of shape (N, D)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# HF migrated the Inference API to a router-based endpoint. The
# legacy api-inference.huggingface.co subdomain was deprecated and
# no longer resolves from many networks (including GH Actions runners).
_DEFAULT_BASE_URL = "https://router.huggingface.co/hf-inference/models"
_DEFAULT_TIMEOUT = 30


class HFEmbeddingsError(Exception):
    """Raised when the HuggingFace embeddings call fails."""


class HFEmbeddingsClient:
    """Thin wrapper around the HF Inference API feature-extraction pipeline."""

    def __init__(
        self,
        token: str,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        if not token:
            raise HFEmbeddingsError("HUGGINGFACE_TOKEN is required")
        self.token = token
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> Optional["HFEmbeddingsClient"]:
        token = (os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
        if not token:
            logger.warning("HUGGINGFACE_TOKEN not set; embeddings disabled")
            return None
        model = (os.environ.get("HF_EMBEDDING_MODEL") or _DEFAULT_MODEL).strip()
        base_url = (
            os.environ.get("HF_INFERENCE_BASE_URL") or _DEFAULT_BASE_URL
        ).strip()
        timeout_raw = os.environ.get("HF_INFERENCE_TIMEOUT")
        try:
            timeout = int(timeout_raw) if timeout_raw else _DEFAULT_TIMEOUT
        except ValueError:
            timeout = _DEFAULT_TIMEOUT
        return cls(token=token, model=model, base_url=base_url, timeout=timeout)

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a batch of texts. Returns one vector per input text.

        HF feature-extraction returns either:
          - a single vector (1D) when given a single string
          - a list of vectors (2D) when given a list of strings
          - a list of token-level matrices (3D) for some models
        We normalize all of these to a clean 2D list-of-lists.
        """
        if not texts:
            return []

        url = f"{self.base_url}/{self.model}/pipeline/feature-extraction"
        payload = json.dumps(
            {
                "inputs": list(texts),
                "options": {"wait_for_model": True},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise HFEmbeddingsError(
                f"HF API HTTP {exc.code}: {body[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise HFEmbeddingsError(f"HF API network error: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HFEmbeddingsError(f"HF API non-JSON response: {raw[:300]}") from exc

        return _normalize_vectors(data, n_inputs=len(texts))


def _normalize_vectors(data: object, n_inputs: int) -> List[List[float]]:
    """Coerce HF response into a (n_inputs, D) list-of-lists.

    HF feature-extraction can return 1D / 2D / 3D depending on model.
    For sentence-transformers models we expect 2D; for raw token-level
    models we mean-pool the token matrix to get a sentence vector.
    """
    if not isinstance(data, list):
        raise HFEmbeddingsError(f"Unexpected HF response shape: {type(data).__name__}")

    if not data:
        return []

    # 1D: single vector (was given a single input). Wrap it.
    if isinstance(data[0], (int, float)):
        if n_inputs != 1:
            raise HFEmbeddingsError(
                f"HF returned a single vector but {n_inputs} inputs were sent"
            )
        return [[float(x) for x in data]]

    # 2D: list of vectors, one per input.
    if isinstance(data[0], list) and (not data[0] or isinstance(data[0][0], (int, float))):
        return [[float(x) for x in vec] for vec in data]

    # 3D: list of token matrices, one per input → mean pool.
    if isinstance(data[0], list) and isinstance(data[0][0], list):
        pooled: List[List[float]] = []
        for token_matrix in data:
            if not token_matrix:
                pooled.append([])
                continue
            dim = len(token_matrix[0])
            sums = [0.0] * dim
            for token_vec in token_matrix:
                for i, v in enumerate(token_vec):
                    sums[i] += float(v)
            n = len(token_matrix)
            pooled.append([s / n for s in sums])
        return pooled

    raise HFEmbeddingsError("Unexpected HF response: nested structure not recognized")
