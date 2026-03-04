import re
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from app.services.qa import (
    MAX_CITATIONS,
    NOT_FOUND_ANSWER,
    _convert_chunk_markers_to_numeric,
    answer_question,
)
from app.services.retriever import RetrievedChunk


def _make_chunk(chunk_id: str, page_start: int, page_end: int | None = None, filename: str = "directive060.pdf") -> RetrievedChunk:
    doc_id = uuid4()
    embedding = SimpleNamespace(
        id=uuid4(),
        chunk_id=chunk_id,
        document_id=doc_id,
        pdf_page_start=page_start,
        pdf_page_end=page_start if page_end is None else page_end,
        content=f"content for {chunk_id}",
    )
    return RetrievedChunk(
        embedding=embedding,
        filename=filename,
        distance=0.1,
        vector_similarity=0.9,
        lexical_score=0.8,
        combined_score=0.85,
        rank=1,
    )


class CitationConversionTests(unittest.TestCase):
    def test_convert_markers_to_numeric_dedupes_same_doc_page(self) -> None:
        chunks = [
            _make_chunk("a", 4),
            _make_chunk("b", 4),
            _make_chunk("c", 5),
        ]
        answer_markdown = (
            "Directive 060 requires stakeholder engagement.[[chunk:a]]\n\n"
            "- Notify nearby residents before flaring.[[chunk:b]]\n"
            "- Disclose unresolved concerns to the field centre.[[chunk:c]]"
        )

        answer, citations = _convert_chunk_markers_to_numeric(answer_markdown, chunks)

        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0].filename, "directive060.pdf")
        self.assertEqual(citations[0].page_start, 4)
        self.assertEqual(citations[0].page_end, 4)
        self.assertEqual(citations[1].page_start, 5)
        self.assertIn("engagement.[1]", answer)
        self.assertIn("before flaring.[1]", answer)
        self.assertIn("field centre.[2]", answer)

    def test_convert_markers_enforces_max_citations_with_remap(self) -> None:
        chunks = [_make_chunk(f"c{idx}", idx) for idx in range(1, 7)]
        answer_markdown = "\n".join(
            [
                "Direct answer sentence.[[chunk:c1]]",
                "- Requirement one.[[chunk:c2]]",
                "- Requirement two.[[chunk:c3]]",
                "- Requirement three.[[chunk:c4]]",
                "- Requirement four.[[chunk:c5]]",
                "- Requirement five.[[chunk:c6]]",
            ]
        )

        answer, citations = _convert_chunk_markers_to_numeric(answer_markdown, chunks)

        self.assertEqual(len(citations), MAX_CITATIONS)
        self.assertIsNone(re.search(r"\[(5|6)\]", answer))
        for line in answer.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            self.assertIsNotNone(re.search(r"\[\d+\]$", stripped))

    def test_convert_markers_normalizes_zero_indexed_pages(self) -> None:
        chunks = [_make_chunk("z0", 0, 0)]
        answer_markdown = "Operators must notify before activity starts.[[chunk:z0]]"

        answer, citations = _convert_chunk_markers_to_numeric(answer_markdown, chunks)

        self.assertEqual(answer, "Operators must notify before activity starts.[1]")
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].page_start, 1)
        self.assertEqual(citations[0].page_end, 1)


class AnswerQuestionFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_question_returns_not_found_when_markers_missing(self) -> None:
        chunks = [_make_chunk("p5-c0", 5)]
        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"found": true, "answer_markdown": "Directive 060 has requirements."}'
                    )
                )
            ]
        )

        async def _fake_create(*args, **kwargs):
            return fake_response

        with patch("app.services.qa.openai_client.chat.completions.create", side_effect=_fake_create):
            result = await answer_question(
                "What requirements apply before flaring?",
                chunks,
                request_id="test-request-id",
            )

        self.assertEqual(result.answer, NOT_FOUND_ANSWER)
        self.assertEqual(result.citations, [])

    async def test_answer_question_precision_retry_adds_numeric_threshold(self) -> None:
        chunks = [_make_chunk("p5-c0", 5)]
        chunks[0].embedding.content = "Solution gas may be conserved at 900 m3/day with NPV greater than -$55,000."
        responses = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"found": true, "answer_markdown": '
                                '"Solution gas flaring is allowed under certain conditions.[[chunk:p5-c0]]"}'
                            )
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"found": true, "answer_markdown": '
                                '"Solution gas flaring is allowed when volumes are 900 m3/day and NPV is greater than -$55,000.[[chunk:p5-c0]]"}'
                            )
                        )
                    )
                ]
            ),
        ]

        call_count = {"value": 0}

        async def _fake_create(*args, **kwargs):
            idx = call_count["value"]
            call_count["value"] += 1
            return responses[min(idx, len(responses) - 1)]

        with patch("app.services.qa.openai_client.chat.completions.create", side_effect=_fake_create):
            result = await answer_question(
                "When is solution gas flaring allowed under Directive 060?",
                chunks,
                request_id="test-retry-request-id",
            )

        self.assertGreaterEqual(call_count["value"], 2)
        self.assertIn("900 m3/day", result.answer)
        self.assertIn("-$55,000", result.answer)
        self.assertTrue(result.citations)
