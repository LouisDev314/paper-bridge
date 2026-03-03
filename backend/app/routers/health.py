from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.api_route("/health", methods=["GET", "HEAD"], summary="Health check")
async def health_check():
    return {"status": "ok"}