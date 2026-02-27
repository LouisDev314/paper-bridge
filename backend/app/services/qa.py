from openai import AsyncOpenAI
from app.core.config import settings
from app.core.logging import logger
from app.schemas.qa import AskResponse, Citation
from typing import List
from app.db.models import Embedding

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

async def answer_question(question: str, chunks: List[Embedding]) -> AskResponse:
    logger.info("Generating answer with GPT-4o-mini...")
    
    context_text = "\n\n---\n\n".join(
        [f"Chunk ID: {c.chunk_id}\nPage: {c.page_start}-{c.page_end}\nContent:\n{c.content}" for c in chunks]
    )
    
    messages = [
        {
            "role": "system", 
            "content": (
                "You are an assistant answering questions based solely on the provided context. "
                "Do NOT hallucinate or use outside knowledge. If the answer is not in the context, say 'I cannot answer this based on the provided document'. "
                "You MUST cite the page numbers in your answer when referencing facts."
            )
        },
        {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {question}"}
    ]
    
    response = await openai_client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        max_tokens=1000
    )
    
    answer = response.choices[0].message.content or ""
    
    citations = [
        Citation(
            chunk_id=c.chunk_id,
            page_start=c.page_start,
            page_end=c.page_end,
            text=c.content
        ) for c in chunks
    ]
    
    return AskResponse(answer=answer, citations=citations)
