import instructor
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings
from app.core.logging import logger
from app.schemas.extraction import ExtractionSchema

# Setup instructor with async client
client = instructor.from_openai(
    AsyncOpenAI(api_key=settings.openai_api_key),
    mode=instructor.Mode.TOOLS
)

@retry(
    stop=stop_after_attempt(settings.llm_retries + 1),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def extract_document_features(text: str) -> ExtractionSchema:
    logger.info("Extracting data via Instructor...")
    try:
        extraction = await client.chat.completions.create(
            model=settings.chat_model,
            response_model=ExtractionSchema,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": "You are a highly capable document extraction system. Extracted information must exactly match the document. Do not hallucinate."},
                {"role": "user", "content": f"Extract information from the following document text:\n\n{text}"}
            ]
        )
        return extraction
    except Exception as e:
        logger.error(f"Instructor extraction failed: {e}")
        raise
