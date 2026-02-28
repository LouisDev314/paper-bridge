from fastapi import APIRouter, Depends, HTTPException
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
async def global_ask(req: AskRequest, db: AsyncSession = Depends(get_db)):
    try:
        q_emb = (await generate_embeddings([req.question]))[0]
    except Exception as exc:
        logger.error("question_embedding_failed error=%s", exc)
        raise HTTPException(status_code=502, detail="Failed to embed question.") from exc

    top_k = req.top_k if req.top_k is not None else settings.rag_top_k
    chunks: list[RetrievedChunk] = await retrieve_chunks(
        db=db,
        question_embedding=q_emb,
        top_k=top_k,
        document_ids=req.doc_ids,
    )

    if not chunks:
        return AskResponse(
            answer="No context available. Please embed documents first.",
            citations=[],
        )

    return await answer_question(req.question, chunks)
