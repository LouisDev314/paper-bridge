import math

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_request_id, logger

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
async def generate_embeddings(texts: list[str], request_id: str | None = None) -> list[list[float]]:
    req_id = request_id or get_request_id()
    logger.info(
        "embedding_request request_id=%s chunks=%s embedding_model=%s",
        req_id,
        len(texts),
        settings.openai_embed_model,
    )
    try:
        response = await openai_client.embeddings.create(
            input=texts,
            model=settings.openai_embed_model,
        )
        vectors: list[list[float]] = []
        for data in response.data:
            emb = data.embedding
            if len(emb) != settings.openai_embed_dims:
                raise ValueError(
                    f"Embedding dimension mismatch. expected={settings.openai_embed_dims} got={len(emb)}"
                )
            norm = math.sqrt(sum(v * v for v in emb))
            if norm == 0:
                vectors.append(emb)
            else:
                vectors.append([v / norm for v in emb])
        return vectors
    except Exception as exc:
        logger.error("embedding_generation_failed request_id=%s error=%s", req_id, exc)
        raise
