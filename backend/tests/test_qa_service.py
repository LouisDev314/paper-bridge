import re
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from app.services.qa import (
    MAX_CITATIONS,
    NOT_FOUND_ANSWER,
    QAResult,
    _build_context,
    _chunk_key_rule_bonus,
    _convert_chunk_markers_to_numeric,
    _should_retry_for_coverage,
    answer_question,
)
from app.services.retriever import RetrievedChunk


def _make_chunk(
    chunk_id: str,
    page_start: int,
    page_end: int | None = None,
    filename: str = "directive060.pdf",
    content: str | None = None,
    combined_score: float = 0.85,
    vector_similarity: float = 0.9,
) -> RetrievedChunk:
    doc_id = uuid4()
    embedding = SimpleNamespace(
        id=uuid4(),
        chunk_id=chunk_id,
        document_id=doc_id,
        pdf_page_start=page_start,
        pdf_page_end=page_start if page_end is None else page_end,
        content=content or f"content for {chunk_id}",
    )
    return RetrievedChunk(
        embedding=embedding,
        filename=filename,
        distance=0.1,
        vector_similarity=vector_similarity,
        lexical_score=0.8,
        combined_score=combined_score,
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


class ContextAccuracyUpgradeTests(unittest.TestCase):
    def test_chunk_key_rule_bonus_prefers_threshold_anchors(self) -> None:
        weak = _make_chunk("weak", 10, content="General discussion without concrete thresholds.")
        strong = _make_chunk(
            "strong",
            11,
            content="Conserve when NPV is greater than -$55,000 and combined gas exceeds 900 m3/day.",
        )

        self.assertGreater(_chunk_key_rule_bonus(strong), _chunk_key_rule_bonus(weak))

    def test_build_context_enforces_diversity_and_page_cap(self) -> None:
        chunks = [
            _make_chunk("p10-a", 10, 10, content="General content.", combined_score=0.99, vector_similarity=0.90),
            _make_chunk("p10-b", 10, 11, content="Additional content.", combined_score=0.98, vector_similarity=0.89),
            _make_chunk("p11-a", 11, 11, content="Page 11 content.", combined_score=0.97, vector_similarity=0.88),
            _make_chunk("p12-a", 12, 12, content="Page 12 content.", combined_score=0.96, vector_similarity=0.87),
            _make_chunk("p10-c", 10, 12, content="Third same-start page range.", combined_score=0.95, vector_similarity=0.86),
            _make_chunk("p11-dup", 11, 11, content="Duplicate range should be skipped.", combined_score=0.94, vector_similarity=0.85),
        ]

        _context, selected_chunks, _tokens = _build_context(
            "What must operators do before planned flaring near residents?",
            chunks,
            max_tokens=10000,
        )

        selected_pages = [int(chunk.embedding.pdf_page_start) for chunk in selected_chunks]
        first_three = selected_pages[:3]
        self.assertEqual(len(set(first_three)), 3)
        self.assertLessEqual(selected_pages.count(10), 2)

        selected_ranges = {
            (chunk.filename, int(chunk.embedding.pdf_page_start), int(chunk.embedding.pdf_page_end))
            for chunk in selected_chunks
        }
        self.assertEqual(len(selected_ranges), len(selected_chunks))

    def test_coverage_retry_trigger_uses_source_and_page_diversity(self) -> None:
        chunks = [
            _make_chunk("c1", 36, content="Residents should be notified."),
            _make_chunk("c2", 37, content="Unresolved concerns must be disclosed to AER field centre."),
        ]

        single_source_answer = "Notify residents before planned activity.[[chunk:c1]]"
        multi_source_answer = (
            "Notify residents before planned activity.[[chunk:c1]]\n"
            "- Disclose unresolved concerns to the AER field centre.[[chunk:c2]]"
        )

        self.assertTrue(
            _should_retry_for_coverage(
                "What must operators do before conducting flaring near residents?",
                chunks,
                single_source_answer,
            )
        )
        self.assertFalse(
            _should_retry_for_coverage(
                "What must operators do before conducting flaring near residents?",
                chunks,
                multi_source_answer,
            )
        )


class AccuracyRegressionScenarios(unittest.IsolatedAsyncioTestCase):
    def _assert_quality(self, answer: str, citations_count: int) -> None:
        self.assertRegex(answer, r"(?m)^- \*\*[^*]+?\*\*")
        self.assertRegex(answer, r"\[\d+\]")
        self.assertGreaterEqual(citations_count, 2)

    async def test_pair1_community_and_aer_disclosure(self) -> None:
        question = "What must operators do before conducting flaring or incineration near residents under Directive 060?"
        chunks = [
            _make_chunk("p36", 36, content="Notify residents within 1.5 km at least 24 hours before planned flaring."),
            _make_chunk("p37", 37, content="Disclose unresolved concerns to the AER field centre before activity."),
            _make_chunk("p38", 38, content="Planned events require engagement; emergency events follow emergency reporting."),
        ]
        responses = [
            QAResult(
                found=True,
                answer_markdown="Operators must notify residents before activity.[[chunk:p36]]",
            ),
            QAResult(
                found=True,
                answer_markdown=(
                    "Operators must complete notification and disclosure steps before planned flaring or incineration near residents.[[chunk:p36]][[chunk:p37]]\n\n"
                    "Key requirements include:\n"
                    "- **Resident Notification** Notify residents within 1.5 km at least 24 hours before planned activity.[[chunk:p36]]\n"
                    "- **AER Disclosure** Disclose unresolved concerns to the AER field centre before activity begins.[[chunk:p37]]\n"
                    "- **Planned vs Emergency** Planned operations require engagement, while emergency events follow emergency reporting rules.[[chunk:p38]]"
                ),
            ),
        ]
        calls = {"count": 0}

        async def _fake_run(*args, **kwargs):
            idx = min(calls["count"], len(responses) - 1)
            calls["count"] += 1
            return responses[idx]

        with patch("app.services.qa._run_qa_model", side_effect=_fake_run):
            result = await answer_question(question, chunks, request_id="pair1")

        self.assertEqual(calls["count"], 2)
        self._assert_quality(result.answer, len(result.citations))
        lowered = result.answer.lower()
        self.assertIn("resident", lowered)
        self.assertIn("unresolved concerns", lowered)
        self.assertIn("field centre", lowered)
        self.assertIn("emergency", lowered)

    async def test_pair2_public_notice_contents(self) -> None:
        question = "What information must be included in the public notice/information package for a planned flaring or incineration event?"
        chunks = [
            _make_chunk("p40", 40, content="Public notice includes operator contact, location, duration, and well type."),
            _make_chunk("p41", 41, content="Information package includes expected volumes or rates and H2S content where applicable."),
            _make_chunk("p42", 42, content="Planned flaring communication should include timing and outreach details."),
        ]
        responses = [
            QAResult(
                found=True,
                answer_markdown="The notice must identify the operator and location.[[chunk:p40]]",
            ),
            QAResult(
                found=True,
                answer_markdown=(
                    "Planned flaring/incineration notices must include core event details and safety content.[[chunk:p40]][[chunk:p41]]\n\n"
                    "Key requirements include:\n"
                    "- **Operator Contact** Provide operator contact information for public follow-up.[[chunk:p40]]\n"
                    "- **Location and Duration** Include event location and planned duration.[[chunk:p40]][[chunk:p42]]\n"
                    "- **Volumes/Rates and Well Type** State expected volumes or rates and identify the well type.[[chunk:p40]][[chunk:p41]]\n"
                    "- **H2S Content** Include H2S content when applicable.[[chunk:p41]]"
                ),
            ),
        ]
        calls = {"count": 0}

        async def _fake_run(*args, **kwargs):
            idx = min(calls["count"], len(responses) - 1)
            calls["count"] += 1
            return responses[idx]

        with patch("app.services.qa._run_qa_model", side_effect=_fake_run):
            result = await answer_question(question, chunks, request_id="pair2")

        self.assertEqual(calls["count"], 2)
        self._assert_quality(result.answer, len(result.citations))
        lowered = result.answer.lower()
        self.assertIn("contact", lowered)
        self.assertIn("location", lowered)
        self.assertIn("duration", lowered)
        self.assertIn("volumes", lowered)
        self.assertIn("rates", lowered)
        self.assertIn("well type", lowered)
        self.assertIn("h2s", lowered)

    async def test_pair3_solution_gas_conservation_economics(self) -> None:
        question = "When is solution gas flaring allowed under Directive 060?"
        chunks = [
            _make_chunk("p20", 20, content="If combined flare and vent exceeds 900 m3/day, evaluate conservation economics."),
            _make_chunk("p21", 21, content="Conservation is required when NPV is greater than -$55,000."),
            _make_chunk("p22", 22, content="AER may require conservation regardless of economics; outages/emergencies handled separately."),
        ]
        responses = [
            QAResult(
                found=True,
                answer_markdown="Solution gas flaring may be allowed under some conditions.[[chunk:p20]]",
            ),
            QAResult(
                found=True,
                answer_markdown=(
                    "Solution gas flaring is allowed only when Directive 060 conservation conditions are met.[[chunk:p20]][[chunk:p21]]\n\n"
                    "Key requirements include:\n"
                    "- **Volume Trigger** Combined flare plus vent greater than 900 m3/day triggers conservation evaluation.[[chunk:p20]]\n"
                    "- **Economic Threshold** Conservation is required when NPV is greater than -$55,000.[[chunk:p21]]\n"
                    "- **Regulatory Discretion** AER can require conservation regardless of economics.[[chunk:p22]]\n"
                    "- **Outage/Emergency Handling** Outage and emergency handling requirements remain separate and must be followed.[[chunk:p22]]"
                ),
            ),
        ]
        calls = {"count": 0}

        async def _fake_run(*args, **kwargs):
            idx = min(calls["count"], len(responses) - 1)
            calls["count"] += 1
            return responses[idx]

        with patch("app.services.qa._run_qa_model", side_effect=_fake_run):
            result = await answer_question(question, chunks, request_id="pair3")

        self.assertEqual(calls["count"], 2)
        self._assert_quality(result.answer, len(result.citations))
        lowered = result.answer.lower()
        self.assertIn("900 m3/day", lowered)
        self.assertIn("-$55,000", lowered)
        self.assertIn("aer can require conservation", lowered)
        self.assertIn("outage", lowered)

    async def test_pair4_high_gor_shut_in(self) -> None:
        question = "When must wells be shut in due to high gas-oil ratio under Directive 060?"
        chunks = [
            _make_chunk("p30", 30, content="Wells must be shut in when GOR exceeds 3000 m3/m3."),
            _make_chunk("p31", 31, content="During outages, shut in the highest GOR wells first."),
            _make_chunk("p32", 32, content="Operational follow-up and monitoring obligations apply."),
        ]
        responses = [
            QAResult(
                found=True,
                answer_markdown="Wells may need to be shut in for high GOR.[[chunk:p30]]",
            ),
            QAResult(
                found=True,
                answer_markdown=(
                    "Directive 060 requires shut-in actions when high GOR thresholds are exceeded.[[chunk:p30]]\n\n"
                    "Key requirements include:\n"
                    "- **High GOR Threshold** Shut in wells when GOR exceeds 3000 m3/m3.[[chunk:p30]]\n"
                    "- **Outage Priority** During outages, shut in the highest GOR wells first.[[chunk:p31]]"
                ),
            ),
        ]
        calls = {"count": 0}

        async def _fake_run(*args, **kwargs):
            idx = min(calls["count"], len(responses) - 1)
            calls["count"] += 1
            return responses[idx]

        with patch("app.services.qa._run_qa_model", side_effect=_fake_run):
            result = await answer_question(question, chunks, request_id="pair4")

        self.assertEqual(calls["count"], 2)
        self._assert_quality(result.answer, len(result.citations))
        lowered = result.answer.lower()
        self.assertIn("3000 m3/m3", lowered)
        self.assertIn("highest gor wells first", lowered)
