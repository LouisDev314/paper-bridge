from pydantic import BaseModel, Field
from typing import List, Optional

class LineItem(BaseModel):
    description: str = Field(..., description="Description of the line item")
    quantity: float = Field(..., description="Quantity of the item")
    unit_price: float = Field(..., description="Unit price of the item")
    total: float = Field(..., description="Total price for the line item")

class ExtractionSchema(BaseModel):
    document_type: str = Field(..., description="Type of the document, e.g., Invoice, Receipt, Contract")
    date_issued: Optional[str] = Field(None, description="ISO formatted date when the document was issued")
    issuer: str = Field(..., description="Entity that issued the document")
    recipient: str = Field(..., description="Entity receiving the document")
    part_numbers: List[str] = Field(default_factory=list, description="Any part numbers found in the document")
    total_amount: float = Field(..., description="Total monetary amount. If none, use 0.0")
    currency: str = Field(..., description="3-letter ISO currency code, e.g., USD")
    line_items: List[LineItem] = Field(default_factory=list, description="Individual line items")
    summary: str = Field(..., description="A short summary of the document contents")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1 indicating how certain you are about the extraction")
    extraction_notes: Optional[str] = Field(None, description="Any notes or caveats regarding the extraction process")
