import re
from dataclasses import dataclass

from app.core.config import settings
from app.utils.tokens import count_tokens

GLOSSARY_LINE_RE = re.compile(r"^(?:[A-Z][A-Z0-9/().-]{1,15})\s+.+")
HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*)\s+[A-Z].+$")
BULLET_RE = re.compile(r"^[\u2022\-*]\s+")


@dataclass(frozen=True)
class TextChunk:
    content: str
    approx_tokens: int


def _clean_line(line: str) -> str:
    line = line.replace("\u00a0", " ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _split_into_blocks(text: str) -> list[str]:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []

    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        is_heading = bool(HEADING_RE.match(line))
        is_glossary = bool(GLOSSARY_LINE_RE.match(line))
        is_bullet = bool(BULLET_RE.match(line))

        if is_heading:
            if current:
                blocks.append(current)
                current = []
            blocks.append([line])
            continue

        if is_glossary or is_bullet:
            if current and not GLOSSARY_LINE_RE.match(current[-1]) and not BULLET_RE.match(current[-1]):
                blocks.append(current)
                current = []
            current.append(line)
            continue

        if current and (GLOSSARY_LINE_RE.match(current[-1]) or BULLET_RE.match(current[-1])):
            blocks.append(current)
            current = []

        current.append(line)

    if current:
        blocks.append(current)

    return ["\n".join(block) for block in blocks if block]


def _split_large_block(block: str, chunk_size: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", block)
    out: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_tokens = count_tokens(sentence)

        if sentence_tokens > chunk_size:
            words = sentence.split()
            buf: list[str] = []
            buf_tokens = 0
            for word in words:
                word_tokens = count_tokens(word)
                if buf and buf_tokens + word_tokens > chunk_size:
                    out.append(" ".join(buf))
                    buf = [word]
                    buf_tokens = word_tokens
                else:
                    buf.append(word)
                    buf_tokens += word_tokens
            if buf:
                if current:
                    out.append(" ".join(current))
                    current = []
                    current_tokens = 0
                out.append(" ".join(buf))
            continue

        if current and current_tokens + sentence_tokens > chunk_size:
            out.append(" ".join(current))
            current = [sentence]
            current_tokens = sentence_tokens
        else:
            current.append(sentence)
            current_tokens += sentence_tokens

    if current:
        out.append(" ".join(current))

    return [segment for segment in out if segment.strip()]


def chunk_text(
    text: str,
    chunk_size: int = settings.chunk_size_tokens,
    chunk_overlap: int = settings.chunk_overlap_tokens,
) -> list[TextChunk]:
    """
    Chunk by semantic blocks first (headings, glossary lines, bullets), then tokenize.
    This avoids splitting definition entries across chunks.
    """
    blocks = _split_into_blocks(text)
    if not blocks:
        return []

    chunks: list[TextChunk] = []
    current_blocks: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_blocks, current_tokens
        if not current_blocks:
            return

        content = "\n".join(current_blocks).strip()
        if content:
            chunks.append(TextChunk(content=content, approx_tokens=current_tokens))

        overlap_blocks: list[str] = []
        overlap_tokens = 0
        for block in reversed(current_blocks):
            block_tokens = count_tokens(block)
            if overlap_tokens + block_tokens > chunk_overlap:
                break
            overlap_blocks.insert(0, block)
            overlap_tokens += block_tokens

        current_blocks = overlap_blocks
        current_tokens = overlap_tokens

    for block in blocks:
        block_tokens = count_tokens(block)

        if block_tokens > chunk_size:
            flush()
            for segment in _split_large_block(block, chunk_size):
                seg_tokens = count_tokens(segment)
                chunks.append(TextChunk(content=segment, approx_tokens=seg_tokens))
            continue

        if current_blocks and current_tokens + block_tokens > chunk_size:
            flush()

        current_blocks.append(block)
        current_tokens += block_tokens

    if current_blocks:
        content = "\n".join(current_blocks).strip()
        if content:
            chunks.append(TextChunk(content=content, approx_tokens=current_tokens))

    return chunks
