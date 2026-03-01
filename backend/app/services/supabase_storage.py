from typing import Optional

from supabase import create_client, Client

from app.core.config import settings
from app.core.logging import logger

class SupabaseStorage:
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.bucket = settings.supabase_storage_bucket

    def _get_client(self) -> Client:
        if self.supabase is not None:
            return self.supabase
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase credentials are not configured.")
        self.supabase = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        return self.supabase

    def upload_file(self, file_bytes: bytes, destination_key: str, content_type: str = "application/pdf") -> str:
        """Upload a file to Supabase Storage."""
        logger.info("Uploading file to %s/%s", self.bucket, destination_key)
        try:
            self._get_client().storage.from_(self.bucket).upload(
                path=destination_key,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "false"},
            )
            return destination_key
        except Exception as exc:
            logger.error("failed_to_upload file_key=%s error=%s", destination_key, exc)
            raise

    def download_file(self, file_key: str) -> bytes:
        """Download file from Supabase Storage."""
        logger.info("Downloading file %s", file_key)
        try:
            return self._get_client().storage.from_(self.bucket).download(file_key)
        except Exception as exc:
            logger.error("failed_to_download file_key=%s error=%s", file_key, exc)
            raise

    def delete_files(self, file_keys: list[str]) -> None:
        if not file_keys:
            return
        logger.info("Deleting %s files from %s", len(file_keys), self.bucket)
        try:
            self._get_client().storage.from_(self.bucket).remove(file_keys)
        except Exception as exc:
            logger.error("failed_to_delete file_keys=%s error=%s", file_keys, exc)
            raise

storage_service = SupabaseStorage()
