# PaperBridge Backend

PaperBridge is a production-ready AI document intelligence backend.

## Stack
- FastAPI (async)
- Supabase Postgres (with pgvector)
- Supabase Storage (private bucket)
- Instructor & gpt-4o-mini
- PyMuPDF
- text-embedding-3-small
- Docker & uv

## Setup

1. Copy `.env` file containing your Supabase and OpenAI credentials.
2. Run database migrations in your Supabase project using `app/db/migrations.sql`.
3. Stand up the server using Docker:
   ```bash
   docker compose up --build
   ```

## Architecture

- **PDF Parsing**: Uses PyMuPDF. If a page has < 100 characters, it falls back to OpenAI Vision to read textual content from raw pixel renderings. Images are stored in the private Supabase Storage bucket.
- **Extraction**: Strict JSON extraction driven by Pydantic models through `Instructor`. Deterministic rules are run post-extraction to calculate confidence Flags (PASSED, FLAGGED, FAILED).
- **RAG + Embeddings**: Text is chunked with 800 tokens using `tiktoken` with optimal overlap. Embeddings are pushed to `pgvector` inside Supabase. The `ask` endpoint returns context-bound answers with deterministic citations mapping to page numbers and exact chunks.
- **Async Workflow**: Time-consuming actions like extraction and embedding trigger database jobs. Clients can poll their progress endpoints.
- **Storage**: Supabase's Python SDK with the Service Role key pushes all PDFs into a secure bucket safely behind the application tier.
