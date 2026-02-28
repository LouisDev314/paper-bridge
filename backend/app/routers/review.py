from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.database import get_db
from app.db.models import Extraction, ReviewEdit
from app.schemas.api import ErrorResponse
from app.schemas.review import ReviewEditRequest, ReviewEditResponse

router = APIRouter(tags=["review"])

@router.post(
    "/extractions/{extraction_id}/review",
    response_model=ReviewEditResponse,
    summary="Submit reviewed extraction data",
    responses={404: {"model": ErrorResponse, "description": "Extraction not found"}},
)
async def submit_review(extraction_id: UUID, req: ReviewEditRequest, db: AsyncSession = Depends(get_db)):
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
        
    edit = ReviewEdit(
        extraction_id=extraction.id,
        original_data=extraction.data,
        updated_data=req.updated_data,
        edited_by=req.edited_by
    )
    db.add(edit)

    extraction.data = req.updated_data

    await db.commit()
    await db.refresh(edit)

    return edit
