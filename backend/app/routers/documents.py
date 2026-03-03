import hashlib
import re
from pathlib import Path
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import Document, DocumentPage, Embedding
from app.schemas.api import DocumentResponse, ErrorResponse, UploadDocumentResponse
from app.services.document_status import (
    DOCUMENT_STATUS_UPLOADED,
    compute_document_statuses,
)
from app.services.pdf_parser import parse_pdf
from app.services.pipeline import ensure_pipeline_job, run_pipeline_job
from app.services.supabase_storage import storage_service

router = APIRouter(tags=["documents"])

ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_URL_TTL_SECONDS = 120


def _safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
    return cleaned[:180] or "document.pdf"


def _compute_checksum(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


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


async def _queue_pipeline(
    *,
    request_id: str | None,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> UUID:
    pipeline_job = await ensure_pipeline_job(document_id=document_id, db=db, request_id=request_id)
    if pipeline_job.status == "queued":
        background_tasks.add_task(run_pipeline_job, pipeline_job.id, request_id)
    return pipeline_job.id


async def _existing_document_by_checksum(db: AsyncSession, checksum_sha256: str) -> Document | None:
    return (
        await db.execute(
            select(Document)
            .where(Document.checksum_sha256 == checksum_sha256)
            .order_by(Document.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def _ingest_pdf_upload(
    *,
    request_id: str | None,
    file: UploadFile,
    db: AsyncSession,
) -> Document:
    filename = file.filename or ""
    safe_name = _safe_filename(filename)
    if not safe_name.lower().endswith(".pdf"):
        await file.close()
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    if file.content_type and file.content_type.lower() not in ALLOWED_PDF_CONTENT_TYPES:
        await file.close()
        raise HTTPException(status_code=400, detail="Unsupported content type for PDF upload.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    file_bytes = await _read_upload_bytes(file, max_bytes=max_bytes)
    checksum_sha256 = _compute_checksum(file_bytes)

    existing_doc = await _existing_document_by_checksum(db, checksum_sha256)
    if existing_doc:
        logger.info(
            "upload_deduped request_id=%s checksum=%s existing_document_id=%s version=%s",
            request_id,
            checksum_sha256,
            existing_doc.id,
            existing_doc.version,
        )
        await file.close()
        return existing_doc

    version = 1
    document_id = uuid4()
    storage_key = f"documents/{checksum_sha256[:16]}/v{version}/{safe_name}"

    existing_storage_doc = (
        await db.execute(select(Document).where(Document.storage_key == storage_key).limit(1))
    ).scalars().first()
    if existing_storage_doc:
        logger.info(
            "upload_deduped_storage_key request_id=%s storage_key=%s existing_document_id=%s",
            request_id,
            storage_key,
            existing_storage_doc.id,
        )
        await file.close()
        return existing_storage_doc

    doc = Document(
        id=document_id,
        filename=safe_name,
        storage_key=storage_key,
        checksum_sha256=checksum_sha256,
        version=version,
        total_pages=0,
    )

    file_uploaded = False
    try:
        logger.info(
            "upload_start request_id=%s document_id=%s checksum=%s version=%s storage_key=%s",
            request_id,
            doc.id,
            checksum_sha256,
            version,
            storage_key,
        )
        await run_in_threadpool(storage_service.upload_file, file_bytes, storage_key, "application/pdf")
        file_uploaded = True

        total_pages, pages_data = await parse_pdf(file_bytes, str(doc.id))
        doc.total_pages = total_pages

        db.add(doc)
        for pd in pages_data:
            db.add(
                DocumentPage(
                    document_id=doc.id,
                    page_number=pd["page_number"],
                    text=pd["text"],
                    text_quality_score=pd["text_quality_score"],
                    page_image_key=pd["page_image_key"],
                )
            )
        await db.commit()
        await db.refresh(doc)
    except ValueError as exc:
        await db.rollback()
        if file_uploaded:
            await run_in_threadpool(storage_service.delete_files, [storage_key])
        logger.warning("upload_rejected request_id=%s document_id=%s reason=%s", request_id, doc.id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        if file_uploaded:
            await run_in_threadpool(storage_service.delete_files, [storage_key])
        logger.exception("document_upload_failed request_id=%s document_id=%s error=%s", request_id, doc.id, exc)
        raise HTTPException(status_code=500, detail="Failed to parse PDF document.") from exc
    finally:
        await file.close()

    logger.info(
        "upload_complete request_id=%s document_id=%s total_pages=%s checksum=%s version=%s",
        request_id,
        doc.id,
        doc.total_pages,
        doc.checksum_sha256,
        doc.version,
    )
    return doc


def _to_document_response(document: Document, status_value: str) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        checksum_sha256=document.checksum_sha256,
        version=document.version,
        total_pages=document.total_pages,
        status=status_value,
        created_at=document.created_at,
    )


def _to_upload_response(
    document: Document,
    *,
    status_value: str,
    pipeline_job_id: UUID | None,
) -> UploadDocumentResponse:
    return UploadDocumentResponse(
        id=document.id,
        filename=document.filename,
        checksum_sha256=document.checksum_sha256,
        version=document.version,
        total_pages=document.total_pages,
        status=status_value,
        created_at=document.created_at,
        pipeline_job_id=pipeline_job_id,
    )


@router.post(
    "/documents",
    response_model=UploadDocumentResponse,
    summary="Upload a PDF and trigger parse, extraction, and embedding pipeline",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file type or payload"},
        413: {"model": ErrorResponse, "description": "File too large"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    request_id = getattr(request.state, "request_id", None)
    document = await _ingest_pdf_upload(request_id=request_id, file=file, db=db)
    pipeline_job_id = await _queue_pipeline(
        request_id=request_id,
        document_id=document.id,
        background_tasks=background_tasks,
        db=db,
    )
    status_map = await compute_document_statuses(db, [document.id])
    return _to_upload_response(
        document,
        status_value=status_map.get(document.id, DOCUMENT_STATUS_UPLOADED),
        pipeline_job_id=pipeline_job_id,
    )


@router.post(
    "/documents/batch",
    response_model=List[UploadDocumentResponse],
    summary="Upload multiple PDFs and trigger parse, extraction, and embedding pipeline",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file type or payload"},
        413: {"model": ErrorResponse, "description": "File too large"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def batch_upload_documents(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    request_id = getattr(request.state, "request_id", None)
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    responses: list[UploadDocumentResponse] = []
    for upload in files:
        document = await _ingest_pdf_upload(request_id=request_id, file=upload, db=db)
        pipeline_job_id = await _queue_pipeline(
            request_id=request_id,
            document_id=document.id,
            background_tasks=background_tasks,
            db=db,
        )
        status_map = await compute_document_statuses(db, [document.id])
        responses.append(
            _to_upload_response(
                document,
                status_value=status_map.get(document.id, DOCUMENT_STATUS_UPLOADED),
                pipeline_job_id=pipeline_job_id,
            )
        )
    return responses


@router.get("/documents", response_model=List[DocumentResponse], summary="List uploaded documents")
async def list_documents(
    skip: int = Query(default=0, ge=0, description="Number of items to skip."),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()).offset(skip).limit(limit))
    documents = result.scalars().all()
    status_map = await compute_document_statuses(db, [document.id for document in documents])
    return [_to_document_response(document, status_map.get(document.id, DOCUMENT_STATUS_UPLOADED)) for document in documents]


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

    status_map = await compute_document_statuses(db, [doc.id])
    return _to_document_response(doc, status_map.get(doc.id, DOCUMENT_STATUS_UPLOADED))


@router.get(
    "/documents/{document_id}/download",
    response_class=RedirectResponse,
    summary="Download the original uploaded PDF via short-lived signed URL",
    responses={404: {"model": ErrorResponse, "description": "Document not found"}},
)
async def download_document(document_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    request_id = getattr(request.state, "request_id", None)
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        signed_url = await run_in_threadpool(
            storage_service.create_signed_download_url,
            doc.storage_key,
            expires_in=DOWNLOAD_URL_TTL_SECONDS,
            download_filename=doc.filename,
        )
    except Exception as exc:
        logger.error(
            "document_download_signed_url_failed request_id=%s document_id=%s storage_key=%s error=%s",
            request_id,
            document_id,
            doc.storage_key,
            exc,
        )
        raise HTTPException(status_code=502, detail="Failed to prepare document download.") from exc

    return RedirectResponse(url=signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a document and all dependent rows (pages/jobs/extractions/embeddings)",
    responses={404: {"model": ErrorResponse, "description": "Document not found"}},
)
async def delete_document(document_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    request_id = getattr(request.state, "request_id", None)
    doc = (
        await db.execute(
            select(Document).options(selectinload(Document.pages)).where(Document.id == document_id)
        )
    ).scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_paths = [doc.storage_key] + [page.page_image_key for page in doc.pages if page.page_image_key]
    if storage_paths:
        try:
            await run_in_threadpool(storage_service.delete_files, storage_paths)
        except Exception as exc:
            logger.warning(
                "document_delete_storage_cleanup_failed request_id=%s document_id=%s error=%s",
                request_id,
                document_id,
                exc,
            )

    await db.execute(delete(Embedding).where(Embedding.document_id == document_id))
    await db.delete(doc)
    await db.commit()
    logger.info("document_deleted request_id=%s document_id=%s", request_id, document_id)
    return Response(status_code=204)
