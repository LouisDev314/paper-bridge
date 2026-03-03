from typing import Any, Dict, Literal, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    checksum_sha256: str
    version: int
    total_pages: int
    status: Literal["uploaded", "processing", "ready", "failed"]
    created_at: datetime

    class Config:
        from_attributes = True


class UploadDocumentResponse(DocumentResponse):
    pipeline_job_id: Optional[UUID] = None


class DownloadDocumentResponse(BaseModel):
    url: str
    filename: str


class JobResponse(BaseModel):
    id: UUID
    document_id: UUID
    task_type: str
    status: str
    error_message: Optional[str]
    task_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ErrorDetail(BaseModel):
    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error message")
    request_id: Optional[str] = Field(default=None, description="Request correlation ID")


class ErrorResponse(BaseModel):
    error: ErrorDetail
