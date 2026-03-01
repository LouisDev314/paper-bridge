import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.schemas.qa import AskResponse, Citation
from app.services.retriever import RetrievedChunk


async def _fake_db_dependency():
    yield SimpleNamespace()


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides[get_db] = _fake_db_dependency
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_documents_reject_non_pdf(self) -> None:
        resp = self.client.post(
            "/documents",
            files={"file": ("notes.txt", b"not a pdf", "text/plain")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Only PDF files are supported", resp.text)

    def test_ask_enforces_validation(self) -> None:
        resp = self.client.post("/ask", json={"question": "ok", "top_k": 999})
        self.assertEqual(resp.status_code, 422)

    def test_ask_happy_path_returns_citations(self) -> None:
        doc_id = uuid4()
        fake_embedding = SimpleNamespace(
            chunk_id="p5-c0",
            document_id=doc_id,
            page_start=5,
            page_end=5,
            pdf_page_start=5,
            pdf_page_end=5,
            content="OVG overall vent gas",
        )
        retrieved = [
            RetrievedChunk(
                embedding=fake_embedding,
                distance=0.2,
                vector_similarity=0.8,
                lexical_score=0.5,
                combined_score=0.72,
                rank=1,
            )
        ]

        async def _embed(*args, **kwargs):
            return [[0.1] * 1536]

        async def _retrieve(*args, **kwargs):
            self.assertEqual(kwargs["top_k"], 15)  # clamped from request
            return retrieved

        async def _answer(*args, **kwargs):
            return AskResponse(
                answer="OVG means overall vent gas.",
                citations=[
                    Citation(
                        chunk_id="p5-c0",
                        document_id=doc_id,
                        page_start=5,
                        page_end=5,
                        pdf_page_start=5,
                        pdf_page_end=5,
                        text="OVG overall vent gas",
                        similarity_score=0.72,
                    )
                ],
            )

        with (
            patch("app.routers.ask.generate_embeddings", side_effect=_embed),
            patch("app.routers.ask.retrieve_chunks", side_effect=_retrieve),
            patch("app.routers.ask.answer_question", side_effect=_answer),
        ):
            resp = self.client.post(
                "/ask",
                json={"question": "What does OVG stand for?", "top_k": 50, "doc_ids": [str(doc_id)]},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("overall vent gas", payload["answer"].lower())
        self.assertTrue(payload["citations"])
        self.assertEqual(payload["citations"][0]["pdf_page_start"], 5)


if __name__ == "__main__":
    unittest.main()
