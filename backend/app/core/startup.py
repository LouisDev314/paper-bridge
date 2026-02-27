# backend/app/core/startup.py
from pydantic import ValidationError
from .config import Settings

def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        # Pretty, actionable error output
        raise RuntimeError(
            "❌ Invalid or missing environment variables. "
            "Check backend/.env and required keys.\n\n"
            f"{e}"
        ) from e
