# PaperBridge Backend Guide

This guide documents the PaperBridge backend as it exists in the codebase under `backend/app`. It is **derived directly from the FastAPI routes, Pydantic models, services, and database schema** and avoids any undocumented behavior.

---

## 1) Overview

### What the PaperBridge backend does

PaperBridge is a **document intelligence** backend. It:

- **Ingests PDFs** via `/documents`.
- **Parses and OCRs pages** into text (with a Vision fallback for low‑text pages).
- **Stores documents and pages** in Postgres and binary files in **Supabase Storage**.
- **Creates background jobs** to:
  - **Extract structured fields** (e.g., totals, currency, line items) with an LLM + `instructor`.
  - **Chunk and embed text** into pgvector embeddings for retrieval.
- **Supports retrieval‑augmented QA** over a single document with `/documents/{id}/ask`.
- **Supports human review and exports**:
  - Editing extracted JSON via `/extractions/{id}/review`.
  - Exporting the latest extraction as JSON or CSV via `/documents/{id}/export.(json|csv)`.

### High‑level pipeline

End‑to‑end, the main flow looks like this:

```text
          +-------------------+
          |  Client (tool/UI) |
          +---------+---------+
                    |
                    | 1) Upload PDF
                    v
         POST /documents  (router: documents)
                    |
                    | - Store binary in Supabase Storage
                    | - Parse PDF into pages (PyMuPDF + optional Vision fallback)
                    v
      Postgres: documents, document_pages

                    |
        +-----------+----------------------------+
        |                                        |
        | 2a) Trigger extraction                 | 2b) Trigger embeddings
        v                                        v
POST /documents/{document_id}/extract   POST /documents/{document_id}/embed
(router: extract)                       (router: embed)
        |                                        |
        | - Create Job row (task_type="extract") | - Create Job row (task_type="embed")
        | - Background task:                     | - Background task:
        |   * concatenate page text              |   * chunk text (token-based)
        |   * call LLM via instructor            |   * generate embeddings via OpenAI
        |   * validate extraction                |   * store chunks + vectors
        v                                        v
   Postgres: jobs, extractions             Postgres: jobs, embeddings

                    |
        3) Ask questions about a document
                    v
      POST /documents/{document_id}/ask  (router: ask)
                    |
                    | - embed question
                    | - retrieve top-k chunks via pgvector
                    | - call LLM to answer with citations
                    v
      AskResponse: { answer, citations[] }

                    |
        4) Human review and export
                    v
POST /extractions/{extraction_id}/review   GET /documents/{document_id}/export.json
(router: review)                           GET /documents/{document_id}/export.csv
      |                                     (router: export)
      v
Postgres: review_edits, extractions
```

Routers are wired in `app.main`:

- `health_router` → `/health`
- `documents_router` → `/documents...`
- `jobs_router` → `/jobs/{job_id}`
- `extract_router` → `/documents/{id}/extract`
- `embed_router` → `/documents/{id}/embed`
- `ask_router` → `/documents/{id}/ask`
- `review_router` → `/extractions/{id}/review`
- `export_router` → `/documents/{id}/export.*`

Each router relies on:

- **Database layer**: `app.db.database`, `app.db.models`
- **Service layer**: `app.services.*`
- **Schemas**: `app.schemas.*`
- **Config & logging**: `app.core.config`, `app.core.logging`

---

## 2) Project Layout

### Backend app directory tree

Derived from the actual files under `backend/app`:

```text
backend/app
├── main.py
├── core
│   ├── config.py
│   └── logging.py
├── routers
│   ├── __init__.py
│   ├── ask.py
│   ├── documents.py
│   ├── embed.py
│   ├── export.py
│   ├── extract.py
│   ├── health.py
│   ├── jobs.py
│   └── review.py
├── services
│   ├── chunker.py
│   ├── embedder.py
│   ├── extractor.py
│   ├── pdf_parser.py
│   ├── qa.py
│   ├── retriever.py
│   ├── supabase_storage.py
│   └── validator.py
├── schemas
│   ├── api.py
│   ├── extraction.py
│   ├── qa.py
│   └── review.py
├── db
│   ├── database.py
│   ├── migrations.sql
│   └── models.py
└── utils
    ├── ids.py
    └── tokens.py
```

### Responsibilities

- **`main.py`**
  - Defines the FastAPI app, lifespan, and CORS.
  - Includes all routers from `app.routers`.

- **`core/`**
  - `config.py`: Pydantic `Settings` class (`BaseSettings`) with all runtime configuration (API env/host/port, OpenAI, Supabase, database URL, limits, RAG parameters, retry/timeout settings). Loads from `.env`.
  - `logging.py`: Central logging setup (`setup_logging`) and root `logger` used across services and routers.

- **`routers/`**
  - `__init__.py`: Exports router objects:
    - `health_router`, `documents_router`, `jobs_router`, `extract_router`, `embed_router`, `ask_router`, `export_router`, `review_router`.
  - `health.py`: `/health` heartbeat endpoint.
  - `documents.py`: Upload, list, and fetch `Document` records; orchestrates Supabase storage and PDF parsing.
  - `jobs.py`: Fetch `Job` status by ID.
  - `extract.py`: Trigger extraction job for a document; background task writes to `extractions` table.
  - `embed.py`: Trigger embedding job for a document; background task writes to `embeddings` table.
  - `ask.py`: Question‑answering over a document using embeddings and OpenAI chat.
  - `review.py`: Persist human review edits of an extraction.
  - `export.py`: Export latest extraction for a document as JSON or CSV.

- **`services/`**
  - `qa.py`: LLM‑based QA over retrieved chunks; returns `AskResponse`.
  - `retriever.py`: Vector similarity retrieval over `embeddings` (pgvector cosine distance).
  - `embedder.py`: OpenAI embeddings client with retry/backoff.
  - `chunker.py`: Token‑aware chunking for document text using `tiktoken`.
  - `validator.py`: Deterministic validation of `ExtractionSchema` to label extractions as `PASSED`, `FLAGGED`, `FAILED`.
  - `extractor.py`: Uses `instructor` + OpenAI to produce structured `ExtractionSchema` from raw text, with retry policy.
  - `pdf_parser.py`: PDF parsing via PyMuPDF with Vision fallback for low‑text pages and Supabase image storage.
  - `supabase_storage.py`: Supabase Storage client abstraction for upload/download.

