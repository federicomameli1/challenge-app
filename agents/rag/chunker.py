"""Paragraph-based chunking for plain-text and markdown documents."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Chunk:
    """A retrieval unit produced by chunking."""

    text: str
    source: str
    index: int
    metadata: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}#{self.index}"


def chunk_document(text: str, source: str, *, min_chars: int = 40) -> List[Chunk]:
    """Split `text` on blank lines, drop chunks shorter than `min_chars`.

    Blank line = one or more consecutive newlines with only whitespace between.
    Each kept paragraph becomes a Chunk with monotonic index.
    """
    if not text or not text.strip():
        return []

    raw_parts = re.split(r"\n\s*\n+", text)
    chunks: List[Chunk] = []
    index = 0
    for part in raw_parts:
        normalized = part.strip()
        if len(normalized) < min_chars:
            continue
        chunks.append(Chunk(text=normalized, source=source, index=index))
        index += 1
    return chunks


def chunk_directory(
    directory: str,
    *,
    extensions: Sequence[str] = (".txt", ".md"),
    min_chars: int = 40,
    relative_to: Optional[str] = None,
) -> List[Chunk]:
    """Walk `directory` and chunk every file with a matching extension.

    `relative_to` controls how `source` is recorded: if provided, paths are
    rendered relative to that root; otherwise the absolute path is used.
    """
    base = Path(directory)
    if not base.is_dir():
        raise FileNotFoundError(f"Not a directory: {directory}")

    root = Path(relative_to) if relative_to else None
    all_chunks: List[Chunk] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        source = str(path.relative_to(root)) if root else str(path)
        all_chunks.extend(chunk_document(text, source, min_chars=min_chars))
    return all_chunks
