from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.db.database import get_db
from app.db.models import Document, DocumentPage
from app.schemas.api import DocumentResponse
from app.services.supabase_storage import storage_service
from app.services.pdf_parser import parse_pdf
from app.core.logging import logger

router = APIRouter(tags=["documents"])

@router.post("/documents", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    file_bytes = await file.read()
    
    doc = Document(filename=file.filename, storage_key="")
    db.add(doc)
    await db.flush()
    
    storage_key = f"{doc.id}/{file.filename}"
    storage_service.upload_file(file_bytes, storage_key)
    doc.storage_key = storage_key
    
    # Parse PDF and create pages synchronously for now, if it takes long we could move to jobs
    try:
        total_pages, pages_data = await parse_pdf(file_bytes, str(doc.id))
        doc.total_pages = total_pages
        
        for pd in pages_data:
            page = DocumentPage(
                document_id=doc.id,
                page_number=pd["page_number"],
                text=pd["text"],
                text_quality_score=pd["text_quality_score"],
                page_image_key=pd["page_image_key"]
            )
            db.add(page)
    except Exception as e:
        logger.error(f"Failed parsing PDF {doc.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse PDF document.")
        
    await db.commit()
    await db.refresh(doc)
    return doc

@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return result.scalars().all()

@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
