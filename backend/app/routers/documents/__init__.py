from fastapi import APIRouter

router = APIRouter()

# List documents
@router.get("/", tags=["list documents"])
async def list_documents():
    return [{"username": "Rick"}, {"username": "Morty"}]

# Create ingest job
@router.post("/", tags=["create ingest job"])
async def create_ingest_job():
    return {"username": "fakecurrentuser"}

# Get document details
@router.post("/", tags=["get document details"])
async def get_document_details():
    return {"username": "fakecurrentuser"}
