import tiktoken
from app.core.config import settings

def count_tokens(text: str, model: str = None) -> int:
    """Return the number of tokens in a text using tiktoken."""
    model_to_use = model or settings.chat_model
    try:
        encoding = tiktoken.encoding_for_model(model_to_use)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))