- **`schemas/`**
  - `api.py`: API response schemas:
    - `DocumentResponse`, `JobResponse`, `ExportResponse`.
  - `qa.py`: `AskRequest`, `Citation`, `AskResponse`.
  - `review.py`: `ReviewEditRequest`, `ReviewEditResponse`.
  - `extraction.py`: `ExtractionSchema` and nested `LineItem` describing structured extraction output.

- **`db/`**
  - `database.py`: Async SQLAlchemy engine + `AsyncSessionLocal`, `Base`, and `get_db()` dependency.
  - `models.py`: ORM models for `Document`, `Job`, `DocumentPage`, `Extraction`, `ReviewEdit`, `Embedding` (with `pgvector` column).
  - `migrations.sql`: SQL to set up pgvector extension, tables, and indexes consistent with the models.

- **`utils/`**
  - `tokens.py`: `count_tokens` using `tiktoken` with the configured chat model.
  - `ids.py`: `generate_id` helper for prefixed UUID strings (not currently used in routers).

---

## 3) App Lifecycle, Middleware, and CORS

### Lifespan context manager

Defined in `app.main`:

- `lifespan(app: FastAPI)` is an `@asynccontextmanager` with:
  - **Startup**: Logs `"Starting up PaperBridge backend..."`.
  - **Shutdown**: Logs `"Shutting down PaperBridge backend..."`.
- The lifespan is passed to `FastAPI(..., lifespan=lifespan)`.

The **logger** used here (`logger.info(...)`) is imported from `app.core.logging`, which:

- Configures root logging via `setup_logging(debug: bool = False)`.
- Sets level to `DEBUG` when `debug=True` and `INFO` otherwise.
- Uses a stream handler to `sys.stdout` with a standard timestamped format.
- Reduces verbosity of `uvicorn` and `sqlalchemy.engine` loggers.

### Middleware and CORS

In `app.main`:

- `app.add_middleware(CORSMiddleware, ...)` is configured as:
  - `allow_origins=["*"]`
  - `allow_credentials=True`
  - `allow_methods=["*"]`
  - `allow_headers=["*"]`

Implications for frontend development:

- **Any origin** (localhost ports, staging domains, etc.) can call the API without CORS issues.
- All HTTP methods and headers are allowed, and browser cookies/credentials are permitted.
- This is convenient for development but permissive for production; if you later tighten CORS, mirror this shape but restrict `allow_origins`.

---

## 4) Configuration & Environment Variables

### Settings loading

`app.core.config.Settings`:

- Inherits from `BaseSettings` (pydantic‑settings).
- `model_config`:
  - `env_file=".env"` (relative to the backend working directory).
  - `env_file_encoding="utf-8"`.
  - `extra="ignore"` (unknown env vars are ignored).
- An instance `settings = Settings()` is created at import time and is used throughout the codebase (OpenAI clients, Supabase client, database engine, chunking parameters, etc.).

Pydantic automatically maps environment variables to fields (e.g., `api_env` ⇔ `API_ENV`), which are also reflected in the `.env` file under `backend/.env`. **Do not commit real secrets; the current file should be treated as example values only.**

### Env vars actually used

The following fields are defined in `Settings` and used indirectly via `settings` in services and DB code. The env var names correspond to upper‑case versions in `.env`.

> Values below are **placeholders**; do not use any real keys/URLs in documentation.

| env var name                 | required?                         | default (from code)               | what it controls                                                                                   | example placeholder                                           | failure mode (from code usage)                                                                 |
|-----------------------------|-----------------------------------|-----------------------------------|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| `DEBUG`                     | no                                | `False`                           | Logging verbosity (`settings.debug` is used when building DB engine `echo` flag).                  | `false`                                                      | If unset, logs at INFO; if set incorrectly, pydantic may error on parsing.                     |
| `API_ENV`                   | no                                | `"local"`                         | Logical environment name (`settings.api_env`), currently not branched on in code.                 | `"local"` / `"production"`                                   | Only affects metadata/logging if you use it later.                                            |
| `API_HOST`                  | no                                | `"0.0.0.0"`                       | Intended host for API (`settings.api_host`), used for documentation / potential future wiring.    | `"0.0.0.0"`                                                  | If ignored in your run command, has no direct effect.                                         |
| `API_PORT`                  | no                                | `8000`                            | Intended port for API (`settings.api_port`).                                                       | `8000`                                                       | Same as `API_HOST`—not directly wired, but used for consistency.                              |
| `OPENAI_API_KEY`            | **yes (for LLM features)**        | `""` (empty string)               | API key for OpenAI (`settings.openai_api_key`), used in all OpenAI/Instructor clients.           | `sk-<your-openai-api-key>`                                   | OpenAI calls in `qa.py`, `embedder.py`, `extractor.py`, `pdf_parser.py` will fail (401/403).  |
| `CHAT_MODEL`                | no                                | `"gpt-4o-mini"`                   | Chat model name for OpenAI (`settings.chat_model`).                                               | `"gpt-4o-mini"`                                              | Wrong name → OpenAI model not found errors at runtime.                                        |
| `OPENAI_EMBED_MODEL`        | no                                | `"text-embedding-3-small"`        | Embedding model (`settings.openai_embed_model`) used in `embedder.generate_embeddings`.           | `"text-embedding-3-small"`                                   | Wrong/unsupported model → OpenAI embeddings errors.                                           |
| `OPENAI_EMBED_DIMS`         | **effectively required**          | `1536`                            | Dimensionality of embeddings (`settings.openai_embed_dims`), must match `Vector(1536)` in models. | `1536`                                                       | If changed without updating DB schema, pgvector insert/query will break.                      |
| `SUPABASE_URL`              | **yes (for storage)**             | `""`                              | Supabase instance URL (`settings.supabase_url`) for `SupabaseStorage`.                            | `https://<project>.supabase.co`                             | Supabase client in `supabase_storage.py` cannot reach backend; upload/download will fail.     |
| `SUPABASE_SERVICE_ROLE_KEY` | **yes (for storage)**             | `""`                              | Service role key (`settings.supabase_service_role_key`) used by Supabase client.                  | `sb-<your-service-role-key>`                                 | Upload/download calls will fail with authorization errors.                                    |
| `SUPABASE_STORAGE_BUCKET`   | no                                | `"paperbridge-documents"`         | Storage bucket name (`settings.supabase_storage_bucket`).                                         | `"paperbridge-documents"`                                    | Wrong bucket → uploads/downloads fail or go to unexpected bucket.                             |
| `DATABASE_URL`              | **yes (for DB)**                  | `""`                              | Async SQLAlchemy engine URL (`settings.database_url`).                                            | `postgresql+psycopg://user:pass@host:5432/dbname`           | `create_async_engine` in `db.database` will fail to connect; all DB‑backed endpoints break.   |
| `MAX_UPLOAD_MB`             | no (currently unused in routers)  | `25`                              | Intended max upload size in MB (`settings.max_upload_mb`).                                        | `25`                                                         | Currently not enforced at router; could be used in future for validation or reverse proxy.    |
| `MAX_PAGES`                 | no (currently unused in routers)  | `200`                             | Intended max allowed pages per document (`settings.max_pages`).                                   | `200`                                                        | Not enforced yet; if used later, excessive pages may error.                                   |
| `CHUNK_SIZE_TOKENS`         | no                                | `800`                             | Chunk size in tokens for `chunker.chunk_text`.                                                    | `800`                                                        | Too small → many chunks; too large → long context, more tokens.                               |
| `CHUNK_OVERLAP_TOKENS`      | no                                | `120`                             | Overlap between chunks in tokens.                                                                 | `120`                                                        | Too small → less context continuity; too large → more tokens.                                 |
| `RAG_TOP_K`                 | no                                | `6`                               | Default top‑k for retrieval (`settings.rag_top_k`) used in `retriever.retrieve_chunks`.           | `5` or `6`                                                   | Larger → more chunks and cost; smaller → less context and possibly weaker answers.            |
| `LLM_RETRIES`               | no                                | `2`                               | Number of additional LLM retries (`settings.llm_retries`) in `extractor`.                         | `2`                                                          | Too low → less resilience; too high → more latency if OpenAI is flaky.                        |
| `LLM_TIMEOUT_S`             | no (not directly used in code)    | `45`                              | Intended max LLM call duration in seconds.                                                        | `45`                                                         | Not yet wired; safe to leave default.                                                         |

