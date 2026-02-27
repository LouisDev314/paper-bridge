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
    
    max_upload_mb: int = 25
    max_pages: int = 200
    
    chunk_size_tokens: int = 800
    chunk_overlap_tokens: int = 120
    rag_top_k: int = 6
    
    llm_retries: int = 2
    llm_timeout_s: int = 45

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
