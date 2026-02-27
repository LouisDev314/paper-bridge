import fitz  # PyMuPDF
import base64
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.logging import logger
from app.services.supabase_storage import storage_service

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

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
    doc = fitz.open("pdf", file_bytes)
    total_pages = len(doc)
    pages_data = []

    for i, page in enumerate(doc):
        page_number = i + 1
        text = page.get_text()
        text_quality_score = 1.0
        page_image_key = None

        if len(text.strip()) < 100:
            logger.info(f"Page {page_number} of {document_id} has < 100 chars. Using Vision fallback.")
            # Render to image
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            
            # Extract text via vision
            vision_text = await _extract_text_via_vision(img_bytes)
            text = vision_text if vision_text else text
            text_quality_score = 0.8  # slightly lower confidence for vision
            
            # Store image in supabase
            page_image_key = f"{document_id}/pages/page_{page_number}.png"
            storage_service.upload_file(img_bytes, page_image_key, content_type="image/png")

        pages_data.append({
            "page_number": page_number,
            "text": text,
            "text_quality_score": text_quality_score,
            "page_image_key": page_image_key
        })
        
    return total_pages, pages_data
