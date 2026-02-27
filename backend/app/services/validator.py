from datetime import datetime
from app.schemas.extraction import ExtractionSchema

def validate_extraction(data: ExtractionSchema) -> str:
    """
    Returns PASSED, FLAGGED, or FAILED based on deterministic rules.
    """
    if not data.document_type:
        return "FAILED"
    
    if len(data.summary) < 10:
        return "FAILED"
        
    if data.date_issued:
        try:
            # Basic ISO format check
            datetime.fromisoformat(data.date_issued.replace("Z", "+00:00"))
        except ValueError:
            return "FAILED"

    if data.total_amount < 0:
        return "FAILED"
        
    if len(data.currency) != 3 or not data.currency.isalpha() or not data.currency.isupper():
        return "FAILED"
        
    if data.confidence < 0.6:
        return "FLAGGED"
        
    return "PASSED"
