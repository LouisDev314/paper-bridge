from dataclasses import dataclass
import re
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_request_id, logger
from app.db.models import Document, Embedding
from app.services.embedder import generate_embeddings

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
DIRECTIVE_ANCHORS = (
    "solution gas",
    "conservation",
    "economic evaluation",
    "npv",
    "-55,000",
    "900 m3/day",
    "gor",
    "3000 m3/m3",
    "nonroutine",
    "planned flaring",
    "public notification",
    "aer field centre",
    "h2s",
    "incineration",
    "enclosed combustion",
)
NUMERIC_UNIT_RE = re.compile(
    r"(\d[\d,.\-]*)\s*(m3/day|m3/d|m3/m3|m3|hours?|hour|days?|day|%|dollars?|mol/kmol)"
)


@dataclass
class RetrievedChunk:
    embedding: Embedding
    filename: str
    distance: float | None
    vector_similarity: float | None
    lexical_score: float
    combined_score: float
    rank: int


@dataclass
class _MergedCandidate:
    embedding: Embedding
    filename: str
    best_distance: float | None
    query_hits: int


def _clip(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def _normalize_match_text(text: str) -> str:
    return (
        text.lower()
        .replace("m³", "m3")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )


def _keyword_tokens(text: str) -> list[str]:
    normalized = _normalize_match_text(text).replace("/", " ")
    raw_tokens = normalized.split()
    clean_tokens = []
    for token in raw_tokens:
        token = "".join(ch for ch in token if ch.isalnum() or ch in "-$")
        if len(token) < 3 or token in STOPWORDS:
            continue
        clean_tokens.append(token)
    return list(dict.fromkeys(clean_tokens))


def _question_suggests_flaring_economics(question: str) -> bool:
    lower = _normalize_match_text(question)
    return any(
        keyword in lower
        for keyword in (
            "solution gas",
            "flaring",
            "allowed",
            "conservation",
            "economic",
            "npv",
            "gor",
        )
    )


def _question_suggests_procedural(question: str) -> bool:
    lower = _normalize_match_text(question)
    return any(
        keyword in lower
        for keyword in (
            "notify",
            "notification",
            "public",
            "planned",
            "required",
            "must",
            "report",
            "field centre",
            "incineration",
            "enclosed combustion",
        )
    )


def _build_query_expansions(question: str) -> list[str]:
    base = " ".join(question.split()).strip()
    if not base:
        return [question]

    lower = _normalize_match_text(base)
    expanded: list[str] = [base]

    if "allowed" in lower:
        expanded.append(f"{base} permitted conditions thresholds limits")
    elif "must" in lower or "required" in lower:
        expanded.append(f"{base} mandatory requirements thresholds limits")
    else:
        expanded.append(f"{base} directive requirements thresholds limits")

    if _question_suggests_flaring_economics(base):
        expanded.append(
            "Directive 060 solution gas conservation economic evaluation NPV -55,000 900 m3/day GOR 3000 m3/m3"
        )

    if _question_suggests_procedural(base):
        expanded.append(
            "Directive 060 planned flaring incineration enclosed combustion public notification 24 72 hours AER field centre H2S"
        )

    if len(expanded) < 3:
        expanded.append(
            "Directive 060 solution gas conservation thresholds NPV GOR m3/day m3/m3 public notification AER field centre"
        )
    if len(expanded) < 4:
        expanded.append(
            "Directive 060 compliance criteria limits conditions required reporting and notification thresholds"
        )

    deduped: list[str] = []
    seen: set[str] = set()
    for query in expanded:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)
    return deduped[:5]


def _question_needs_numeric_focus(question: str) -> bool:
    lower = _normalize_match_text(question)
    return any(
        keyword in lower
        for keyword in ("allowed", "must", "required", "threshold", "limit", "npv", "gor", "hours", "when")
    )


