from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Embedding, Job

DOCUMENT_STATUS_UPLOADED = "uploaded"
DOCUMENT_STATUS_PROCESSING = "processing"
DOCUMENT_STATUS_READY = "ready"
DOCUMENT_STATUS_FAILED = "failed"

_ACTIVE_JOB_STATUSES = {"queued", "processing"}
_FAILURE_JOB_STATUSES = {"failed"}
_NON_READY_TERMINAL_STATUSES = {"done", "needs_review"}


async def _embedded_document_ids(db: AsyncSession, document_ids: Sequence[UUID]) -> set[UUID]:
    if not document_ids:
        return set()
    result = await db.execute(
        select(Embedding.document_id).where(Embedding.document_id.in_(list(document_ids))).distinct()
    )
    return set(result.scalars().all())


async def ready_document_ids(db: AsyncSession, document_ids: Sequence[UUID] | None = None) -> set[UUID]:
    stmt = select(Embedding.document_id).distinct()
    if document_ids:
        stmt = stmt.where(Embedding.document_id.in_(list(document_ids)))
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def compute_document_statuses(
    db: AsyncSession,
    document_ids: Sequence[UUID],
) -> dict[UUID, str]:
    if not document_ids:
        return {}

    result = await db.execute(
        select(Job.document_id, Job.status)
        .where(Job.document_id.in_(list(document_ids)))
        .order_by(Job.created_at.desc(), Job.updated_at.desc(), Job.id.desc())
    )
    job_rows = result.all()

    latest_status_by_doc: dict[UUID, str] = {}
    processing_doc_ids: set[UUID] = set()

    for document_id, status in job_rows:
        if status in _ACTIVE_JOB_STATUSES:
            processing_doc_ids.add(document_id)
        if document_id not in latest_status_by_doc:
            latest_status_by_doc[document_id] = status

    embedded_doc_ids = await _embedded_document_ids(db, document_ids)

    statuses: dict[UUID, str] = {}
    for document_id in document_ids:
        if document_id in processing_doc_ids:
            statuses[document_id] = DOCUMENT_STATUS_PROCESSING
            continue

        if document_id in embedded_doc_ids:
            statuses[document_id] = DOCUMENT_STATUS_READY
            continue

        latest_status = latest_status_by_doc.get(document_id)
        if latest_status in _FAILURE_JOB_STATUSES or latest_status in _NON_READY_TERMINAL_STATUSES:
            statuses[document_id] = DOCUMENT_STATUS_FAILED
            continue

        statuses[document_id] = DOCUMENT_STATUS_UPLOADED

    return statuses
