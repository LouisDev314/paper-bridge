import hashlib
import re
from pathlib import Path
from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import Document, DocumentPage
from app.schemas.api import DocumentResponse, ErrorResponse, UploadDocumentResponse
from app.services.pipeline import ensure_pipeline_job, run_pipeline_job
from app.services.pdf_parser import parse_pdf
from app.services.supabase_storage import storage_service

router = APIRouter(tags=["documents"])

ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024


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


def _to_upload_response(document: Document, pipeline_job_id: UUID | None = None) -> UploadDocumentResponse:
    payload = UploadDocumentResponse.model_validate(document)
    payload.pipeline_job_id = pipeline_job_id
    return payload


async def _queue_pipeline_if_requested(
    *,
    request_id: str | None,
    document_id: UUID,
    auto_process: bool,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> UUID | None:
    if not auto_process:
        return None
    pipeline_job = await ensure_pipeline_job(document_id=document_id, db=db, request_id=request_id)
    if pipeline_job.status == "queued":
        background_tasks.add_task(run_pipeline_job, pipeline_job.id, request_id)
    return pipeline_job.id


async def _ingest_pdf_upload(
    *,
    request_id: str | None,
    file: UploadFile,
    dedupe: bool,
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

    existing_doc = (
        await db.execute(
            select(Document)
            .where(Document.checksum_sha256 == checksum_sha256)
            .order_by(Document.version.desc())
            .limit(1)
        )
    ).scalars().first()

    if dedupe and existing_doc:
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
    if existing_doc:
        version = int(existing_doc.version) + 1

    doc = Document(filename=safe_name, storage_key="", checksum_sha256=checksum_sha256, version=version)
    db.add(doc)
    await db.flush()

    storage_key = f"documents/{checksum_sha256[:16]}/v{version}/{safe_name}"
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
        doc.storage_key = storage_key

        total_pages, pages_data = await parse_pdf(file_bytes, str(doc.id))
        doc.total_pages = total_pages

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

    await db.commit()
    await db.refresh(doc)
    logger.info(
        "upload_complete request_id=%s document_id=%s total_pages=%s checksum=%s version=%s",
        request_id,
        doc.id,
        doc.total_pages,
        doc.checksum_sha256,
        doc.version,
    )
    return doc


@router.post(
    "/documents",
    response_model=UploadDocumentResponse,
    summary="Upload a PDF and parse its pages",
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
    dedupe: bool = Query(
        default=True,
        description="If true, returns the existing document when this exact file checksum already exists.",
    ),
    auto_process: bool = Query(
        default=False,
        description="If true, automatically orchestrates extract then embed as a pipeline job.",
    ),
    db: AsyncSession = Depends(get_db),
):
    request_id = getattr(request.state, "request_id", None)
    document = await _ingest_pdf_upload(request_id=request_id, file=file, dedupe=dedupe, db=db)
    pipeline_job_id = await _queue_pipeline_if_requested(
        request_id=request_id,
        document_id=document.id,
        auto_process=auto_process,
        background_tasks=background_tasks,
        db=db,
    )
    return _to_upload_response(document, pipeline_job_id)


@router.post(
    "/documents/batch",
    response_model=List[UploadDocumentResponse],
    summary="Upload multiple PDFs and parse pages",
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
    dedupe: bool = Query(
        default=True,
        description="If true, returns the existing document when an exact file checksum already exists.",
    ),
    auto_process: bool = Query(
        default=False,
        description="If true, automatically orchestrates extract then embed for each uploaded document.",
    ),
    db: AsyncSession = Depends(get_db),
):
    request_id = getattr(request.state, "request_id", None)
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    responses: list[UploadDocumentResponse] = []
    for upload in files:
        document = await _ingest_pdf_upload(request_id=request_id, file=upload, dedupe=dedupe, db=db)
        pipeline_job_id = await _queue_pipeline_if_requested(
            request_id=request_id,
            document_id=document.id,
            auto_process=auto_process,
            background_tasks=background_tasks,
            db=db,
        )
        responses.append(_to_upload_response(document, pipeline_job_id))
    return responses


@router.get("/documents", response_model=List[DocumentResponse], summary="List uploaded documents")
async def list_documents(
    skip: int = Query(default=0, ge=0, description="Number of items to skip."),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()).offset(skip).limit(limit))
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

    storage_paths = [doc.storage_key] + [p.page_image_key for p in doc.pages if p.page_image_key]
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

    await db.delete(doc)
    await db.commit()
    logger.info("document_deleted request_id=%s document_id=%s", request_id, document_id)
    return Response(status_code=204)
