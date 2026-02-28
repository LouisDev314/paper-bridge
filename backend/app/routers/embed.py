import time

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from uuid import UUID

from app.core.config import settings
from app.core.logging import logger
from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Document, Job, DocumentPage, Embedding
from app.schemas.api import ErrorResponse, JobResponse
from app.services.chunker import chunk_text
from app.services.embedder import generate_embeddings

router = APIRouter(tags=["embed"])

async def run_embed_job(job_id: UUID):
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

            if not pages:
                raise ValueError("No parsed pages found. Upload and parse the document before embedding.")

            all_chunks = []
            for page in pages:
                if not page.text:
                    continue
                page_chunks = chunk_text(page.text)
                for i, c in enumerate(page_chunks):
                    all_chunks.append({
                        "chunk_id": f"p{page.page_number}-c{i}",
                        "page_start": page.page_number,
                        "page_end": page.page_number,
                        "content": c
                    })
            
            if not all_chunks:
                job.status = "done"
                await db.commit()
                return

            await db.execute(delete(Embedding).where(Embedding.document_id == job.document_id))
            texts = [c["content"] for c in all_chunks]
            batch_size = settings.embedding_batch_size
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i+batch_size]
                batch_embeddings = await generate_embeddings(batch_texts)

                for j, emb in enumerate(batch_embeddings):
                    chunk_meta = all_chunks[i+j]
                    db.add(Embedding(
                        document_id=job.document_id,
                        chunk_id=chunk_meta["chunk_id"],
                        page_start=chunk_meta["page_start"],
                        page_end=chunk_meta["page_end"],
                        content=chunk_meta["content"],
                        embedding=emb
                    ))

            job.status = "done"
            await db.commit()
            logger.info(
                "embed_job_done job_id=%s document_id=%s chunks=%s duration_ms=%.2f",
                job_id,
                job.document_id,
                len(all_chunks),
                (time.perf_counter() - started_at) * 1000,
            )

        except Exception as exc:
            logger.error("embed_job_failed job_id=%s error=%s", job_id, exc)
            await db.rollback()
            job = await db.get(Job, job_id)
            if not job:
                return
            job.status = "failed"
            job.error_message = "Embedding job failed."
            await db.commit()

@router.post(
    "/documents/{document_id}/embed",
    response_model=JobResponse,
    summary="Queue an embedding job for a document",
    responses={
        404: {"model": ErrorResponse, "description": "Document not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def trigger_embed(document_id: UUID, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    existing = await db.execute(
        select(Job)
        .where(Job.document_id == document_id, Job.task_type == "embed", Job.status.in_(["queued", "processing"]))
        .order_by(Job.created_at.desc())
    )
    running = existing.scalars().first()
    if running:
        return running

    job = Job(document_id=document_id, task_type="embed", status="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(run_embed_job, job.id)
    return job
