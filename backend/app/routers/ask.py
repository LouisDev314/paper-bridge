from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.config import settings
from app.schemas.qa import AskRequest, AskResponse
from app.services.embedder import generate_embeddings
from app.services.retriever import retrieve_chunks
from app.services.qa import answer_question

router = APIRouter(tags=["ask"])

@router.post("/ask", response_model=AskResponse)
async def global_ask(req: AskRequest, db: AsyncSession = Depends(get_db)):
    # 1) embed question
    q_emb = (await generate_embeddings([req.question]))[0]

    # 2) retrieve across ALL documents (or limited set)
    top_k = req.top_k if req.top_k is not None else settings.rag_top_k
    chunks = await retrieve_chunks(
        db=db,
        question_embedding=q_emb,
        top_k=top_k,
        document_ids=req.document_ids,
    )

    if not chunks:
        return AskResponse(
            answer="No context available. Please embed documents first.",
            citations=[],
        )

    # 3) answer with existing QA service
    return await answer_question(req.question, chunks)
