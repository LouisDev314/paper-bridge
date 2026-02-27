from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
ENV_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required
    openai_api_key: str
    database_url: str

    # Optional
    app_name: str = "PaperBridge"
    debug: bool = False

    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    chunk_size_tokens: int = 300
    chunk_overlap_tokens: int = 50
    rag_top_k: int = 5

    max_extraction_retries: int = 3

settings = Settings()