> Note: `embedder.generate_embeddings` currently hard‑codes 3 attempts via `tenacity`, while `extractor.extract_document_features` uses `settings.llm_retries + 1`. This is visible in the service code.

---

## 5) How to Run the Backend

All commands below assume your working directory is `backend/` on macOS.

### 5.1 Local run with `uv` and `uvicorn`

1. **Install `uv`** (if not already installed):

   ```bash
   pip install uv
   ```

2. **Install dependencies into a `.venv` managed by `uv`:**

   ```bash
   cd backend
   uv sync
   ```

   This uses `pyproject.toml` and `uv.lock` and creates `.venv` in the backend folder (matching the Dockerfile behavior).

3. **Run the FastAPI app via `uvicorn` using `uv`:**

   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Base URLs and docs:**

   - Base URL: `http://localhost:8000`
   - Swagger UI: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`

Ensure your `.env` is present in `backend/` and contains **redacted / non‑production** values for:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `DATABASE_URL`

### 5.2 Docker and docker‑compose

The backend includes:

- `backend/Dockerfile`
- `backend/docker-compose.yml`

**Dockerfile** highlights:

- Base: `python:3.12-slim`.
- Installs `uv`.
- Sets `WORKDIR /app`.
- Copies `pyproject.toml` and `uv.lock`, then runs:
  - `ENV UV_PROJECT_ENVIRONMENT=/app/.venv`
  - `uv sync --frozen --no-cache` (installs into `/app/.venv` inside the image).
- Copies the rest of the backend source.
- Exposes port `8000`.
- CMD:

  ```text
  ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

**docker-compose.yml**:

- Service `backend`:
  - `build: .`
  - `ports: ["8000:8000"]`
  - `env_file: [".env"]`

**Run with docker‑compose:**

```bash
cd backend
docker compose up --build
```

This will build the image using the Dockerfile and start the backend on `http://localhost:8000`.

**Run with plain Docker:**

```bash
cd backend
docker build -t paperbridge-backend .
docker run --env-file .env -p 8000:8000 paperbridge-backend
```

#### Docker gotchas (derived from Dockerfile)

- The virtual environment is created under `/app/.venv` during the **image build**. If you later mount a host volume over `/app` or `/app/.venv`, you can hide that environment and cause `uv` or Python to fail. Avoid bind‑mounting over the entire `/app` directory unless you intentionally rebuild or re‑install dependencies in the container.

### 5.3 JetBrains IDE: “Unresolved reference app” fix

In PyCharm/IntelliJ:

- Mark `backend/` as a **Sources Root** (right‑click `backend` → “Mark Directory As” → “Sources Root”).
- Use the Python interpreter from `backend/.venv` (created by `uv sync`):
  - Preferences → Project → Python Interpreter → add existing interpreter → point to `.venv/bin/python`.

This ensures imports like `from app.routers import ...` resolve correctly.

---

## 6) API Reference (Router by Router)

This section lists only endpoints that exist in the code.

### 6.1 Health router (`routers/health.py`)

- **Router definition**:
  - `router = APIRouter(tags=["health"])`
- **Endpoints**:
  - **GET `/health`**
    - **Purpose**: Basic liveness check.
    - **Request**:
      - No body.
      - No path or query parameters.
    - **Response**:
      - Status: `200 OK`
      - Body:

        ```json
        {
          "status": "ok"
        }
        ```

### 6.2 Documents router (`routers/documents.py`)

- **Router definition**:
  - `router = APIRouter(tags=["documents"])`
- **Dependencies**:
  - `db: AsyncSession = Depends(get_db)` from `app.db.database`.
  - `Document`, `DocumentPage` ORM models.
  - `DocumentResponse` Pydantic model.
  - `storage_service` (Supabase).
  - `parse_pdf` service.

#### POST `/documents`

- **Purpose**: Upload a PDF document, store it in Supabase, parse pages, and persist to DB.
- **Request**:
  - Method: `POST`
  - Path: `/documents`
  - Content type: `multipart/form-data`
  - Body fields:
    - `file`: PDF file (`UploadFile = File(...)`).
