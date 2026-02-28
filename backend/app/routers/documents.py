import re
from pathlib import Path
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Document, DocumentPage
from app.core.logging import logger
from app.schemas.api import DocumentResponse, ErrorResponse
from app.services.pdf_parser import parse_pdf
from app.services.supabase_storage import storage_service

router = APIRouter(tags=["documents"])

ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    return cleaned[:180] or "document.pdf"


async def _read_upload_bytes(upload: UploadFile, max_bytes: int) -> bytes:
    data = bytearray()
    while chunk := await upload.read(UPLOAD_READ_CHUNK_SIZE):
        data.extend(chunk)
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max supported size is {settings.max_upload_mb}MB.",
            )
    return bytes(data)


@router.post(
    "/documents",
    response_model=DocumentResponse,
    summary="Upload a PDF and parse its pages",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file type or payload"},
        413: {"model": ErrorResponse, "description": "File too large"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    filename = file.filename or ""
    safe_name = _safe_filename(filename)
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    if file.content_type and file.content_type.lower() not in ALLOWED_PDF_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported content type for PDF upload.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    file_bytes = await _read_upload_bytes(file, max_bytes=max_bytes)

    doc = Document(filename=safe_name, storage_key="")
    db.add(doc)
    await db.flush()

    storage_key = f"{doc.id}/{safe_name}"
    await run_in_threadpool(storage_service.upload_file, file_bytes, storage_key, "application/pdf")
    doc.storage_key = storage_key

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
    except ValueError as exc:
        await db.rollback()
        logger.warning("upload_rejected document_id=%s reason=%s", doc.id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.error("document_upload_failed document_id=%s error=%s", doc.id, exc)
        raise HTTPException(status_code=500, detail="Failed to parse PDF document.") from exc
    finally:
        await file.close()

    await db.commit()
    await db.refresh(doc)
    return doc

@router.get("/documents", response_model=List[DocumentResponse], summary="List uploaded documents")
async def list_documents(
    skip: int = Query(default=0, ge=0, description="Number of items to skip."),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get a document by ID",
    responses={404: {"model": ErrorResponse, "description": "Document not found"}},
)
async def get_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
