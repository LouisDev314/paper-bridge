from pydantic import BaseModel
from typing import Optional, Any, Dict
from uuid import UUID
from datetime import datetime

class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    total_pages: int
    created_at: datetime

    class Config:
        from_attributes = True

class JobResponse(BaseModel):
    id: UUID
    document_id: UUID
    task_type: str
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ExportResponse(BaseModel):
    data: Dict[str, Any]
    status: str
