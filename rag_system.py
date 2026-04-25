"""
rag_system.py
TF-IDF retrieval engine over the pet care knowledge base.
Supports optional extra .txt sources from a knowledge_sources/ directory.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class KnowledgeChunk:
    id: str
    tags: list[str]
    title: str
    content: str
    score: float = field(default=0.0)


def load_knowledge_base(kb_path: str | Path | None = None) -> list[dict[str, Any]]:
    if kb_path is None:
        kb_path = Path(__file__).parent / "pet_care_kb.json"
    kb_path = Path(kb_path)
    if not kb_path.exists():
        raise FileNotFoundError(
            f"Knowledge base not found at {kb_path}. "
            "Ensure pet_care_kb.json is in the project directory."
        )
    with open(kb_path, encoding="utf-8") as f:
        chunks = json.load(f)
    if not isinstance(chunks, list):
        raise ValueError("pet_care_kb.json must be a JSON array.")
    required = {"id", "tags", "title", "content"}
    for chunk in chunks:
        missing = required - set(chunk.keys())
        if missing:
            raise ValueError(f"Chunk '{chunk.get('id', '?')}' is missing fields: {missing}")
    return chunks


class PetCareRetriever:
    """TF-IDF retrieval engine. Fit once at construction; reuse retrieve() per query."""

    TAG_BONUS: float = 0.15
    DEFAULT_TOP_K: int = 4

    def __init__(self, chunks: list[dict[str, Any]], *, tag_bonus: float = TAG_BONUS) -> None:
        self._chunks = chunks
        self._tag_bonus = tag_bonus
        self._vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        corpus = [c["content"] for c in chunks]
        self._tfidf_matrix = self._vectorizer.fit_transform(corpus)
        self._tags_lower: list[list[str]] = [
            [t.lower() for t in c["tags"]] for c in chunks
        ]

    def retrieve(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> list[KnowledgeChunk]:
        if not query.strip():
            return []
        query_vec = self._vectorizer.transform([query])
        cosine_scores = cosine_similarity(query_vec, self._tfidf_matrix).flatten()
        query_lower = query.lower()
        final_scores = np.array([
            cosine_scores[i] + self._compute_tag_bonus(query_lower, self._tags_lower[i])
            for i in range(len(self._chunks))
        ])
        top_k = min(top_k, len(self._chunks))
        top_indices = np.argsort(final_scores)[::-1][:top_k]
        return [
            KnowledgeChunk(
                id=self._chunks[i]["id"],
                tags=self._chunks[i]["tags"],
                title=self._chunks[i]["title"],
                content=self._chunks[i]["content"],
                score=float(final_scores[i]),
            )
            for i in top_indices
        ]

    def _compute_tag_bonus(self, query_lower: str, chunk_tags: list[str]) -> float:
        return sum(
            self._tag_bonus for tag in chunk_tags if tag in query_lower
        )


def load_extra_sources(directory: str | Path) -> list[dict[str, Any]]:
    """
    Load all .txt files in `directory` as additional knowledge chunks.
    Each file becomes one chunk; tags and title are derived from the filename.
    Content is truncated to 500 words.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    chunks = []
    for txt_file in sorted(directory.glob("*.txt")):
        stem = txt_file.stem
        words = re.split(r"[-_]", stem)
        tags = [w.lower() for w in words if w]
        title = " ".join(w.capitalize() for w in words if w)
        content = txt_file.read_text(encoding="utf-8").strip()
        content_words = content.split()
        if len(content_words) > 500:
            content = " ".join(content_words[:500])
        chunks.append({
            "id": f"extra-{stem}",
            "tags": tags,
            "title": title,
            "content": content,
        })
    return chunks


_retriever: PetCareRetriever | None = None
_loaded_extra_dir: str | None = None


def get_retriever(
    kb_path: str | Path | None = None,
    extra_sources_dir: str | Path | None = None,
) -> PetCareRetriever:
    """
    Module-level singleton. Re-fits if extra_sources_dir changes.
    Auto-discovers a knowledge_sources/ directory next to the KB file.
    """
    global _retriever, _loaded_extra_dir

    # Auto-discover knowledge_sources/ next to the KB file
    if extra_sources_dir is None:
        kb = Path(kb_path) if kb_path else Path(__file__).parent / "pet_care_kb.json"
        default_extra = kb.parent / "knowledge_sources"
        if default_extra.is_dir():
            extra_sources_dir = default_extra

    extra_key = str(extra_sources_dir) if extra_sources_dir else None

    if _retriever is None or _loaded_extra_dir != extra_key:
        chunks = load_knowledge_base(kb_path)
        if extra_sources_dir:
            extra = load_extra_sources(extra_sources_dir)
            chunks = chunks + extra
        _retriever = PetCareRetriever(chunks)
        _loaded_extra_dir = extra_key

    return _retriever
