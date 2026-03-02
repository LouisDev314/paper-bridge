import unittest
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


async def _fake_db_dependency():
    yield SimpleNamespace()


def _fake_document(document_id):
    return SimpleNamespace(
        id=document_id,
        filename="sample.pdf",
        checksum_sha256="abc123",
        version=1,
        total_pages=2,
        created_at=datetime.now(UTC),
    )


class PipelineUploadApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides[get_db] = _fake_db_dependency
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_upload_without_auto_process_keeps_pipeline_job_id_null(self) -> None:
        document_id = uuid4()

        async def _ingest(**kwargs):
            return _fake_document(document_id)

        async def _queue(**kwargs):
            return None

        with (
            patch("app.routers.documents._ingest_pdf_upload", side_effect=_ingest),
            patch("app.routers.documents._queue_pipeline_if_requested", side_effect=_queue),
        ):
            resp = self.client.post(
                "/documents?dedupe=true&auto_process=false",
                files={"file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["id"], str(document_id))
        self.assertIsNone(payload.get("pipeline_job_id"))

    def test_upload_with_auto_process_returns_pipeline_job_id(self) -> None:
        document_id = uuid4()
        pipeline_job_id = uuid4()

        async def _ingest(**kwargs):
            return _fake_document(document_id)

        async def _queue(**kwargs):
            return pipeline_job_id

        with (
            patch("app.routers.documents._ingest_pdf_upload", side_effect=_ingest),
            patch("app.routers.documents._queue_pipeline_if_requested", side_effect=_queue),
        ):
            resp = self.client.post(
                "/documents?dedupe=true&auto_process=true",
                files={"file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["id"], str(document_id))
        self.assertEqual(payload["pipeline_job_id"], str(pipeline_job_id))

    def test_batch_upload_with_auto_process_returns_pipeline_ids(self) -> None:
        document_ids = [uuid4(), uuid4()]
        pipeline_job_ids = [uuid4(), uuid4()]
        call_index = {"value": 0}

        async def _ingest(**kwargs):
            idx = call_index["value"]
            call_index["value"] += 1
            return _fake_document(document_ids[idx])

        async def _queue(**kwargs):
            idx = call_index["value"] - 1
            return pipeline_job_ids[idx]

        with (
            patch("app.routers.documents._ingest_pdf_upload", side_effect=_ingest),
            patch("app.routers.documents._queue_pipeline_if_requested", side_effect=_queue),
        ):
            resp = self.client.post(
                "/documents/batch?dedupe=true&auto_process=true",
                files=[
                    ("files", ("a.pdf", b"%PDF-1.4", "application/pdf")),
                    ("files", ("b.pdf", b"%PDF-1.4", "application/pdf")),
                ],
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["pipeline_job_id"], str(pipeline_job_ids[0]))
        self.assertEqual(payload[1]["pipeline_job_id"], str(pipeline_job_ids[1]))


if __name__ == "__main__":
    unittest.main()
