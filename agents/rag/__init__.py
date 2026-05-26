"""Lightweight RAG primitives shared across agents.

Provides paragraph-based chunking, HuggingFace Inference API embeddings,
and cosine similarity retrieval. Designed to be dependency-free beyond the
Python stdlib so it adds no weight to the container image.
"""

from .chunker import Chunk, chunk_document, chunk_directory
from .hf_embeddings import HFEmbeddingsClient, HFEmbeddingsError
from .retrieval import cosine_similarity, top_k

__all__ = [
    "Chunk",
    "chunk_document",
    "chunk_directory",
    "HFEmbeddingsClient",
    "HFEmbeddingsError",
    "cosine_similarity",
    "top_k",
]