- **Behavior**:
  - Rejects non‑PDF filenames:
    - If `file.filename` does not end with `.pdf` → raises `HTTPException(400, "Only PDF files are supported.")`.
  - Reads entire file into memory (`file.read()`).
  - Creates `Document` with empty `storage_key`, flushes to get `id`.
  - Uploads file bytes to Supabase Storage using key `{doc.id}/{file.filename}` and updates `doc.storage_key`.
  - Calls `parse_pdf(file_bytes, str(doc.id))`:
    - Returns `total_pages` and `pages_data` (list of dicts: `page_number`, `text`, `text_quality_score`, `page_image_key`).
    - For each page, inserts a `DocumentPage` row.
  - On parsing error:
    - Logs an error via `logger`.
    - Raises `HTTPException(500, "Failed to parse PDF document.")`.
  - Commits DB transaction and refreshes `doc`.
- **Response**:
  - Status: `200 OK`
  - Model: `DocumentResponse`:
    - `id: UUID`
    - `filename: str`
    - `total_pages: int`
    - `created_at: datetime`
  - Example:

    ```json
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "filename": "invoice.pdf",
      "total_pages": 3,
      "created_at": "2024-01-01T12:00:00Z"
    }
    ```

- **Errors**:
  - `400 Bad Request`:

    ```json
    {
      "detail": "Only PDF files are supported."
    }
    ```

  - `500 Internal Server Error`:

    ```json
    {
      "detail": "Failed to parse PDF document."
    }
    ```

  - `422 Unprocessable Entity`: Standard FastAPI validation error if the request is not valid `multipart/form-data`.

#### GET `/documents`

- **Purpose**: List all documents sorted by `created_at` descending.
- **Request**:
  - Method: `GET`
  - Path: `/documents`
  - No parameters.
- **Response**:
  - Status: `200 OK`
  - Body: `List[DocumentResponse]` (may be empty).

#### GET `/documents/{document_id}`

- **Purpose**: Fetch a single document’s metadata.
- **Request**:
  - Method: `GET`
  - Path: `/documents/{document_id}`
  - Path params:
    - `document_id: UUID`
- **Behavior**:
  - Looks up `Document` by primary key.
  - If not found → `HTTPException(404, "Document not found")`.
- **Response**:
  - Status: `200 OK`
  - Body: `DocumentResponse`.
- **Errors**:
  - `404 Not Found`:

    ```json
    {
      "detail": "Document not found"
    }
    ```

  - `422 Unprocessable Entity` if `document_id` is not a valid UUID string.

### 6.3 Jobs router (`routers/jobs.py`)

- **Router definition**:
  - `router = APIRouter(prefix="/jobs", tags=["jobs"])`
- **Dependencies**:
  - `db: AsyncSession = Depends(get_db)`.
  - `Job` ORM model.
  - `JobResponse` Pydantic model.

#### GET `/jobs/{job_id}`

- **Purpose**: Fetch the status and metadata of a background job.
- **Request**:
  - Method: `GET`
  - Path: `/jobs/{job_id}`
  - Path params:
    - `job_id: UUID`
- **Behavior**:
  - Fetches `Job` by primary key.
  - If not found → `HTTPException(404, "Job not found")`.
- **Response**:
  - Status: `200 OK`
  - Body: `JobResponse`:
    - `id, document_id, task_type, status, error_message, created_at, updated_at`.
- **Errors**:
  - `404 Not Found`:

    ```json
    {
      "detail": "Job not found"
    }
    ```

  - `422 Unprocessable Entity` for invalid UUID.

### 6.4 Extract router (`routers/extract.py`)

- **Router definition**:
  - `router = APIRouter(tags=["extract"])`
- **Dependencies**:
  - `db: AsyncSession = Depends(get_db)`.
  - `BackgroundTasks` for async job execution.
  - `Document`, `Job`, `DocumentPage`, `Extraction` models.
  - `AsyncSessionLocal` for background DB sessions.
  - `extract_document_features`, `validate_extraction`, `logger`.
  - `JobResponse` Pydantic model (response).

#### `run_extraction_job(job_id: UUID)` (background task)

- Not an endpoint, but critical to behavior.
- Looks up the `Job` by ID:
  - If missing: returns silently.
- Sets `job.status = "processing"` and commits.
- Gathers all `DocumentPage` rows for `job.document_id`, ordered by `page_number`.
- Concatenates text into a single string separated by double newlines.
- Calls `extract_document_features(full_text)`:
  - LLM + instructor call to produce `ExtractionSchema`.
- Validates via `validate_extraction`:
  - Returns status as `"PASSED"`, `"FLAGGED"`, or `"FAILED"`.
- Inserts an `Extraction` row with:
  - `document_id`, `data` (Pydantic `.model_dump()`), `status`.
- Sets `job.status`:
  - Default `"done"`, overridden to `"needs_review"` if `status == "FLAGGED"`.
- On any exception:
  - Logs error and sets `job.status = "failed"`, `job.error_message` to the exception message.

#### POST `/documents/{document_id}/extract`

- **Purpose**: Queue an extraction job for a document.
- **Request**:
  - Method: `POST`
  - Path: `/documents/{document_id}/extract`
  - Path params:
    - `document_id: UUID`
  - No body.
- **Behavior**:
  - Fetches `Document` by `document_id`; if not found → `HTTPException(404, "Document not found")`.
  - Creates a `Job` with:
    - `task_type="extract"`, `status="queued"`.
  - Commits and refreshes job.
  - Enqueues `run_extraction_job(job.id)` in `BackgroundTasks`.
- **Response**:
  - Status: `200 OK`
  - Body: `JobResponse` (queued job).
- **Errors**:
  - `404 Not Found` if document missing.
  - `422 Unprocessable Entity` for invalid UUID.

### 6.5 Embed router (`routers/embed.py`)

- **Router definition**:
  - `router = APIRouter(tags=["embed"])`
- **Dependencies**:
  - `db: AsyncSession = Depends(get_db)`.
  - `BackgroundTasks`.
  - `Document`, `Job`, `DocumentPage`, `Embedding` models.
  - `AsyncSessionLocal`.
  - `chunk_text`, `generate_embeddings`, `logger`.
  - `JobResponse` response model.

#### `run_embed_job(job_id: UUID)` (background task)

- Fetches `Job` by ID; if missing, exits.
- Sets `status="processing"` and commits.
- Selects all `DocumentPage` rows for the document, ordered by page number.
- For each page:
  - If `page.text` is empty, skip.
  - Call `chunk_text(page.text)` to get token‑aware chunks.
  - Build `all_chunks` list:
    - `chunk_id="p{page_number}-c{i}"`, `page_start`, `page_end`, `content`.
