from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.models import Embedding


@dataclass
class RetrievedChunk:
    embedding: Embedding
    distance: float | None


async def retrieve_chunks(
    db: AsyncSession,
    question_embedding: list[float],
    document_ids: list[UUID] | None = None,
    top_k: int = settings.rag_top_k,
):
    logger.info("Retrieving top %s chunks", top_k)

    distance = Embedding.embedding.cosine_distance(question_embedding).label("distance")
    q = select(Embedding, distance)

    if document_ids:
        q = q.where(Embedding.document_id.in_(document_ids))

    q = q.order_by(distance).limit(top_k)

    res = await db.execute(q)
    rows = res.all()
    return [RetrievedChunk(embedding=row[0], distance=row[1]) for row in rows]
