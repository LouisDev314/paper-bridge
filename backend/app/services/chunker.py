from app.core.config import settings
from app.utils.tokens import count_tokens

def chunk_text(text: str, chunk_size: int = settings.chunk_size_tokens, chunk_overlap: int = settings.chunk_overlap_tokens) -> list[str]:
    """
    Chunks text by word boundaries according to configured token limits.
    """
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        word_len = count_tokens(word)
        if current_length + word_len > chunk_size:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            
            # Keep overlap
            overlap_words = []
            overlap_len = 0
            for w in reversed(current_chunk):
                wl = count_tokens(w)
                if overlap_len + wl <= chunk_overlap:
                    overlap_words.insert(0, w)
                    overlap_len += wl
                else:
                    break
                    
            current_chunk = overlap_words + [word]
            current_length = overlap_len + word_len
        else:
            current_chunk.append(word)
            current_length += word_len
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks
