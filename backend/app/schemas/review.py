from pydantic import BaseModel
from typing import Any, Dict, Optional
from uuid import UUID
from datetime import datetime

class ReviewEditRequest(BaseModel):
    updated_data: Dict[str, Any]
    edited_by: Optional[str] = None

class ReviewEditResponse(BaseModel):
    id: UUID
    extraction_id: UUID
    original_data: Dict[str, Any]
    updated_data: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
