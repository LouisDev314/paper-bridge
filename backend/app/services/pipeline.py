import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.database import AsyncSessionLocal
from app.db.models import Embedding, Extraction, Job

PIPELINE_TASK_TYPE = "pipeline"
ACTIVE_JOB_STATUSES = {"queued", "processing"}
EXTRACT_SUCCESS_STATUSES = {"done", "needs_review"}
EMBED_SUCCESS_STATUSES = {"done"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_pipeline_metadata(raw: Any) -> dict[str, Any]:
    metadata = raw if isinstance(raw, dict) else {}
    steps = metadata.get("steps")
    if not isinstance(steps, dict):
        steps = {}
    extract_step = steps.get("extract")
    embed_step = steps.get("embed")
    if not isinstance(extract_step, dict):
        extract_step = {}
    if not isinstance(embed_step, dict):
        embed_step = {}
    metadata["steps"] = {
        "extract": {
            "status": str(extract_step.get("status", "queued")),
            "job_id": extract_step.get("job_id"),
            "error_message": extract_step.get("error_message"),
            "updated_at": extract_step.get("updated_at"),
        },
        "embed": {
            "status": str(embed_step.get("status", "queued")),
            "job_id": embed_step.get("job_id"),
            "error_message": embed_step.get("error_message"),
            "updated_at": embed_step.get("updated_at"),
        },
    }
    return metadata


async def _latest_job(
    db: AsyncSession,
    document_id: UUID,
    task_type: str,
    statuses: set[str] | None = None,
) -> Job | None:
    stmt = select(Job).where(Job.document_id == document_id, Job.task_type == task_type)
    if statuses:
        stmt = stmt.where(Job.status.in_(sorted(statuses)))
    result = await db.execute(stmt.order_by(Job.created_at.desc()).limit(1))
    return result.scalars().first()


async def _has_extraction(db: AsyncSession, document_id: UUID) -> bool:
    result = await db.execute(select(Extraction.id).where(Extraction.document_id == document_id).limit(1))
    return result.scalar_one_or_none() is not None


async def _is_embedding_complete(db: AsyncSession, document_id: UUID) -> bool:
    latest_embed_job = await _latest_job(db, document_id, task_type="embed")
    if latest_embed_job and latest_embed_job.status == "done":
        return True
    result = await db.execute(select(Embedding.id).where(Embedding.document_id == document_id).limit(1))
    return result.scalar_one_or_none() is not None


async def _set_step(
    db: AsyncSession,
    pipeline_job: Job,
    step: str,
    status: str,
    job_id: UUID | None = None,
    error_message: str | None = None,
) -> None:
    metadata = _normalize_pipeline_metadata(pipeline_job.task_metadata)
    step_data = metadata["steps"][step]
    step_data["status"] = status
    step_data["job_id"] = str(job_id) if job_id else step_data.get("job_id")
    step_data["error_message"] = error_message
    step_data["updated_at"] = _utc_now_iso()
    pipeline_job.task_metadata = metadata
    await db.commit()


async def _ensure_step_job(db: AsyncSession, document_id: UUID, task_type: str) -> Job:
    active = await _latest_job(db, document_id, task_type, statuses=ACTIVE_JOB_STATUSES)
    if active:
        return active

    job = Job(document_id=document_id, task_type=task_type, status="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _wait_for_job_terminal(
    db: AsyncSession,
    job_id: UUID,
    timeout_seconds: int = 1800,
    poll_seconds: float = 0.5,
) -> Job:
    started = time.monotonic()
    while True:
        job = await db.get(Job, job_id)
        if not job:
            raise RuntimeError(f"Dependent job was deleted: {job_id}")
        await db.refresh(job)
        if job.status not in ACTIVE_JOB_STATUSES:
            return job
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError(f"Timed out waiting for job {job_id}")
        await asyncio.sleep(poll_seconds)


async def ensure_pipeline_job(document_id: UUID, db: AsyncSession, request_id: str | None = None) -> Job:
    active = await _latest_job(db, document_id, PIPELINE_TASK_TYPE, statuses=ACTIVE_JOB_STATUSES)
    if active:
        logger.info(
            "pipeline_job_reused request_id=%s document_id=%s pipeline_job_id=%s status=%s",
            request_id,
            document_id,
            active.id,
            active.status,
        )
        return active

    extraction_complete = await _has_extraction(db, document_id)
    embedding_complete = await _is_embedding_complete(db, document_id)

    if extraction_complete and embedding_complete:
        existing_done = await _latest_job(db, document_id, PIPELINE_TASK_TYPE, statuses={"done"})
        if existing_done:
            logger.info(
                "pipeline_job_done_reused request_id=%s document_id=%s pipeline_job_id=%s",
                request_id,
                document_id,
                existing_done.id,
            )
            return existing_done

        latest_extract = await _latest_job(db, document_id, "extract")
        latest_embed = await _latest_job(db, document_id, "embed")
        metadata = _normalize_pipeline_metadata({})
        metadata["steps"]["extract"]["status"] = "skipped"
        metadata["steps"]["extract"]["job_id"] = str(latest_extract.id) if latest_extract else None
        metadata["steps"]["extract"]["updated_at"] = _utc_now_iso()
        metadata["steps"]["embed"]["status"] = "skipped"
        metadata["steps"]["embed"]["job_id"] = str(latest_embed.id) if latest_embed else None
        metadata["steps"]["embed"]["updated_at"] = _utc_now_iso()
        metadata["started_at"] = _utc_now_iso()
        metadata["completed_at"] = _utc_now_iso()

        done_job = Job(
            document_id=document_id,
            task_type=PIPELINE_TASK_TYPE,
            status="done",
            task_metadata=metadata,
        )
        db.add(done_job)
        await db.commit()
        await db.refresh(done_job)
        logger.info(
            "pipeline_job_backfilled_done request_id=%s document_id=%s pipeline_job_id=%s",
            request_id,
            document_id,
            done_job.id,
        )
        return done_job

    queued_job = Job(
        document_id=document_id,
        task_type=PIPELINE_TASK_TYPE,
        status="queued",
        task_metadata=_normalize_pipeline_metadata({}),
    )
    db.add(queued_job)
    await db.commit()
    await db.refresh(queued_job)
    logger.info(
        "pipeline_job_queued request_id=%s document_id=%s pipeline_job_id=%s",
        request_id,
        document_id,
        queued_job.id,
    )
    return queued_job


async def run_pipeline_job(job_id: UUID, request_id: str | None = None) -> None:
    from app.routers.embed import run_embed_job
    from app.routers.extract import run_extraction_job

    async with AsyncSessionLocal() as db:
        pipeline_job = await db.get(Job, job_id)
        if not pipeline_job or pipeline_job.task_type != PIPELINE_TASK_TYPE:
            return

        pipeline_job.status = "processing"
        pipeline_job.error_message = None
        metadata = _normalize_pipeline_metadata(pipeline_job.task_metadata)
        metadata["started_at"] = metadata.get("started_at") or _utc_now_iso()
        pipeline_job.task_metadata = metadata
        await db.commit()

        logger.info(
            "pipeline_job_started request_id=%s document_id=%s pipeline_job_id=%s",
            request_id,
            pipeline_job.document_id,
            pipeline_job.id,
        )

        try:
            document_id = pipeline_job.document_id

            if await _has_extraction(db, document_id):
                latest_extract = await _latest_job(db, document_id, "extract")
                await _set_step(db, pipeline_job, "extract", "skipped", latest_extract.id if latest_extract else None)
                logger.info(
                    "pipeline_extract_skipped request_id=%s document_id=%s pipeline_job_id=%s",
                    request_id,
                    document_id,
                    pipeline_job.id,
                )
            else:
                extract_job = await _ensure_step_job(db, document_id, task_type="extract")
                await _set_step(db, pipeline_job, "extract", "processing", extract_job.id)
                logger.info(
                    "pipeline_extract_trigger request_id=%s document_id=%s pipeline_job_id=%s extract_job_id=%s",
                    request_id,
                    document_id,
                    pipeline_job.id,
                    extract_job.id,
                )
                if extract_job.status == "processing":
                    extract_job = await _wait_for_job_terminal(db, extract_job.id)
                else:
                    await run_extraction_job(extract_job.id)
                    extract_job = await db.get(Job, extract_job.id)
                    if extract_job:
                        await db.refresh(extract_job)

                if not extract_job or extract_job.status not in EXTRACT_SUCCESS_STATUSES:
                    err = extract_job.error_message if extract_job else "Extraction step did not complete."
                    await _set_step(db, pipeline_job, "extract", "failed", extract_job.id if extract_job else None, err)
                    raise RuntimeError(err or "Extraction step failed.")

                await _set_step(db, pipeline_job, "extract", "done", extract_job.id)
                logger.info(
                    "pipeline_extract_done request_id=%s document_id=%s pipeline_job_id=%s extract_job_id=%s status=%s",
                    request_id,
                    document_id,
                    pipeline_job.id,
                    extract_job.id,
                    extract_job.status,
                )

            if await _is_embedding_complete(db, document_id):
                latest_embed = await _latest_job(db, document_id, "embed")
                await _set_step(db, pipeline_job, "embed", "skipped", latest_embed.id if latest_embed else None)
                logger.info(
                    "pipeline_embed_skipped request_id=%s document_id=%s pipeline_job_id=%s",
                    request_id,
                    document_id,
                    pipeline_job.id,
                )
            else:
                embed_job = await _ensure_step_job(db, document_id, task_type="embed")
                await _set_step(db, pipeline_job, "embed", "processing", embed_job.id)
                logger.info(
                    "pipeline_embed_trigger request_id=%s document_id=%s pipeline_job_id=%s embed_job_id=%s",
                    request_id,
                    document_id,
                    pipeline_job.id,
                    embed_job.id,
                )
                if embed_job.status == "processing":
                    embed_job = await _wait_for_job_terminal(db, embed_job.id)
                else:
                    await run_embed_job(embed_job.id)
                    embed_job = await db.get(Job, embed_job.id)
                    if embed_job:
                        await db.refresh(embed_job)

                if not embed_job or embed_job.status not in EMBED_SUCCESS_STATUSES:
                    err = embed_job.error_message if embed_job else "Embedding step did not complete."
                    await _set_step(db, pipeline_job, "embed", "failed", embed_job.id if embed_job else None, err)
                    raise RuntimeError(err or "Embedding step failed.")

                await _set_step(db, pipeline_job, "embed", "done", embed_job.id)
                logger.info(
                    "pipeline_embed_done request_id=%s document_id=%s pipeline_job_id=%s embed_job_id=%s status=%s",
                    request_id,
                    document_id,
                    pipeline_job.id,
                    embed_job.id,
                    embed_job.status,
                )

            pipeline_job = await db.get(Job, pipeline_job.id)
            if not pipeline_job:
                return
            metadata = _normalize_pipeline_metadata(pipeline_job.task_metadata)
            metadata["completed_at"] = _utc_now_iso()
            pipeline_job.task_metadata = metadata
            pipeline_job.status = "done"
            pipeline_job.error_message = None
            await db.commit()
            logger.info(
                "pipeline_job_done request_id=%s document_id=%s pipeline_job_id=%s",
                request_id,
                pipeline_job.document_id,
                pipeline_job.id,
            )
        except Exception as exc:
            logger.exception(
                "pipeline_job_failed request_id=%s pipeline_job_id=%s error=%s",
                request_id,
                job_id,
                exc,
            )
            await db.rollback()
            pipeline_job = await db.get(Job, job_id)
            if not pipeline_job:
                return
            metadata = _normalize_pipeline_metadata(pipeline_job.task_metadata)
            metadata["failed_at"] = _utc_now_iso()
            pipeline_job.task_metadata = metadata
            pipeline_job.status = "failed"
            pipeline_job.error_message = str(exc)
            await db.commit()
