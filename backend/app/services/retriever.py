from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from sqlalchemy import select
from app.db.models import Embedding
from app.core.config import settings
from uuid import UUID


async def retrieve_chunks(
    db: AsyncSession,
    question_embedding: list[float],
    document_ids: list[UUID] | None = None,
    top_k: int = settings.rag_top_k,
):
    logger.info(f"Retrieving top {top_k} chunks")

    q = select(Embedding)

    # Using vector_cosine_ops or cosine_distance function from pgvector
    # smaller distance is closer
    # optional filter by a set of document_ids (still multi-doc)
    if document_ids:
        q = q.where(Embedding.document_id.in_([str(doc_id) for doc_id in document_ids]))

    q = (
        q.order_by(Embedding.embedding.cosine_distance(question_embedding))
         .limit(top_k)
    )

    res = await db.execute(q)
    return res.scalars().all()
