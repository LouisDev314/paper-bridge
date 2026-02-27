from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Embedding
from app.core.config import settings
from app.core.logging import logger

async def retrieve_chunks(db: AsyncSession, document_id: str, question_embedding: list[float], top_k: int = settings.rag_top_k):
    logger.info(f"Retrieving top {top_k} chunks for document {document_id}")
    
    # We use vector_cosine_ops or cosine_distance function from pgvector
    # smaller distance is closer
    stmt = (
        select(Embedding)
        .where(Embedding.document_id == document_id)
        .order_by(Embedding.embedding.cosine_distance(question_embedding))
        .limit(top_k)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()
    return chunks