- If `all_chunks` is empty:
  - Sets `job.status="done"` and commits (no embeddings created).
- Otherwise:
  - Batches texts into size 100.
  - For each batch:
    - Calls `generate_embeddings(batch_texts)` (OpenAI embeddings).
    - For each embedding, inserts an `Embedding` row with `document_id`, `chunk_id`, `page_start`, `page_end`, `content`, `embedding`.
- On success: sets `job.status="done"`.
- On failure: logs and sets `job.status="failed"` with `error_message`.

#### POST `/documents/{document_id}/embed`

- **Purpose**: Queue an embedding job for a document.
- **Request**:
  - Method: `POST`
  - Path: `/documents/{document_id}/embed`
  - Path params:
    - `document_id: UUID`
  - No body.
- **Behavior**:
  - Validates that `Document` exists; else `404`.
  - Creates a `Job` with `task_type="embed"`, `status="queued"`.
  - Commits and refreshes.
  - Schedules `run_embed_job` via `BackgroundTasks`.
- **Response**:
  - Status: `200 OK`
  - Body: `JobResponse`.
- **Errors**:
  - `404 Not Found` if document missing.
  - `422 Unprocessable Entity` for invalid UUID.

### 6.6 Ask router (`routers/ask.py`)

- **Router definition**:
  - `router = APIRouter(tags=["ask"])`
- **Dependencies**:
  - `db: AsyncSession = Depends(get_db)`.
  - `Document` model.
  - `AskRequest`, `AskResponse` models.
  - `generate_embeddings`, `retrieve_chunks`, `answer_question`.

#### POST `/documents/{document_id}/ask`

- **Purpose**: Ask a natural language question about a **single document**.
- **Request**:
  - Method: `POST`
  - Path: `/documents/{document_id}/ask`
  - Path params:
    - `document_id: UUID`
  - JSON body (`AskRequest`):

    ```json
    {
      "question": "What is the total amount on this invoice?"
    }
    ```

- **Behavior**:
  - Ensures document exists; else `HTTPException(404, "Document not found")`.
  - Calls `generate_embeddings([req.question])` and takes the first embedding.
  - Calls `retrieve_chunks(db, str(document_id), question_embedding)`:
    - Uses `settings.rag_top_k` by default.
    - Orders by `embedding.cosine_distance(question_embedding)` via pgvector.
  - If `chunks` is empty:
    - Returns `AskResponse(answer="No context available. Please embed the document first.", citations=[])`.
  - Otherwise:
    - Calls `answer_question(req.question, chunks)`:
      - Builds a context string from chunks (including chunk IDs and page ranges).
      - Sends a system + user message to OpenAI chat with strict “no hallucination” instructions and page citation requirement.
      - Returns `AskResponse`.
- **Response**:
  - Status: `200 OK`
  - Body (`AskResponse`):

    ```json
    {
      "answer": "The total amount is 123.45 USD.",
      "citations": [
        {
          "chunk_id": "p1-c0",
          "page_start": 1,
          "page_end": 1,
          "text": "Full chunk text here..."
        }
      ]
    }
    ```

- **Errors**:
  - `404 Not Found` if document missing.
  - `422 Unprocessable Entity` if body is missing or malformed.

### 6.7 Review router (`routers/review.py`)

- **Router definition**:
  - `router = APIRouter(tags=["review"])`
- **Dependencies**:
  - `db: AsyncSession = Depends(get_db)`.
  - `Extraction`, `ReviewEdit` models.
  - `ReviewEditRequest`, `ReviewEditResponse` schemas.

#### POST `/extractions/{extraction_id}/review`

- **Purpose**: Persist a human review/edit of a specific extraction and update the extraction data.
- **Request**:
  - Method: `POST`
  - Path: `/extractions/{extraction_id}/review`
  - Path params:
    - `extraction_id: UUID`
  - Body (`ReviewEditRequest`):

    ```json
    {
      "updated_data": {
        "document_type": "Invoice",
        "total_amount": 123.45,
        "currency": "USD"
      },
      "edited_by": "reviewer@example.com"
    }
    ```

    - `updated_data`: `Dict[str, Any]` – the new JSON you want to store.
    - `edited_by`: optional identifier of the reviewer.

- **Behavior**:
  - Fetches `Extraction` by ID; if missing → `HTTPException(404, "Extraction not found")`.
  - Creates `ReviewEdit` row:
    - `original_data` is the current `extraction.data`.
    - `updated_data` is from request.
    - `extraction_id` is linked.
  - Updates `extraction.data = req.updated_data`.
  - Commits and refreshes `edit`.
- **Response**:
  - Status: `200 OK`
  - Body (`ReviewEditResponse`):
    - `id`, `extraction_id`, `original_data`, `updated_data`, `created_at`.
- **Errors**:
  - `404 Not Found` if extraction missing.
  - `422 Unprocessable Entity` for malformed body or UUID.

### 6.8 Export router (`routers/export.py`)

- **Router definition**:
  - `router = APIRouter(tags=["export"])`
- **Dependencies**:
  - `db: AsyncSession = Depends(get_db)`.
  - `Document`, `Extraction` models.
  - `csv`, `io`, `JSONResponse`, `Response`.

#### GET `/documents/{document_id}/export.json`

- **Purpose**: Export the **latest extraction** for a document as raw JSON.
- **Request**:
  - Method: `GET`
  - Path: `/documents/{document_id}/export.json`
  - Path params:
    - `document_id: UUID`
- **Behavior**:
  - Validates that the document exists; if not, `404 "Document not found"`.
  - Fetches the most recent `Extraction` for the document:
    - Orders by `created_at DESC`, takes `.first()`.
  - If no extraction exists, `HTTPException(404, "No extractions found for this document")`.
  - Returns `JSONResponse(content=extraction.data)`.
- **Response**:
  - Status: `200 OK`
  - Body: The raw JSON originally produced by extraction (structure defined by `ExtractionSchema` but free‑form).
- **Errors**:
  - `404 Not Found` if document or extraction missing.

#### GET `/documents/{document_id}/export.csv`

- **Purpose**: Export the latest extraction as a flattened CSV, with optional line‑item section.
- **Request**:
  - Method: `GET`
  - Path: `/documents/{document_id}/export.csv`
  - Path params:
    - `document_id: UUID`
