# How PaperBridge Backend Works

## 1) End-to-end workflow

1. `POST /documents`
   - Uploads a PDF, validates type/size, stores it in Supabase Storage.
   - Parses pages with PyMuPDF; low-text pages use Vision fallback.
   - Persists `documents` and `document_pages`.
2. `POST /documents/{document_id}/extract`
   - Queues extraction job in `jobs`.
   - Background task concatenates page text, calls Instructor/OpenAI, validates output, stores in `extractions`.
   - Job status becomes `done`, `needs_review`, or `failed`.
3. `POST /documents/{document_id}/embed`
   - Queues embedding job in `jobs`.
   - Background task chunks page text, generates embeddings in batches, writes to `embeddings`.
   - Existing embeddings for that document are deleted first (idempotent rebuild).
4. `POST /ask`
   - Accepts `question` + optional `doc_ids` list.
   - Embeds question, retrieves nearest chunks (optionally scoped to provided documents), calls QA model.
   - Returns answer + citations (`document_id`, page range, `chunk_id`, chunk text, similarity score).
5. `POST /extractions/{extraction_id}/review`
   - Saves manual edits into `review_edits` and updates `extractions.data`.
6. Export
   - `GET /documents/{document_id}/export.json`
   - `GET /documents/{document_id}/export.csv`

## 2) Module map

- Entrypoint
  - `backend/app/main.py`
  - App init, CORS, request-id/latency middleware, exception handlers, router registration.
- Routers
  - `backend/app/routers/documents.py`: upload/list/get docs.
  - `backend/app/routers/extract.py`: extraction job trigger + worker.
  - `backend/app/routers/embed.py`: embedding job trigger + worker.
  - `backend/app/routers/ask.py`: multi-document QA.
  - `backend/app/routers/jobs.py`: poll job status.
  - `backend/app/routers/review.py`: submit reviewed extraction.
  - `backend/app/routers/export.py`: JSON/CSV export.
- Services
  - `backend/app/services/pdf_parser.py`: PDF page parsing + Vision fallback + page image upload.
  - `backend/app/services/chunker.py`: token-aware chunking.
  - `backend/app/services/embedder.py`: embeddings API calls with retry/timeout.
  - `backend/app/services/retriever.py`: vector retrieval and doc filtering.
  - `backend/app/services/qa.py`: grounded answer generation from retrieved chunks.
  - `backend/app/services/extractor.py`: structured extraction via Instructor.
  - `backend/app/services/validator.py`: deterministic extraction quality checks.
  - `backend/app/services/supabase_storage.py`: Supabase bucket upload/download wrapper.
- DB
  - `backend/app/db/models.py`: SQLAlchemy models.
  - `backend/app/db/migrations.sql`: table/index creation.
- Schemas
  - `backend/app/schemas/*.py`: request/response contracts.

## 3) Key functions (annotated)

### `upload_document(...)` (`routers/documents.py`)
- What it does:
  - Validates upload, sanitizes filename, enforces size limit, uploads to storage, parses pages, persists metadata.
- Inputs:
  - `UploadFile`, DB session.
- Outputs:
  - `DocumentResponse`.
- Failure modes:
  - 400 invalid file type/pages limit exceeded.
  - 413 file too large.
  - 500 storage/parser failure.
- Why this way:
  - Keeps upload synchronous for simple UX while protecting API with strict limits and rollback.

### `parse_pdf(...)` (`services/pdf_parser.py`)
- What it does:
  - Offloads CPU-heavy PDF parsing to threadpool and runs Vision fallback for low-text pages.
- Inputs:
  - PDF bytes, `document_id`.
- Outputs:
  - `(total_pages, pages_data)` list of page metadata.
- Failure modes:
  - Raises `ValueError` for over-page-limit PDFs.
  - Upstream OpenAI/storage failures.
- Why this way:
  - Avoids blocking FastAPI event loop while retaining OCR fallback quality.

### `run_extraction_job(...)` (`routers/extract.py`)
- What it does:
  - Background extraction job lifecycle from `queued` to terminal state.
- Inputs:
  - `job_id`.
- Outputs:
  - Persists `Extraction` + updates `Job`.
- Failure modes:
  - Empty text, model call failure, validation failure path.
- Why this way:
  - Keeps expensive extraction asynchronous and observable via `/jobs/{id}`.

### `run_embed_job(...)` (`routers/embed.py`)
- What it does:
  - Builds chunks, embeds in batches, writes vectors.
- Inputs:
  - `job_id`.
- Outputs:
  - `embeddings` rows + job status.
- Failure modes:
  - No parsed text/pages, embedding API errors, DB failures.
- Why this way:
  - Batch processing + idempotent rebuild prevents duplicate vectors on retries/re-runs.

### `retrieve_chunks(...)` (`services/retriever.py`)
- What it does:
  - pgvector cosine search with optional `document_id` scope.
- Inputs:
  - question embedding, optional doc IDs, `top_k`.
- Outputs:
  - `RetrievedChunk[]` (chunk + distance).
- Failure modes:
  - DB/extension/index misconfiguration.
- Why this way:
  - Single query supports both global and multi-document retrieval.

### `answer_question(...)` (`services/qa.py`)
- What it does:
  - Builds grounded context and asks model to answer only from evidence.
- Inputs:
  - question, retrieved chunks.
- Outputs:
  - `AskResponse` with citations.
- Failure modes:
  - Upstream model API failure.
- Why this way:
  - Keeps citations deterministic from retrieved chunks, independent of LLM formatting.

## 4) Data model and lifecycle

- Document lifecycle (effective):
  - Uploaded (`documents` + `document_pages`)
  - Extract queued/running/completed (`jobs`, `extractions`)
  - Embed queued/running/completed (`jobs`, `embeddings`)
- Integrity notes:
  - FKs + `ON DELETE CASCADE` keep related rows consistent.
  - Embedding job deletes prior vectors for same doc before rebuilding.

## 5) Production caveats (current architecture)

- Background tasks are in-process FastAPI tasks, not a distributed worker queue.
  - If process restarts mid-job, queued/running work may be interrupted.
- AuthN/AuthZ is still not implemented.
  - Suitable for trusted internal network only.
- Rate limiting is not implemented yet.
  - Should be added at gateway/reverse proxy layer for abuse protection.
