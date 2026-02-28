from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger

openai_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    timeout=settings.llm_timeout_s,
    max_retries=settings.llm_retries,
)

@retry(
    stop=stop_after_attempt(settings.llm_retries + 1),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    logger.info("Generating embeddings for %s chunks", len(texts))
    try:
        response = await openai_client.embeddings.create(
            input=texts,
            model=settings.openai_embed_model,
        )
        return [data.embedding for data in response.data]
    except Exception as exc:
        logger.error("embedding_generation_failed error=%s", exc)
        raise
