from typing import List

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import logger
from app.schemas.qa import AskResponse, Citation
from app.services.retriever import RetrievedChunk

openai_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    timeout=settings.llm_timeout_s,
    max_retries=settings.llm_retries,
)

async def answer_question(question: str, chunks: List[RetrievedChunk]) -> AskResponse:
    logger.info("Generating answer for question with %s evidence chunks", len(chunks))

    context_text = "\n\n=== EVIDENCE ===\n\n".join(
        [
            (
                f"Document ID: {chunk.embedding.document_id}\n"
                f"Pages: {chunk.embedding.page_start}-{chunk.embedding.page_end}\n"
                f"Chunk ID: {chunk.embedding.chunk_id}\n"
                f"Content:\n{chunk.embedding.content}"
            )
            for chunk in chunks
        ]
    )

    messages = [
        {
            "role": "system", 
            "content": (
                "You are an assistant answering questions based solely on the provided context. "
                "Do not hallucinate or use outside knowledge. "
                "If the answer is not in the context, say 'I cannot answer this based on the provided documents'. "
                "When referencing facts, include citations with BOTH Document ID and page range."
            )
        },
        {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {question}"}
    ]
    
    response = await openai_client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0,
        max_tokens=1000,
    )
    
    answer = response.choices[0].message.content or ""
    
    citations = [
        Citation(
            chunk_id=chunk.embedding.chunk_id,
            document_id=chunk.embedding.document_id,
            page_start=chunk.embedding.page_start,
            page_end=chunk.embedding.page_end,
            text=chunk.embedding.content,
            similarity_score=(1 - chunk.distance) if chunk.distance is not None else None,
        )
        for chunk in chunks
    ]
    
    return AskResponse(answer=answer, citations=citations)
