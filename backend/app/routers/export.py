from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import csv
import io

from app.db.database import get_db
from app.db.models import Document, Extraction
from app.schemas.api import ErrorResponse

router = APIRouter(tags=["export"])

@router.get(
    "/documents/{document_id}/export.json",
    summary="Export latest extraction as JSON",
    responses={404: {"model": ErrorResponse, "description": "Document or extraction not found"}},
)
async def export_json(document_id: UUID, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    result = await db.execute(select(Extraction).where(Extraction.document_id == document_id).order_by(Extraction.created_at.desc()))
    extraction = result.scalars().first()
    
    if not extraction:
        raise HTTPException(status_code=404, detail="No extractions found for this document")
        
    return JSONResponse(content=extraction.data)

@router.get(
    "/documents/{document_id}/export.csv",
    summary="Export latest extraction as CSV",
    responses={404: {"model": ErrorResponse, "description": "Document or extraction not found"}},
)
async def export_csv(document_id: UUID, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    result = await db.execute(select(Extraction).where(Extraction.document_id == document_id).order_by(Extraction.created_at.desc()))
    extraction = result.scalars().first()
    
    if not extraction:
        raise HTTPException(status_code=404, detail="No extractions found for this document")
        
    data = extraction.data
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    headers = [k for k in data.keys() if k != "line_items"]
    writer.writerow(headers)
    writer.writerow([data.get(h, "") for h in headers])
    
    if "line_items" in data and isinstance(data["line_items"], list) and len(data["line_items"]) > 0:
        writer.writerow([])
        writer.writerow(["--- LINE ITEMS ---"])
        li_headers = list(data["line_items"][0].keys())
        writer.writerow(li_headers)
        for li in data["line_items"]:
            writer.writerow([li.get(lh, "") for lh in li_headers])
            
    csv_str = output.getvalue()
    return Response(content=csv_str, media_type="text/csv")
