from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Document, Job, DocumentPage, Extraction
from app.schemas.api import JobResponse
from app.services.extractor import extract_document_features
from app.services.validator import validate_extraction
from app.core.logging import logger

router = APIRouter(tags=["extract"])

async def run_extraction_job(job_id: UUID):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job: return
        
        job.status = "processing"
        await db.commit()
        
        try:
            result = await db.execute(select(DocumentPage).where(DocumentPage.document_id == job.document_id).order_by(DocumentPage.page_number))
            pages = result.scalars().all()
            full_text = "\n\n".join([p.text or "" for p in pages])
            
            extraction_pydantic = await extract_document_features(full_text)
            status = validate_extraction(extraction_pydantic)
            
            extraction_entry = Extraction(
                document_id=job.document_id,
                data=extraction_pydantic.model_dump(),
                status=status
            )
            db.add(extraction_entry)
            
            job.status = "done"
            # Alternatively mark job as needs_review if flagged? Prompt: "Jobs table must support... needs_review".
            if status == "FLAGGED":
                job.status = "needs_review"
                
            await db.commit()
            
        except Exception as e:
            logger.error(f"Extraction job {job_id} failed: {e}")
            job.status = "failed"
            job.error_message = str(e)
            await db.commit()

@router.post("/documents/{document_id}/extract", response_model=JobResponse)
async def trigger_extraction(document_id: UUID, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    job = Job(document_id=document_id, task_type="extract", status="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    background_tasks.add_task(run_extraction_job, job.id)
    return job
