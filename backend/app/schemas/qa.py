from typing import List, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

class AskRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "question": "What are the payment terms across these supplier agreements?",
                    "doc_ids": [
                        "9c6c9f55-4d4f-4712-bf81-31e72f7a9b32",
                        "117082e7-9f8d-477d-a64b-599f26ff74ca",
                    ],
                }
            ]
        },
        extra="forbid",
    )

    question: str = Field(..., min_length=3, max_length=4000)
    doc_ids: Optional[List[UUID]] = Field(
        default=None,
        validation_alias=AliasChoices("doc_ids", "document_ids"),
        description="Optional list of document IDs to scope retrieval. If omitted, searches all embedded documents.",
    )

    @field_validator("doc_ids")
    @classmethod
    def dedupe_doc_ids(cls, value: Optional[List[UUID]]) -> Optional[List[UUID]]:
        if not value:
            return value
        return list(dict.fromkeys(value))

class Citation(BaseModel):
    filename: str
    page_start: int
    page_end: int

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
