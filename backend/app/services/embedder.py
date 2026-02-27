from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings
from app.core.logging import logger

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    logger.info(f"Generating embeddings for {len(texts)} chunks...")
    try:
        response = await openai_client.embeddings.create(
            input=texts,
            model=settings.openai_embed_model,
        )
        return [data.embedding for data in response.data]
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise
