from supabase import create_client, Client
from app.core.config import settings
from app.core.logging import logger

class SupabaseStorage:
    def __init__(self):
        self.supabase: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
        self.bucket = settings.supabase_storage_bucket

    def upload_file(self, file_bytes: bytes, destination_key: str, content_type: str = "application/pdf") -> str:
        """Upload a file to Supabase Storage."""
        logger.info(f"Uploading file to {self.bucket}/{destination_key}")
        try:
            self.supabase.storage.from_(self.bucket).upload(
                path=destination_key,
                file=file_bytes,
                file_options={"content-type": content_type}
            )
            return destination_key
        except Exception as e:
            logger.error(f"Failed to upload file to {destination_key}: {e}")
            raise e

    def download_file(self, file_key: str) -> bytes:
        """Download file from Supabase Storage."""
        logger.info(f"Downloading file {file_key}")
        try:
            return self.supabase.storage.from_(self.bucket).download(file_key)
        except Exception as e:
            logger.error(f"Failed to download file {file_key}: {e}")
            raise e

storage_service = SupabaseStorage()
