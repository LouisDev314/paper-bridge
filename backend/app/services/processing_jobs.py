import time
from uuid import UUID

from sqlalchemy import delete, insert, select

from app.core.config import settings
from app.core.logging import logger
from app.db.database import AsyncSessionLocal
from app.db.models import DocumentPage, Embedding, Extraction, Job
from app.services.chunker import chunk_text
from app.services.embedder import generate_embeddings
from app.services.extractor import extract_document_features
from app.services.validator import validate_extraction


async def run_extraction_job(job_id: UUID) -> None:
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
            full_text = "\n\n".join([page.text or "" for page in pages])

            if not full_text.strip():
                raise ValueError("No extracted text found for document.")

            extraction_pydantic = await extract_document_features(full_text)
            status = validate_extraction(extraction_pydantic)

            extraction_entry = Extraction(
                document_id=job.document_id,
                data=extraction_pydantic.model_dump(),
                status=status,
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


async def run_embedding_job(job_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            return

        job.status = "processing"
        job.error_message = None
        await db.commit()

        started_at = time.perf_counter()
        try:
            logger.info("embed_job_started job_id=%s document_id=%s", job_id, job.document_id)
            result = await db.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == job.document_id)
                .order_by(DocumentPage.page_number)
            )
            pages = result.scalars().all()

            if not pages:
                raise ValueError("No parsed pages found. Upload and parse the document before embedding.")

            all_chunks: list[dict[str, object]] = []
            for page in pages:
                if not page.text:
                    continue
                page_chunks = chunk_text(page.text)
                for index, chunk in enumerate(page_chunks):
                    all_chunks.append(
                        {
                            "chunk_id": f"p{page.page_number}-c{index}",
                            "page_start": page.page_number,
                            "page_end": page.page_number,
                            "pdf_page_start": page.page_number,
                            "pdf_page_end": page.page_number,
                            "content": chunk.content,
                            "token_count": chunk.approx_tokens,
                        }
                    )

            logger.info(
                "chunking_complete job_id=%s document_id=%s pages=%s chunks=%s chunk_size_tokens=%s overlap_tokens=%s",
                job_id,
                job.document_id,
                len(pages),
                len(all_chunks),
                settings.chunk_size_tokens,
                settings.chunk_overlap_tokens,
            )

            if not all_chunks:
                job.status = "done"
                await db.commit()
                return

            await db.execute(delete(Embedding).where(Embedding.document_id == job.document_id))
            texts = [str(chunk["content"]) for chunk in all_chunks]
            batch_size = settings.embedding_batch_size

            for start in range(0, len(texts), batch_size):
                batch_texts = texts[start : start + batch_size]
                batch_embeddings = await generate_embeddings(batch_texts, request_id=str(job_id))

                rows_to_insert = []
                for offset, embedding in enumerate(batch_embeddings):
                    chunk_meta = all_chunks[start + offset]
                    rows_to_insert.append(
                        {
                            "document_id": job.document_id,
                            "chunk_id": chunk_meta["chunk_id"],
                            "page_start": chunk_meta["page_start"],
                            "page_end": chunk_meta["page_end"],
                            "pdf_page_start": chunk_meta["pdf_page_start"],
                            "pdf_page_end": chunk_meta["pdf_page_end"],
                            "content": chunk_meta["content"],
                            "embedding": embedding,
                        }
                    )

                await db.execute(insert(Embedding), rows_to_insert)
                logger.info(
                    "embedding_batch_inserted job_id=%s batch_start=%s batch_size=%s embedding_model=%s",
                    job_id,
                    start,
                    len(rows_to_insert),
                    settings.openai_embed_model,
                )

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
            logger.exception("embed_job_failed job_id=%s error=%s", job_id, exc)
            await db.rollback()
            job = await db.get(Job, job_id)
            if not job:
                return
            job.status = "failed"
            job.error_message = f"Embedding job failed: {exc}"
            await db.commit()