def _keyword_boost_score(content: str, question: str) -> float:
    text = _normalize_match_text(content)
    needs_numeric = _question_needs_numeric_focus(question)

    score = 0.0
    if re.search(r"\d", text):
        score += 0.12 if needs_numeric else 0.06
    if NUMERIC_UNIT_RE.search(text):
        score += 0.18
    if "npv" in text:
        score += 0.12
    if "gor" in text:
        score += 0.12
    if "h2s" in text:
        score += 0.10
    if "$" in content or "dollar" in text:
        score += 0.10
    if "aer" in text or "field centre" in text:
        score += 0.08

    anchor_hits = sum(1 for term in DIRECTIVE_ANCHORS if term in text)
    score += min(0.24, 0.04 * anchor_hits)
    return _clip(score)


def _is_numeric_threshold_chunk(chunk: RetrievedChunk) -> bool:
    content = _normalize_match_text(chunk.embedding.content)
    if not re.search(r"\d", content):
        return False
    return bool(
        NUMERIC_UNIT_RE.search(content)
        or any(keyword in content for keyword in ("npv", "gor", "threshold", "limit", "$"))
    )


def _is_procedural_chunk(chunk: RetrievedChunk) -> bool:
    content = _normalize_match_text(chunk.embedding.content)
    return any(
        keyword in content
        for keyword in (
            "notify",
            "notification",
            "report",
            "field centre",
            "public",
            "planned flaring",
            "incineration",
            "enclosed combustion",
            "must",
            "required",
        )
    )


