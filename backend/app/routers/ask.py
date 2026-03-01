from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.database import get_db
from app.schemas.api import ErrorResponse
from app.schemas.qa import AskRequest, AskResponse
from app.services.embedder import generate_embeddings
from app.services.retriever import RetrievedChunk, retrieve_chunks
from app.services.qa import answer_question

router = APIRouter(tags=["ask"])

@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question across one or more documents",
    description=(
        "Runs semantic retrieval and grounded QA. "
        "Use `doc_ids` to restrict retrieval to selected documents."
    ),
    responses={
        422: {"model": ErrorResponse, "description": "Request validation failed"},
        502: {"model": ErrorResponse, "description": "Failed upstream model call"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def global_ask(req: AskRequest, request: Request, db: AsyncSession = Depends(get_db)):
    request_id = getattr(request.state, "request_id", None)
    top_k = req.top_k if req.top_k is not None else settings.rag_top_k
    top_k = max(1, min(top_k, settings.rag_max_top_k))
    logger.info(
        "ask_request request_id=%s top_k=%s embedding_model=%s chat_model=%s filters_document_ids=%s",
        request_id,
        top_k,
        settings.openai_embed_model,
        settings.chat_model,
        [str(doc_id) for doc_id in req.doc_ids] if req.doc_ids else [],
    )

    try:
        q_emb = (await generate_embeddings([req.question], request_id=request_id))[0]
    except Exception as exc:
        logger.error("question_embedding_failed request_id=%s error=%s", request_id, exc)
        raise HTTPException(status_code=502, detail="Failed to embed question.") from exc

    chunks: list[RetrievedChunk] = await retrieve_chunks(
        db=db,
        question=req.question,
        question_embedding=q_emb,
        top_k=top_k,
        document_ids=req.doc_ids,
        vector_candidates=settings.rag_vector_candidates,
        lexical_weight=settings.rag_lexical_weight,
        request_id=request_id,
    )

    if not chunks:
        return AskResponse(
            answer="Not found in the provided documents.",
            citations=[],
        )

    return await answer_question(req.question, chunks, request_id=request_id)
