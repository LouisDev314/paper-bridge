from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.database import get_db
from app.db.models import Document
from app.schemas.qa import AskRequest, AskResponse
from app.services.embedder import generate_embeddings
from app.services.retriever import retrieve_chunks
from app.services.qa import answer_question

router = APIRouter(tags=["ask"])

@router.post("/documents/{document_id}/ask", response_model=AskResponse)
async def ask_question(document_id: UUID, req: AskRequest, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    question_embedding = (await generate_embeddings([req.question]))[0]
    chunks = await retrieve_chunks(db, str(document_id), question_embedding)
    
    if not chunks:
        return AskResponse(answer="No context available. Please embed the document first.", citations=[])
        
    response = await answer_question(req.question, chunks)
    return response