def _dedupe_by_pdf_page(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    deduped: list[RetrievedChunk] = []
    seen: set[tuple[UUID, int, int]] = set()
    for chunk in chunks:
        key = (
            chunk.embedding.document_id,
            int(chunk.embedding.pdf_page_start),
            int(chunk.embedding.pdf_page_end),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _select_diverse_top_chunks(question: str, ranked_chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    deduped_ranked = _dedupe_by_pdf_page(ranked_chunks)
    selected: list[RetrievedChunk] = []
    selected_ids: set[str] = set()

    def _add(chunk: RetrievedChunk | None) -> None:
        if chunk is None:
            return
        chunk_id = str(chunk.embedding.id)
        if chunk_id in selected_ids:
            return
        selected_ids.add(chunk_id)
        selected.append(chunk)

    # Always try to include a numeric-threshold chunk when present.
    _add(next((chunk for chunk in deduped_ranked if _is_numeric_threshold_chunk(chunk)), None))

    # For notification/reporting-style questions, ensure one procedural chunk.
    if _question_suggests_procedural(question):
        _add(next((chunk for chunk in deduped_ranked if _is_procedural_chunk(chunk)), None))

    for chunk in deduped_ranked:
        if len(selected) >= top_k:
            break
        _add(chunk)
    return selected[:top_k]


async def retrieve_chunks(
    db: AsyncSession,
    question: str,
    question_embedding: list[float],
    document_ids: list[UUID] | None = None,
    top_k: int = settings.qa_top_k,
    vector_candidates: int = settings.rag_vector_candidates,
    lexical_weight: float = settings.rag_lexical_weight,
    request_id: str | None = None,
) -> list[RetrievedChunk]:
    req_id = request_id or get_request_id()
    safe_top_k = max(1, min(top_k, settings.rag_max_top_k))
    safe_vector_candidates = max(safe_top_k, min(vector_candidates, 200))
    safe_lexical_weight = _clip(lexical_weight)
    query_variants = _build_query_expansions(question)
    per_query_candidates = max(
        safe_top_k * 2,
        min(40, int((safe_vector_candidates * 1.2) / max(1, len(query_variants))) + safe_top_k),
    )

    logger.info(
        "retrieval_start request_id=%s top_k=%s vector_candidates=%s lexical_weight=%.2f query_variants=%s filters_document_ids=%s",
        req_id,
        safe_top_k,
        safe_vector_candidates,
        safe_lexical_weight,
        query_variants,
        [str(doc_id) for doc_id in document_ids] if document_ids else [],
    )

    await db.execute(text(f"SET LOCAL ivfflat.probes = {settings.vector_ivfflat_probes}"))

    query_embeddings: list[list[float]] = [question_embedding]
    if len(query_variants) > 1:
        try:
            query_embeddings.extend(await generate_embeddings(query_variants[1:], request_id=req_id))
        except Exception as exc:
            logger.warning("retrieval_query_expansion_embedding_failed request_id=%s error=%s", req_id, exc)
            query_variants = query_variants[:1]
            query_embeddings = [question_embedding]

    merged_candidates: dict[str, _MergedCandidate] = {}
    for query_idx, embedding_vector in enumerate(query_embeddings):
        distance = Embedding.embedding.cosine_distance(embedding_vector).label("distance")
        vector_stmt = (
            select(Embedding, Document.filename, distance)
            .join(Document, Document.id == Embedding.document_id)
        )
        if document_ids:
            vector_stmt = vector_stmt.where(Embedding.document_id.in_(document_ids))
        vector_stmt = vector_stmt.order_by(distance.asc()).limit(per_query_candidates)
        vector_rows = (await db.execute(vector_stmt)).all()

        for embedding_row, filename, dist in vector_rows:
            candidate_id = str(embedding_row.id)
            distance_value = float(dist) if dist is not None else None
            existing = merged_candidates.get(candidate_id)
            if not existing:
                merged_candidates[candidate_id] = _MergedCandidate(
                    embedding=embedding_row,
                    filename=filename,
                    best_distance=distance_value,
                    query_hits=1,
                )
                continue

            existing.query_hits += 1
            if existing.best_distance is None:
                existing.best_distance = distance_value
            elif distance_value is not None and distance_value < existing.best_distance:
                existing.best_distance = distance_value

        logger.debug(
            "retrieval_query_variant_scanned request_id=%s query_index=%s rows=%s",
            req_id,
            query_idx,
            len(vector_rows),
        )

    if not merged_candidates:
        logger.info("retrieval_no_candidates request_id=%s", req_id)
        return []

    lexical_scores: dict[str, float] = {}
    candidate_ids = [candidate.embedding.id for candidate in merged_candidates.values()]
    keyword_tokens = _keyword_tokens(" ".join(query_variants))
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
    for candidate in merged_candidates.values():
        embedding_row = candidate.embedding
        content_lower = _normalize_match_text(embedding_row.content)
        token_hits = 0
        if keyword_tokens:
            token_hits = sum(1 for token in keyword_tokens if token in content_lower)
        overlap_score = (token_hits / len(keyword_tokens)) if keyword_tokens else 0.0

        vector_similarity = None if candidate.best_distance is None else _clip(1.0 - candidate.best_distance)
        ts_rank_score = _clip(lexical_scores.get(str(embedding_row.id), 0.0))
        keyword_boost = _keyword_boost_score(embedding_row.content, question)
        query_hit_bonus = min(0.2, max(0.0, 0.05 * (candidate.query_hits - 1)))
        lexical_score = _clip((0.45 * ts_rank_score) + (0.30 * overlap_score) + (0.25 * keyword_boost))
        vec_score = vector_similarity if vector_similarity is not None else 0.0
        combined_score = _clip(
            ((1.0 - safe_lexical_weight) * vec_score)
            + (safe_lexical_weight * lexical_score)
            + query_hit_bonus
        )
        retrieved.append(
            RetrievedChunk(
                embedding=embedding_row,
                filename=candidate.filename,
                distance=candidate.best_distance,
                vector_similarity=vector_similarity,
                lexical_score=lexical_score,
                combined_score=combined_score,
                rank=0,
            )
        )

    retrieved.sort(key=lambda chunk: (-chunk.combined_score, chunk.distance if chunk.distance is not None else 10.0))
    final_chunks = _select_diverse_top_chunks(question, retrieved, safe_top_k)

    for idx, chunk in enumerate(final_chunks, start=1):
        chunk.rank = idx

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
