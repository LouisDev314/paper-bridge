from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.logging import logger

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
    description="Production-ready AI internal tool for document intelligence.",
    version="1.0.0",
    lifespan=lifespan
)

# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(extract_router)
app.include_router(embed_router)
app.include_router(ask_router)
app.include_router(review_router)
app.include_router(export_router)
