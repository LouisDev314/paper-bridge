from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.startup import load_settings
from .routers import health

def create_app() -> FastAPI:
    _settings = load_settings()  # validates immediately
    return FastAPI(title=_settings.app_name)

app = create_app()

# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def initFn():
    return {"status": "ok"}

app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