- **Behavior**:
  - Similar document and extraction lookups as JSON export.
  - Builds CSV:
    - `headers = [k for k in data.keys() if k != "line_items"]`.
    - Writes one row of headers and one row of values.
    - If `line_items` exists and is a non‑empty list:
      - Adds an empty row and a `"--- LINE ITEMS ---"` row.
      - Infers `li_headers` from the first line item keys.
      - Writes header row and one row per line item.
  - Returns `Response(content=csv_str, media_type="text/csv")`.
- **Response**:
  - Status: `200 OK`
  - Body: CSV string, structured as above.
- **Errors**:
  - `404 Not Found` if document or extraction missing.

---

## 7) Service Layer Deep Dive

### 7.1 `services/qa.py`

- **`answer_question(question: str, chunks: List[Embedding]) -> AskResponse`**
  - Inputs:
    - User question string.
    - List of `Embedding` ORM objects (retrieved chunks).
  - Steps:
    - Logs that it is generating an answer.
    - Builds `context_text` concatenating chunk metadata and content.
    - Creates OpenAI chat messages with:
      - System prompt enforcing **no hallucination** and **page citation**.
      - User message containing context and question.
    - Calls `openai_client.chat.completions.create` with `model=settings.chat_model`.
    - Extracts answer text.
    - Creates a `Citation` for each chunk (`chunk_id`, `page_start`, `page_end`, `text`).
  - Output:
    - `AskResponse(answer, citations=...)`.

### 7.2 `services/retriever.py`

- **`retrieve_chunks(db: AsyncSession, document_id: str, question_embedding: list[float], top_k: int = settings.rag_top_k)`**
  - Inputs:
    - Async DB session.
    - Document ID as string.
    - Question embedding vector.
    - Number of results (`top_k`).
  - Steps:
    - Logs retrieval intent.
    - Builds a SQLAlchemy `select(Embedding)` query:
      - Filters by `Embedding.document_id == document_id`.
      - Orders by `Embedding.embedding.cosine_distance(question_embedding)` (pgvector).
      - Limits to `top_k`.
    - Executes and returns `Embedding` list.

### 7.3 `services/embedder.py`

- **OpenAI embeddings client**:
  - `openai_client = AsyncOpenAI(api_key=settings.openai_api_key)`.
- **`generate_embeddings(texts: list[str]) -> list[list[float]]`**
  - Decorated with `@retry` (tenacity):
    - Up to 3 attempts.
    - Exponential backoff (min 2s, max 10s).
    - `reraise=True`.
  - Steps:
    - Logs how many chunks it is embedding.
    - Calls `openai_client.embeddings.create(input=texts, model=settings.openai_embed_model)`.
    - Returns `data.embedding` for each item.
  - Errors:
    - On failure, logs and re‑raises; background job marks job as `failed`.

### 7.4 `services/chunker.py`

- **`chunk_text(text: str, chunk_size: int = settings.chunk_size_tokens, chunk_overlap: int = settings.chunk_overlap_tokens) -> list[str]`**
  - Inputs:
    - Raw text.
    - Chunk size and overlap in tokens.
  - Steps:
    - Splits text on whitespace.
    - Iterates and uses `count_tokens` (from `utils.tokens`) per word.
    - Builds chunks such that each chunk’s token count ≤ `chunk_size`.
    - Maintains an overlapping tail of previous tokens up to `chunk_overlap` for context continuity.
  - Output:
    - List of chunk strings.

### 7.5 `services/validator.py`

- **`validate_extraction(data: ExtractionSchema) -> str`**
  - Rules (deterministic):
    - Fails if:
      - `document_type` is empty.
      - `summary` shorter than 10 characters.
      - `date_issued` is non‑ISO parseable.
      - `total_amount < 0`.
      - `currency` not a 3‑letter uppercase alphabetic string.
    - Flags (`"FLAGGED"`) if:
      - `confidence < 0.6`.
    - Otherwise:
      - Returns `"PASSED"`.

### 7.6 `services/extractor.py`

- Uses `instructor` to wrap `AsyncOpenAI` for tool‑mode structured outputs:
  - `client = instructor.from_openai(AsyncOpenAI(api_key=settings.openai_api_key), mode=instructor.Mode.TOOLS)`.
- **`extract_document_features(text: str) -> ExtractionSchema`**
  - Decorated with `@retry(stop_after_attempt(settings.llm_retries + 1), wait_exponential(...), reraise=True)`.
  - Steps:
    - Logs that extraction is running.
    - Calls `client.chat.completions.create` with:
      - `model=settings.chat_model`.
      - `response_model=ExtractionSchema`.
      - System prompt describing a “highly capable document extraction system” that must not hallucinate.
      - User message containing the full document text.
    - Returns an `ExtractionSchema` instance.
  - Errors:
    - Logged and re‑raised so the job can mark itself as failed.

### 7.7 `services/pdf_parser.py`

- Uses PyMuPDF (`fitz`), OpenAI, and Supabase Storage.
- **`parse_pdf(file_bytes: bytes, document_id: str)`**
  - Inputs:
    - Raw PDF bytes.
    - Document ID string.
  - Steps:
    - Opens PDF from memory.
    - Iterates each page:
      - Extracts text via `page.get_text()`.
      - Sets `text_quality_score = 1.0` and `page_image_key = None` by default.
      - If extracted text is shorter than 100 characters:
        - Logs a notification.
        - Renders page to PNG bytes.
        - Calls `_extract_text_via_vision(image_bytes)`:
          - Sends an image to OpenAI vision model (`settings.chat_model`) with instructions to return only text.
        - Uses vision text (if any) and reduces `text_quality_score` to `0.8`.
        - Uploads the page image to Supabase under `{document_id}/pages/page_{page_number}.png`.
      - Appends dict with `page_number`, `text`, `text_quality_score`, `page_image_key` to results.
    - Returns `(total_pages, pages_data)`.

### 7.8 `services/supabase_storage.py`

- **Supabase client**:
  - `create_client(settings.supabase_url, settings.supabase_service_role_key)`.
  - Uses `settings.supabase_storage_bucket` as bucket.
- **Methods**:
  - `upload_file(file_bytes, destination_key, content_type="application/pdf")`:
    - Logs upload.
    - Calls `supabase.storage.from_(bucket).upload(...)`.
  - `download_file(file_key)`:
    - Logs download.
    - Calls `supabase.storage.from_(bucket).download(file_key)`.

### 7.9 Utilities

