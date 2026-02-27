from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Document, Job, DocumentPage, Embedding
from app.schemas.api import JobResponse
from app.services.chunker import chunk_text
from app.services.embedder import generate_embeddings
from app.core.logging import logger

router = APIRouter(tags=["embed"])

async def run_embed_job(job_id: UUID):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job: return
        
        job.status = "processing"
        await db.commit()
        
        try:
            result = await db.execute(select(DocumentPage).where(DocumentPage.document_id == job.document_id).order_by(DocumentPage.page_number))
            pages = result.scalars().all()
            
            all_chunks = []
            for page in pages:
                if not page.text: continue
                page_chunks = chunk_text(page.text)
                for i, c in enumerate(page_chunks):
                    all_chunks.append({
                        "chunk_id": f"p{page.page_number}-c{i}",
                        "page_start": page.page_number,
                        "page_end": page.page_number,
                        "content": c
                    })
            
            if not all_chunks:
                job.status = "done"
                await db.commit()
                return
                
            texts = [c["content"] for c in all_chunks]
            
            batch_size = 100
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i+batch_size]
                batch_embeddings = await generate_embeddings(batch_texts)
                
                for j, emb in enumerate(batch_embeddings):
                    chunk_meta = all_chunks[i+j]
                    db.add(Embedding(
                        document_id=job.document_id,
                        chunk_id=chunk_meta["chunk_id"],
                        page_start=chunk_meta["page_start"],
                        page_end=chunk_meta["page_end"],
                        content=chunk_meta["content"],
                        embedding=emb
                    ))
                    
            job.status = "done"
            await db.commit()
            
        except Exception as e:
            logger.error(f"Embed job {job_id} failed: {e}")
            job.status = "failed"
            job.error_message = str(e)
            await db.commit()

@router.post("/documents/{document_id}/embed", response_model=JobResponse)
async def trigger_embed(document_id: UUID, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    job = Job(document_id=document_id, task_type="embed", status="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    background_tasks.add_task(run_embed_job, job.id)
    return job
