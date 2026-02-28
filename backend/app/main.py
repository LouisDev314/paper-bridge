import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import logger
from app.schemas.api import ErrorResponse

from app.routers import health_router, documents_router, jobs_router, extract_router, embed_router, ask_router, review_router, export_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up PaperBridge backend...")
    yield
    # Shutdown
    logger.info("Shutting down PaperBridge backend...")

app = FastAPI(
    title="PaperBridge API",
    description=(
        "Backend for document ingestion, extraction, embeddings, and multi-document QA with citations."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "health", "description": "Service health and readiness."},
        {"name": "documents", "description": "Document upload and retrieval."},
        {"name": "extract", "description": "Extraction jobs and structured output."},
        {"name": "embed", "description": "Embedding jobs for vector retrieval."},
        {"name": "ask", "description": "Multi-document question answering with citations."},
        {"name": "jobs", "description": "Job status polling."},
        {"name": "review", "description": "Review and corrections for extraction results."},
        {"name": "export", "description": "Export extraction outputs."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "request_failed request_id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    payload = ErrorResponse(
        error={
            "code": f"http_{exc.status_code}",
            "message": str(exc.detail),
            "request_id": getattr(request.state, "request_id", None),
        }
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    payload = ErrorResponse(
        error={
            "code": "validation_error",
            "message": "Request payload validation failed.",
            "request_id": getattr(request.state, "request_id", None),
        }
    ).model_dump()
    logger.warning("validation_error request_id=%s details=%s", payload["error"]["request_id"], exc.errors())
    return JSONResponse(status_code=422, content=payload)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled_error request_id=%s", request_id)
    payload = ErrorResponse(
        error={
            "code": "internal_server_error",
            "message": "An unexpected error occurred.",
            "request_id": request_id,
        }
    ).model_dump()
    return JSONResponse(status_code=500, content=payload)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(extract_router)
app.include_router(embed_router)
app.include_router(ask_router)
app.include_router(review_router)
app.include_router(export_router)
