import base64
from typing import Any

import fitz  # PyMuPDF
from fastapi.concurrency import run_in_threadpool
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_request_id, logger
from app.services.supabase_storage import storage_service

LOW_TEXT_THRESHOLD = 100

openai_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    timeout=settings.llm_timeout_s,
    max_retries=settings.llm_retries,
)


def _extract_pages_sync(file_bytes: bytes) -> tuple[int, list[dict[str, Any]]]:
    """
    Run CPU-heavy PDF parsing in a worker thread so the event loop stays responsive.
    """
    doc = fitz.open("pdf", file_bytes)
    total_pages = len(doc)
    pages_data: list[dict[str, Any]] = []

    for i, page in enumerate(doc):
        page_number = i + 1
        text = page.get_text()
        image_bytes = None

        if len(text.strip()) < LOW_TEXT_THRESHOLD:
            pix = page.get_pixmap(dpi=150)
            image_bytes = pix.tobytes("png")

        pages_data.append(
            {
                "page_number": page_number,
                "text": text,
                "text_quality_score": 1.0,
                "page_image_key": None,
                "image_bytes": image_bytes,
            }
        )

    doc.close()
    return total_pages, pages_data

async def _extract_text_via_vision(image_bytes: bytes) -> str:
    """Fallback: extract text from an image using gpt-4o-mini Vision."""
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    response = await openai_client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all the text from this document image. Return ONLY the text, nothing else."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ],
        max_tokens=2000,
    )
    return response.choices[0].message.content or ""

async def parse_pdf(file_bytes: bytes, document_id: str):
    """
    Parse PDF into pages. Returns list of dictionaries containing page data.
    dict: page_number, text, text_quality_score, page_image_key
    """
    request_id = get_request_id()
    logger.info("parse_pdf_start request_id=%s document_id=%s", request_id, document_id)
    total_pages, pages_data = await run_in_threadpool(_extract_pages_sync, file_bytes)

    if total_pages > settings.max_pages:
        raise ValueError(f"PDF has {total_pages} pages, exceeds max of {settings.max_pages}.")

    for page_data in pages_data:
        image_bytes = page_data.pop("image_bytes", None)
        if image_bytes is None:
            continue

        page_number = page_data["page_number"]
        logger.info(
            "vision_fallback request_id=%s page=%s document_id=%s reason=low_text model=%s",
            request_id,
            page_number,
            document_id,
            settings.chat_model,
        )
        vision_text = await _extract_text_via_vision(image_bytes)
        if vision_text.strip():
            page_data["text"] = vision_text
        page_data["text_quality_score"] = 0.8
        page_image_key = f"{document_id}/pages/page_{page_number}.png"
        await run_in_threadpool(
            storage_service.upload_file,
            image_bytes,
            page_image_key,
            "image/png",
        )
        page_data["page_image_key"] = page_image_key

    logger.info("parse_pdf_complete request_id=%s document_id=%s total_pages=%s", request_id, document_id, total_pages)
    return total_pages, pages_data
