"""
tests/test_rag.py
Unit tests for the RAG retrieval system.
"""
import pytest
from pathlib import Path

import rag_system
from rag_system import load_knowledge_base, load_extra_sources, PetCareRetriever, get_retriever, KnowledgeChunk


KB_PATH = Path(__file__).parent.parent / "pet_care_kb.json"


# ── load_knowledge_base ───────────────────────────────────────────────────────

def test_knowledge_base_loads_successfully():
    chunks = load_knowledge_base(KB_PATH)
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_knowledge_base_has_39_chunks():
    chunks = load_knowledge_base(KB_PATH)
    assert len(chunks) == 39


def test_every_chunk_has_required_fields():
    chunks = load_knowledge_base(KB_PATH)
    required = {"id", "tags", "title", "content"}
    for chunk in chunks:
        assert required.issubset(chunk.keys()), f"Chunk missing fields: {chunk.get('id')}"


def test_all_chunk_ids_are_unique():
    chunks = load_knowledge_base(KB_PATH)
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"


def test_load_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        load_knowledge_base("/nonexistent/path/kb.json")


# ── PetCareRetriever ──────────────────────────────────────────────────────────

@pytest.fixture
def retriever():
    chunks = load_knowledge_base(KB_PATH)
    return PetCareRetriever(chunks)


def test_retriever_returns_correct_count(retriever):
    results = retriever.retrieve("dog exercise", top_k=4)
    assert len(results) == 4


def test_retriever_returns_knowledge_chunks(retriever):
    results = retriever.retrieve("cat enrichment")
    assert all(isinstance(r, KnowledgeChunk) for r in results)


def test_retriever_scores_are_non_negative(retriever):
    results = retriever.retrieve("senior dog arthritis")
    assert all(r.score >= 0 for r in results)


def test_retriever_finds_arthritis_chunks(retriever):
    results = retriever.retrieve("senior dog arthritis joint pain", top_k=4)
    titles_lower = [r.title.lower() for r in results]
    assert any("arthritis" in t or "joint" in t for t in titles_lower)


def test_retriever_finds_medication_chunks(retriever):
    results = retriever.retrieve("dog medication timing meal", top_k=4)
    titles_lower = [r.title.lower() for r in results]
    assert any("medic" in t or "timing" in t for t in titles_lower)


def test_retriever_finds_cat_enrichment(retriever):
    results = retriever.retrieve("indoor cat enrichment anxiety", top_k=4)
    titles_lower = [r.title.lower() for r in results]
    assert any("cat" in t or "enrichment" in t for t in titles_lower)


def test_retriever_results_ordered_by_score(retriever):
    results = retriever.retrieve("dog dental hygiene brushing", top_k=5)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retriever_empty_query_returns_empty(retriever):
    results = retriever.retrieve("")
    assert results == []


def test_retriever_respects_top_k(retriever):
    for k in [1, 2, 3]:
        results = retriever.retrieve("feeding schedule", top_k=k)
        assert len(results) == k


def test_retriever_tag_bonus_boosts_relevant_chunk(retriever):
    # "arthritis" is a tag on the senior arthritis chunk
    results_with_tag = retriever.retrieve("arthritis dog", top_k=4)
    results_without = retriever.retrieve("dog mobility pain", top_k=4)
    # The chunk with "arthritis" tag should appear when querying "arthritis dog"
    ids_with_tag = [r.id for r in results_with_tag]
    assert any("arthritis" in rid for rid in ids_with_tag)


# ── get_retriever singleton ───────────────────────────────────────────────────

def test_get_retriever_returns_same_instance():
    rag_system._retriever = None
    rag_system._loaded_extra_dir = None
    r1 = get_retriever(KB_PATH)
    r2 = get_retriever(KB_PATH)
    assert r1 is r2


# ── load_extra_sources ────────────────────────────────────────────────────────

def test_load_extra_sources_creates_chunk(tmp_path):
    txt = tmp_path / "rabbit_grooming.txt"
    txt.write_text("Rabbits need regular grooming to prevent fur matting and hairballs.")
    chunks = load_extra_sources(tmp_path)
    assert len(chunks) == 1
    assert chunks[0]["id"] == "extra-rabbit_grooming"
    assert "rabbit" in chunks[0]["tags"]
    assert "grooming" in chunks[0]["tags"]


def test_extra_source_appears_in_retrieval(tmp_path):
    rag_system._retriever = None
    rag_system._loaded_extra_dir = None
    txt = tmp_path / "rabbit_care.txt"
    txt.write_text(
        "Rabbits require daily grooming, especially long-haired breeds. "
        "Gently brush your rabbit to remove loose fur and prevent hairballs. "
        "Rabbit grooming also helps you check for skin conditions."
    )
    r = get_retriever(KB_PATH, extra_sources_dir=tmp_path)
    results = r.retrieve("rabbit grooming", top_k=4)
    titles_lower = [c.title.lower() for c in results]
    assert any("rabbit" in t for t in titles_lower)
    # cleanup so other tests get a fresh singleton
    rag_system._retriever = None
    rag_system._loaded_extra_dir = None
