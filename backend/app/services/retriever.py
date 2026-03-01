from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_request_id, logger
from app.db.models import Embedding

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "does",
    "for",
    "in",
    "is",
    "of",
    "or",
    "the",
    "to",
    "what",
    "which",
}


@dataclass
class RetrievedChunk:
    embedding: Embedding
    distance: float | None
    vector_similarity: float | None
    lexical_score: float
    combined_score: float
    rank: int


def _clip(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def _keyword_tokens(question: str) -> list[str]:
    raw_tokens = [token.lower() for token in question.replace("/", " ").split()]
    clean_tokens = []
    for token in raw_tokens:
        token = "".join(ch for ch in token if ch.isalnum())
        if len(token) < 3 or token in STOPWORDS:
            continue
        clean_tokens.append(token)
    return clean_tokens


async def retrieve_chunks(
    db: AsyncSession,
    question: str,
    question_embedding: list[float],
    document_ids: list[UUID] | None = None,
    top_k: int = settings.rag_top_k,
    vector_candidates: int = settings.rag_vector_candidates,
    lexical_weight: float = settings.rag_lexical_weight,
    request_id: str | None = None,
) -> list[RetrievedChunk]:
    req_id = request_id or get_request_id()
    safe_top_k = max(1, min(top_k, settings.rag_max_top_k))
    safe_vector_candidates = max(safe_top_k, min(vector_candidates, 200))
    safe_lexical_weight = _clip(lexical_weight)

    logger.info(
        "retrieval_start request_id=%s top_k=%s vector_candidates=%s lexical_weight=%.2f filters_document_ids=%s",
        req_id,
        safe_top_k,
        safe_vector_candidates,
        safe_lexical_weight,
        [str(doc_id) for doc_id in document_ids] if document_ids else [],
    )

    await db.execute(text(f"SET LOCAL ivfflat.probes = {settings.vector_ivfflat_probes}"))

    distance = Embedding.embedding.cosine_distance(question_embedding).label("distance")
    vector_stmt = select(Embedding, distance)
    if document_ids:
        vector_stmt = vector_stmt.where(Embedding.document_id.in_(document_ids))
    vector_stmt = vector_stmt.order_by(distance.asc()).limit(safe_vector_candidates)

    vector_rows = (await db.execute(vector_stmt)).all()
    if not vector_rows:
        logger.info("retrieval_no_candidates request_id=%s", req_id)
        return []

    lexical_scores: dict[str, float] = {}
    candidate_ids = [row[0].id for row in vector_rows]
    keyword_tokens = _keyword_tokens(question)
    try:
        lexical_stmt = (
            select(
                Embedding.id,
                func.ts_rank_cd(
                    func.to_tsvector("english", Embedding.content),
                    func.websearch_to_tsquery("english", question),
                ).label("lexical_score"),
            )
            .where(Embedding.id.in_(candidate_ids))
        )
        lexical_rows = (await db.execute(lexical_stmt)).all()
        lexical_scores = {str(row[0]): float(row[1] or 0.0) for row in lexical_rows}
    except Exception as exc:
        logger.warning("retrieval_lexical_rerank_failed request_id=%s error=%s", req_id, exc)

    retrieved: list[RetrievedChunk] = []
    for embedding_row, dist in vector_rows:
        content_lower = embedding_row.content.lower()
        token_hits = 0
        if keyword_tokens:
            token_hits = sum(1 for token in keyword_tokens if token in content_lower)
        overlap_score = (token_hits / len(keyword_tokens)) if keyword_tokens else 0.0

        vector_similarity = None if dist is None else _clip(1.0 - float(dist))
        ts_rank_score = _clip(lexical_scores.get(str(embedding_row.id), 0.0))
        lexical_score = _clip((0.7 * ts_rank_score) + (0.3 * overlap_score))
        vec_score = vector_similarity if vector_similarity is not None else 0.0
        combined_score = ((1.0 - safe_lexical_weight) * vec_score) + (safe_lexical_weight * lexical_score)
        retrieved.append(
            RetrievedChunk(
                embedding=embedding_row,
                distance=float(dist) if dist is not None else None,
                vector_similarity=vector_similarity,
                lexical_score=lexical_score,
                combined_score=combined_score,
                rank=0,
            )
        )

    retrieved.sort(key=lambda chunk: (-chunk.combined_score, chunk.distance if chunk.distance is not None else 10.0))

    for idx, chunk in enumerate(retrieved, start=1):
        chunk.rank = idx

    final_chunks = retrieved[:safe_top_k]
    logger.info(
        "retrieval_complete request_id=%s retrieved=%s top_chunks=%s",
        req_id,
        len(final_chunks),
        [
            {
                "chunk_id": chunk.embedding.chunk_id,
                "document_id": str(chunk.embedding.document_id),
                "distance": round(chunk.distance or 0.0, 6),
                "vector_similarity": round(chunk.vector_similarity or 0.0, 6),
                "lexical_score": round(chunk.lexical_score, 6),
                "combined_score": round(chunk.combined_score, 6),
                "pdf_page_start": chunk.embedding.pdf_page_start,
                "pdf_page_end": chunk.embedding.pdf_page_end,
            }
            for chunk in final_chunks
        ],
    )
    return final_chunks