- `utils.tokens.count_tokens(text: str, model: str | None = None) -> int`
  - Uses `settings.chat_model` by default.
  - Falls back to `"cl100k_base"` if the model is unknown.
- `utils.ids.generate_id(prefix: str = "") -> str`
  - Generates a hyphen‑less UUID string, optionally prefixed; currently not wired into routers.

---

## 8) Testing Without a Frontend

### 8.1 Using Swagger UI (`/docs`)

1. Start the backend (e.g., `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`).
2. Open `http://localhost:8000/docs` in your browser.
3. Test routes in this order:
   - **Health**:
     - Expand `GET /health` and click “Try it out” → “Execute”.
   - **Upload a document**:
     - Expand `POST /documents`.
     - Click “Try it out”.
     - Use the file picker to select a `.pdf`.
     - Execute; note the returned `id` (this is your `document_id`).
   - **List and fetch documents**:
     - `GET /documents` to verify the list.
     - `GET /documents/{document_id}` with the ID from upload.
   - **Trigger extraction & embedding jobs**:
     - `POST /documents/{document_id}/extract`.
     - `POST /documents/{document_id}/embed`.
     - Copy returned `job.id` for each.
     - Poll `GET /jobs/{job_id}` until `status` is `done`, `needs_review`, or `failed`.
   - **Ask questions**:
     - `POST /documents/{document_id}/ask` with a JSON body like:

       ```json
       {
         "question": "What is the total amount on this invoice?"
       }
       ```

   - **Export results**:
     - `GET /documents/{document_id}/export.json`.
     - `GET /documents/{document_id}/export.csv`.
   - **Review an extraction**:
     - You will need an `extraction_id` from the DB (or future UI). Once you have it:
       - Call `POST /extractions/{extraction_id}/review` with `updated_data` and optional `edited_by`.

### 8.2 `curl` examples (macOS)

Set a base URL:

```bash
export BASE_URL="http://localhost:8000"
```

**Health check**

```bash
curl "$BASE_URL/health"
```

**Upload PDF**

```bash
curl -X POST "$BASE_URL/documents" \
  -F "file=@/path/to/document.pdf;type=application/pdf"
```

**List documents**

```bash
curl "$BASE_URL/documents"
```

**Get a document by ID**

```bash
DOCUMENT_ID="11111111-1111-1111-1111-111111111111"
curl "$BASE_URL/documents/$DOCUMENT_ID"
```

**Trigger extraction job**

```bash
curl -X POST "$BASE_URL/documents/$DOCUMENT_ID/extract"
```

**Trigger embedding job**

```bash
curl -X POST "$BASE_URL/documents/$DOCUMENT_ID/embed"
```

The above return `JobResponse` objects with a `job_id` you can poll:

```bash
JOB_ID="22222222-2222-2222-2222-222222222222"
curl "$BASE_URL/jobs/$JOB_ID"
```

**Ask a question**

```bash
curl -X POST "$BASE_URL/documents/$DOCUMENT_ID/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the total amount on this invoice?"
  }'
```

**Export JSON**

```bash
curl "$BASE_URL/documents/$DOCUMENT_ID/export.json"
```

**Export CSV**

```bash
curl "$BASE_URL/documents/$DOCUMENT_ID/export.csv"
```

**Submit a review**

You need a valid `EXTRACTION_ID` from the `extractions` table:

```bash
EXTRACTION_ID="33333333-3333-3333-3333-333333333333"

curl -X POST "$BASE_URL/extractions/$EXTRACTION_ID/review" \
  -H "Content-Type: application/json" \
  -d '{
    "updated_data": {
      "document_type": "Invoice",
      "total_amount": 123.45,
      "currency": "USD"
    },
    "edited_by": "reviewer@example.com"
  }'
```

### 8.3 HTTPie equivalents (optional)

If you have HTTPie (`http`) installed:

```bash
http GET "$BASE_URL/health"
http GET "$BASE_URL/documents"
http GET "$BASE_URL/documents/$DOCUMENT_ID"
http POST "$BASE_URL/documents/$DOCUMENT_ID/extract"
http POST "$BASE_URL/documents/$DOCUMENT_ID/embed"
http POST "$BASE_URL/documents/$DOCUMENT_ID/ask" question=="What is the total amount?"
http GET "$BASE_URL/documents/$DOCUMENT_ID/export.json"
http GET "$BASE_URL/documents/$DOCUMENT_ID/export.csv"
http POST "$BASE_URL/extractions/$EXTRACTION_ID/review" \
  updated_data:='{"document_type": "Invoice"}' \
  edited_by="reviewer@example.com"
```

**Upload via HTTPie** (using `curl` is more straightforward for multipart uploads, but HTTPie can do it too):

```bash
http -f POST "$BASE_URL/documents" file@/path/to/document.pdf
```

---

## 9) Data Storage & Persistence

### 9.1 Database (Postgres + pgvector)

From `db/models.py` and `db/migrations.sql`, the backend uses:

- **Tables**:
  - `documents`:
    - `id` (UUID PK), `filename`, `storage_key`, `total_pages`, `created_at`.
  - `jobs`:
    - `id`, `document_id` (FK), `task_type`, `status`, `error_message`, `created_at`, `updated_at`.
  - `document_pages`:
    - `id`, `document_id` (FK), `page_number`, `text`, `text_quality_score`, `page_image_key`.
  - `extractions`:
    - `id`, `document_id` (FK), `data` (JSONB), `status`, `created_at`, `updated_at`.
  - `review_edits`:
    - `id`, `extraction_id` (FK), `original_data` (JSONB), `updated_data` (JSONB), `created_at`.
  - `embeddings`:
    - `id`, `document_id` (FK), `chunk_id`, `page_start`, `page_end`, `content`, `embedding` (pgvector).

- **Indexes**:
  - `ix_jobs_document_id_status` on `(document_id, status)`.
  - `ix_document_pages_document_id_page` on `(document_id, page_number)`.
  - `ix_extractions_document_id` on `document_id`.
  - `ix_embeddings_embedding` on `embedding` using `ivfflat (embedding vector_cosine_ops)`.

Usage by routers:

- Documents router writes:
  - `documents`, `document_pages`.
- Extract router:
  - Inserts `jobs` (task_type `extract`) and `extractions`.
- Embed router:
  - Inserts `jobs` (task_type `embed`) and `embeddings`.
