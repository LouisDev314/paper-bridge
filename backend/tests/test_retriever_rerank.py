import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.services.retriever import (
    RetrievedChunk,
    _build_query_expansions,
    _keyword_boost_score,
    _select_diverse_top_chunks,
)


def _chunk(content: str, combined_score: float, page: int, chunk_id: str) -> RetrievedChunk:
    embedding = SimpleNamespace(
        id=uuid4(),
        chunk_id=chunk_id,
        document_id=uuid4(),
        pdf_page_start=page,
        pdf_page_end=page,
        content=content,
    )
    return RetrievedChunk(
        embedding=embedding,
        filename="Directive060.pdf",
        distance=0.2,
        vector_similarity=0.8,
        lexical_score=0.5,
        combined_score=combined_score,
        rank=0,
    )


class RetrieverRerankTests(unittest.TestCase):
    def test_query_expansion_includes_anchor_terms_for_solution_gas_question(self) -> None:
        queries = _build_query_expansions("When is solution gas flaring allowed under Directive 060?")
        joined = " ".join(queries).lower()
        self.assertGreaterEqual(len(queries), 3)
        self.assertLessEqual(len(queries), 5)
        self.assertIn("900 m3/day", joined)
        self.assertIn("npv", joined)
        self.assertIn("3000 m3/m3", joined)

    def test_keyword_boost_prefers_numeric_threshold_content(self) -> None:
        question = "When is solution gas flaring allowed?"
        generic = _keyword_boost_score("Flaring events may be managed by operators.", question)
        numeric = _keyword_boost_score(
            "Conserve where NPV is greater than -$55,000 and venting exceeds 900 m3/day.",
            question,
        )
        self.assertGreater(numeric, generic)

    def test_diverse_selection_keeps_numeric_and_procedural_chunks(self) -> None:
        ranked = [
            _chunk("General operations overview text.", 0.95, 1, "a"),
            _chunk("NPV must be greater than -$55,000 and 900 m3/day applies.", 0.70, 2, "b"),
            _chunk("Operators must notify the AER field centre before planned flaring.", 0.65, 3, "c"),
            _chunk("Additional background content.", 0.60, 4, "d"),
        ]
        selected = _select_diverse_top_chunks(
            "What information must operators provide to the public before a planned flaring event?",
            ranked,
            top_k=3,
        )
        selected_text = " ".join(chunk.embedding.content.lower() for chunk in selected)
        self.assertIn("900 m3/day", selected_text)
        self.assertIn("field centre", selected_text)
        self.assertEqual(len(selected), 3)
