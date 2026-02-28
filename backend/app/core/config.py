from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    debug: bool = False

    api_env: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    openai_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_embed_dims: int = 1536

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "paperbridge-documents"

    database_url: str = ""

    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    max_upload_mb: int = Field(default=25, ge=1, le=100)
    max_pages: int = Field(default=200, ge=1, le=1000)

    chunk_size_tokens: int = Field(default=800, ge=100, le=4000)
    chunk_overlap_tokens: int = Field(default=120, ge=0, le=1000)
    rag_top_k: int = Field(default=6, ge=1, le=25)
    embedding_batch_size: int = Field(default=100, ge=1, le=500)

    llm_retries: int = Field(default=2, ge=0, le=10)
    llm_timeout_s: int = Field(default=45, ge=5, le=180)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