- Ask router:
  - Reads `documents` and `embeddings`.
- Review router:
  - Reads/writes `extractions` and `review_edits`.
- Export router:
  - Reads `documents` and `extractions`.

### 9.2 Supabase Storage

- `SupabaseStorage` client uses:
  - `settings.supabase_url`
  - `settings.supabase_service_role_key`
  - `settings.supabase_storage_bucket`
- The documents router:
  - Uploads the original PDF as `{doc.id}/{filename}`.
- The PDF parser:
  - For low‑text pages, uploads page images under `{document_id}/pages/page_{page_number}.png`.

### 9.3 Embeddings and retrieval

- Embeddings:
  - Stored in the `embeddings` table with a fixed dimension matching `OPENAI_EMBED_DIMS` and the pgvector column definition (`Vector(1536)`).
- Retrieval:
  - Uses `embedding.cosine_distance(question_embedding)` ordering for nearest neighbors.
  - Top‑k is controlled by `settings.rag_top_k`.

---

## 10) Troubleshooting

### 10.1 Missing or invalid environment variables

- **Symptoms**:
  - OpenAI errors such as authentication failures.
  - Supabase upload/download failures.
  - Database connection errors at startup.
  - `ValueError` from pydantic when parsing env types.
- **Checks**:
  - Confirm `.env` exists in `backend/` and contains placeholder but well‑formed values.
  - Ensure `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `DATABASE_URL` are set.
  - Make sure new env vars respect the types in `Settings`.

### 10.2 OpenAI API key and model issues

- **Symptoms**:
  - 401/403 errors from OpenAI calls in logs.
  - Extraction or embedding jobs stuck in `failed` state with an error message.
- **Checks**:
  - Verify `OPENAI_API_KEY` is non‑empty and valid.
  - Confirm `CHAT_MODEL` and `OPENAI_EMBED_MODEL` are valid models for your OpenAI account.

### 10.3 Supabase errors

- **Symptoms**:
  - Upload failures when calling `POST /documents`.
  - Vision page image upload failures from `pdf_parser`.
- **Checks**:
  - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` correctly configured.
  - `SUPABASE_STORAGE_BUCKET` exists in your Supabase project.
  - Network access to Supabase from the backend environment.

### 10.4 Database and pgvector issues

- **Symptoms**:
  - Backend cannot start due to DB connection errors.
  - Retrieval queries fail or raise SQL errors.
  - `embeddings` insert fails due to dimension mismatch.
- **Checks**:
  - `DATABASE_URL` uses the `postgresql+psycopg://` URI, as noted in `.env`.
  - Run `db/migrations.sql` against your database (once) to create tables and pgvector extension.
  - Ensure `OPENAI_EMBED_DIMS` matches the vector dimension in `embeddings` (`1536` by default).

### 10.5 Docker volume / missing Python in container

- **Symptom**:
  - Inside the container, commands like `uv` or `python` fail because the virtual environment is missing.
- **Cause**:
  - Overriding `/app` with a host bind mount that does not contain `.venv`, effectively hiding the environment created during `docker build`.
- **Fix**:
  - Avoid bind‑mounting over `/app` unless you also install dependencies in the container after mounting, or adjust Dockerfile and compose accordingly.

### 10.6 “module has no attribute router” / new routers

- **Symptom**:
  - Import errors like `module 'app.routers.<name>' has no attribute 'router'` when wiring new routers.
- **Cause**:
  - Every router module in `routers/` must define a module‑level `router = APIRouter(...)` variable, and `routers/__init__.py` must re‑export it.
- **Fix**:
  - Ensure your new router file has `router = APIRouter(...)` and that `routers/__init__.py` contains:

    ```python
    from .my_new_router import router as my_new_router
    ```

### 10.7 422 validation errors

- **Symptoms**:
  - Responses with status `422` and a body containing `{"detail": [...]}` when calling endpoints.
- **Cause**:
  - FastAPI / Pydantic validation failures on:
    - Path or query parameters (e.g., bad UUID).
    - JSON body shape mismatches (missing required fields).
    - Wrong content type (e.g., not using multipart for file uploads).
- **Example** (bad `document_id`):

  ```json
  {
    "detail": [
      {
        "type": "uuid_parsing",
        "loc": ["path", "document_id"],
        "msg": "Input should be a valid UUID",
        "input": "not-a-uuid"
      }
    ]
  }
  ```

- **Fix**:
  - Use valid UUIDs.
  - Match JSON bodies to the documented schemas (`AskRequest`, `ReviewEditRequest`, etc.).
  - For `/documents`, send `multipart/form-data` with a `file` field containing a `.pdf`.

---

## 11) Pre‑Frontend Checklist

Before building a frontend on top of PaperBridge, verify the following:

1. **Environment configuration**:
   - `.env` exists at `backend/.env` with non‑production but valid values for `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `DATABASE_URL`.
2. **Database ready**:
   - Postgres is reachable from the backend environment.
   - `db/migrations.sql` has been applied (tables and pgvector are present).
3. **Supabase Storage ready**:
   - The configured bucket (`SUPABASE_STORAGE_BUCKET`) exists.
4. **Backend runs locally**:
   - `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` starts without errors.
5. **Health endpoint**:
   - `GET /health` returns `{"status": "ok"}`.
6. **Document upload**:
   - `POST /documents` successfully uploads a sample PDF and returns a `DocumentResponse`.
7. **Jobs and background processing**:
   - `POST /documents/{id}/extract` and `/embed` create jobs.
   - `GET /jobs/{job_id}` transitions from `queued` → `processing` → `done` / `needs_review` (or `failed` with a clear error).
8. **Extraction and export**:
   - After a successful extraction job, `GET /documents/{id}/export.json` returns meaningful data.
   - `GET /documents/{id}/export.csv` returns a CSV including line items if present.
9. **Embeddings and QA**:
   - After embedding, `POST /documents/{id}/ask` returns an `AskResponse` with an answer and citations, or a clear “No context available” message.
10. **Review workflow** (if you can access DB):
    - You can identify an `extraction_id` and call `POST /extractions/{extraction_id}/review` to persist manual corrections.
11. **CORS behavior**:
    - A simple browser fetch from a dev frontend origin to `http://localhost:8000/health` succeeds without CORS errors (given current `allow_origins=["*"]`).

Once all items pass, the backend is in a good state for a frontend to integrate with document upload, processing progress, QA, review, and export flows.

