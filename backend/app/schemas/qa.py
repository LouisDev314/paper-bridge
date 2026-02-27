from pydantic import BaseModel
from typing import List

class AskRequest(BaseModel):
    question: str

class Citation(BaseModel):
    chunk_id: str
    page_start: int
    page_end: int
    text: str

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
