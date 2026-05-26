"""Cosine similarity retrieval over chunk embeddings.

Pure-Python implementation (no numpy) — keeps the dependency footprint to
zero. For our scale (hundreds of chunks per repo) the overhead is negligible.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .chunker import Chunk


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length vectors.

    Returns 0.0 when either vector has zero norm (degenerate case) instead
    of raising — caller can decide how to interpret.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Vector length mismatch: {len(a)} vs {len(b)}"
        )
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def top_k(
    query_vector: Sequence[float],
    chunks: Sequence[Chunk],
    chunk_vectors: Sequence[Sequence[float]],
    *,
    k: int = 5,
    min_score: float = 0.0,
) -> List[Tuple[Chunk, float]]:
    """Return the top-k chunks ranked by cosine similarity to the query.

    Filters out scores below `min_score`. Ties broken by chunk insertion order.
    """
    if len(chunks) != len(chunk_vectors):
        raise ValueError(
            f"chunks ({len(chunks)}) and chunk_vectors ({len(chunk_vectors)}) length mismatch"
        )
    scored: List[Tuple[Chunk, float]] = []
    for chunk, vec in zip(chunks, chunk_vectors):
        score = cosine_similarity(query_vector, vec)
        if score >= min_score:
            scored.append((chunk, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]
