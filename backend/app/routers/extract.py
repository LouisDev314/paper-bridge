import time

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.core.logging import logger
from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Document, Job, DocumentPage, Extraction
from app.schemas.api import ErrorResponse, JobResponse
from app.services.extractor import extract_document_features
from app.services.validator import validate_extraction

router = APIRouter(tags=["extract"])

async def run_extraction_job(job_id: UUID):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            return

        job.status = "processing"
        job.error_message = None
        await db.commit()

        started_at = time.perf_counter()
        try:
            result = await db.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == job.document_id)
                .order_by(DocumentPage.page_number)
            )
            pages = result.scalars().all()
            full_text = "\n\n".join([p.text or "" for p in pages])

            if not full_text.strip():
                raise ValueError("No extracted text found for document.")

            extraction_pydantic = await extract_document_features(full_text)
            status = validate_extraction(extraction_pydantic)

            extraction_entry = Extraction(
                document_id=job.document_id,
                data=extraction_pydantic.model_dump(),
                status=status
            )
            db.add(extraction_entry)

            job.status = "done"
            if status == "FLAGGED":
                job.status = "needs_review"

            await db.commit()
            logger.info(
                "extract_job_done job_id=%s document_id=%s status=%s duration_ms=%.2f",
                job_id,
                job.document_id,
                job.status,
                (time.perf_counter() - started_at) * 1000,
            )

        except Exception as exc:
            logger.error("extract_job_failed job_id=%s document_id=%s error=%s", job_id, job.document_id, exc)
            await db.rollback()
            job = await db.get(Job, job_id)
            if not job:
                return
            job.status = "failed"
            job.error_message = f"Extraction job failed: {exc}"
            await db.commit()

@router.post(
    "/documents/{document_id}/extract",
    response_model=JobResponse,
    summary="Queue a structured extraction job for a document",
    responses={
        404: {"model": ErrorResponse, "description": "Document not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def trigger_extraction(
    document_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    request_id = getattr(request.state, "request_id", None)
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    existing = await db.execute(
        select(Job)
        .where(Job.document_id == document_id, Job.task_type == "extract", Job.status.in_(["queued", "processing"]))
        .order_by(Job.created_at.desc())
    )
    running = existing.scalars().first()
    if running:
        logger.info(
            "extract_job_reused request_id=%s document_id=%s job_id=%s status=%s",
            request_id,
            document_id,
            running.id,
            running.status,
        )
        return running

    job = Job(document_id=document_id, task_type="extract", status="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    logger.info(
        "extract_job_queued request_id=%s document_id=%s job_id=%s",
        request_id,
        document_id,
        job.id,
    )
    background_tasks.add_task(run_extraction_job, job.id)
    return job
