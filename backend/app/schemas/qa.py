from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class AskRequest(BaseModel):
    question: str
    document_ids: Optional[List[UUID]] = None
    top_k: Optional[int] = None

class Citation(BaseModel):
    chunk_id: str
    document_id: UUID
    page_start: int
    page_end: int
    text: str

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
