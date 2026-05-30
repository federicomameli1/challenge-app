"""Tests for agents/rag/ — chunker and cosine retrieval."""

import math
import pytest
from pathlib import Path

from agents.rag.chunker import Chunk, chunk_document, chunk_directory
from agents.rag.retrieval import cosine_similarity, top_k


# ---------------------------------------------------------------------------
# chunk_document
# ---------------------------------------------------------------------------

class TestChunkDocument:
    def test_empty_text_returns_empty(self):
        assert chunk_document("", "src") == []
        assert chunk_document("   \n  ", "src") == []

    def test_single_paragraph(self):
        text = "This is a single paragraph with enough characters to pass the minimum."
        chunks = chunk_document(text, "doc.txt")
        assert len(chunks) == 1
        assert chunks[0].source == "doc.txt"
        assert chunks[0].index == 0

    def test_two_paragraphs_split_on_blank_line(self):
        text = "First paragraph with enough text to not be filtered out.\n\nSecond paragraph is also long enough to pass the minimum threshold."
        chunks = chunk_document(text, "doc.txt")
        assert len(chunks) == 2
        assert chunks[0].index == 0
        assert chunks[1].index == 1

    def test_short_paragraphs_filtered(self):
        text = "Too short.\n\nThis paragraph is long enough to pass the minimum character threshold easily."
        chunks = chunk_document(text, "doc.txt", min_chars=40)
        assert len(chunks) == 1
        assert "long enough" in chunks[0].text

    def test_chunk_id_format(self):
        text = "A" * 50 + "\n\n" + "B" * 50
        chunks = chunk_document(text, "myfile.txt")
        assert chunks[0].id == "myfile.txt#0"
        assert chunks[1].id == "myfile.txt#1"

    def test_chunks_are_stripped(self):
        text = "  \n  Leading spaces paragraph with enough chars  \n  "
        chunks = chunk_document(text, "src", min_chars=10)
        if chunks:
            assert chunks[0].text == chunks[0].text.strip()


class TestChunkDirectory:
    def test_nonexistent_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            chunk_directory("/nonexistent/path/xyz")

    def test_chunks_files_in_directory(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("A" * 100 + "\n\n" + "B" * 100)
        (tmp_path / "b.md").write_text("C" * 100)
        chunks = chunk_directory(str(tmp_path))
        assert len(chunks) >= 3

    def test_ignores_non_matching_extensions(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("A" * 100)
        (tmp_path / "b.py").write_text("# python code\n" + "x = 1\n" * 20)
        chunks = chunk_directory(str(tmp_path), extensions=(".txt",))
        assert all("b.py" not in c.source for c in chunks)

    def test_relative_to_strips_prefix(self, tmp_path: Path):
        (tmp_path / "doc.txt").write_text("A" * 100)
        chunks = chunk_directory(str(tmp_path), relative_to=str(tmp_path))
        assert all(not c.source.startswith(str(tmp_path)) for c in chunks)


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(cosine_similarity(a, b)) < 1e-9

    def test_opposite_vectors_return_minus_one(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-9

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
        assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError, match="length mismatch"):
            cosine_similarity([1.0, 2.0], [1.0])

    def test_result_between_minus_one_and_one(self):
        import random
        rng = random.Random(42)
        a = [rng.gauss(0, 1) for _ in range(64)]
        b = [rng.gauss(0, 1) for _ in range(64)]
        score = cosine_similarity(a, b)
        assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# top_k
# ---------------------------------------------------------------------------

class TestTopK:
    def _make_chunk(self, text: str, idx: int) -> Chunk:
        return Chunk(text=text, source="test", index=idx)

    def test_returns_top_k_chunks(self):
        query = [1.0, 0.0]
        chunks = [self._make_chunk(f"chunk {i}", i) for i in range(5)]
        vecs = [
            [0.9, 0.1],
            [0.1, 0.9],
            [0.8, 0.2],
            [0.2, 0.8],
            [0.95, 0.05],
        ]
        result = top_k(query, chunks, vecs, k=2)
        assert len(result) == 2
        assert result[0][1] >= result[1][1]

    def test_min_score_filters(self):
        query = [1.0, 0.0]
        chunks = [self._make_chunk("a", 0), self._make_chunk("b", 1)]
        vecs = [[0.1, 0.9], [0.9, 0.1]]
        result = top_k(query, chunks, vecs, k=5, min_score=0.8)
        assert len(result) == 1
        assert result[0][0].index == 1

    def test_mismatched_chunks_and_vectors_raise(self):
        chunks = [self._make_chunk("a", 0)]
        vecs = [[1.0, 0.0], [0.0, 1.0]]
        with pytest.raises(ValueError):
            top_k([1.0, 0.0], chunks, vecs)

    def test_results_sorted_descending(self):
        query = [1.0, 0.0]
        chunks = [self._make_chunk(f"c{i}", i) for i in range(4)]
        vecs = [[0.5, 0.5], [0.9, 0.1], [0.1, 0.9], [0.7, 0.3]]
        result = top_k(query, chunks, vecs, k=4)
        scores = [r[1] for r in result]
        assert scores == sorted(scores, reverse=True)
