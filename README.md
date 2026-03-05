# PaperBridge

PaperBridge is a full-stack PDF intelligence app: upload documents, auto-process them (parse, extract, embed), then ask grounded questions with page-level citations.  
It is built as a FastAPI + Next.js monorepo with Supabase (Postgres + Storage) and OpenAI models.

## Key features

- PDF upload with checksum deduplication (re-upload returns the existing document record).
- Automatic pipeline orchestration per upload: `extract -> embed` as background jobs.
- Document readiness model surfaced in API/UI: `uploaded | processing | ready | failed`.
- Multi-document and single-document QA with citations.
- Signed download links for stored PDFs.
- Extraction review endpoint for human corrections.

## Tech stack

| Area | Implementation |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, TanStack Query |
| Frontend API boundary | Next.js proxy route at `/api/pb/*` |
| Backend | FastAPI, Pydantic, SQLAlchemy async |
| Database | Supabase Postgres + `pgvector` |
| Object storage | Supabase Storage (private bucket) |
| LLM/Embeddings | OpenAI (`CHAT_MODEL`, `OPENAI_EMBED_MODEL`) |
| PDF parsing | PyMuPDF, OpenAI vision fallback for low-text pages |
| Python tooling | `uv` |
| JS tooling | `pnpm` workspace |

## Architecture

```text
Browser
  -> Next.js app (apps/web)
  -> /api/pb/* proxy
  -> FastAPI backend (backend/app)
     -> Supabase Postgres (documents/pages/jobs/extractions/embeddings)
     -> Supabase Storage (PDFs + rendered page images when vision fallback is used)
     -> OpenAI APIs (extraction, embeddings, QA)
```

Components:

- `apps/web`: dashboard, documents list/detail, processing view, ask view.
- `backend/app/routers`: HTTP API surface.
- `backend/app/services`: pipeline, parsing, retrieval, QA, storage integration.
- `backend/app/db`: SQLAlchemy models + SQL migration script.

## End-to-end flow

1. Upload PDF to `POST /documents` or `POST /documents/batch`.
2. Backend validates PDF, computes checksum, uploads original PDF to Supabase Storage, parses pages.
3. If page text is sparse, backend renders page image and runs vision extraction; image is stored.
4. Backend creates/reuses a `pipeline` job and runs extraction then embedding in background.
5. Client polls `GET /jobs/{job_id}` until `done`/`failed`.
6. Once embeddings exist, document status becomes `ready`.
7. Ask via `POST /ask` with optional `doc_ids`; answer returns markdown text plus citation objects.

## Project structure

```text
paper-bridge/
├── apps/
│   └── web/
│       └── src/
│           ├── app/                  # pages + Next proxy route
│           ├── components/           # UI components/providers
│           ├── hooks/
│           └── lib/                  # typed API client + schemas
├── backend/
│   ├── app/
│   │   ├── core/
│   │   ├── db/
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── services/
│   ├── scripts/                      # smoke/verification scripts
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml
├── docs/
├── docker-compose.yml
└── README.md
```

## Setup

### Prerequisites

- Node.js 20+
- `pnpm` 9+
- Python 3.12+
- `uv`
- Supabase project with Postgres + Storage bucket
- OpenAI API key

### Environment variables

Backend (`backend/.env`):

```bash
DEBUG=false
API_ENV=local
API_HOST=0.0.0.0
API_PORT=8000

OPENAI_API_KEY=sk-...
CHAT_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_EMBED_DIMS=1536

SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_STORAGE_BUCKET=paperbridge-documents

DATABASE_URL=postgresql+psycopg://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

MAX_UPLOAD_MB=25
MAX_PAGES=200
CHUNK_SIZE_TOKENS=800
CHUNK_OVERLAP_TOKENS=120
QA_TOP_K=5
RAG_MAX_TOP_K=15
RAG_VECTOR_CANDIDATES=50
RAG_LEXICAL_WEIGHT=0.35
RAG_CONTEXT_MAX_TOKENS=6000
VECTOR_IVFFLAT_PROBES=10
EMBEDDING_BATCH_SIZE=100

LLM_RETRIES=2
LLM_TIMEOUT_S=45
ASK_RATE_LIMIT_PER_MINUTE=60
UPLOAD_RATE_LIMIT_PER_MINUTE=20
```

Frontend (`apps/web/.env.local`):

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Note: backend code reads `QA_TOP_K`. If you copied `backend/.env.example`, replace `RAG_TOP_K` with `QA_TOP_K`.

### Install commands

```bash
pnpm -w install
cd backend && uv sync
```

### Database initialization

Run `backend/app/db/migrations.sql` against your Supabase Postgres database.

Example:

```bash
psql "$DATABASE_URL" -f backend/app/db/migrations.sql
```

## Run locally

### Backend

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd apps/web
pnpm dev
```

Frontend runs on `http://localhost:3000` and calls backend through `/api/pb/*`.

## API overview

### Health

- `GET /health`
- `HEAD /health`

### Documents

- `POST /documents` (multipart `file`)
- `POST /documents/batch` (multipart `files`)
- `GET /documents?skip=<int>&limit=<int>`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/download` (signed URL response `{url, filename}`)
- `DELETE /documents/{document_id}`

Upload response shape:

```json
{
  "id": "uuid",
  "filename": "example.pdf",
  "checksum_sha256": "hex",
  "version": 1,
  "total_pages": 12,
  "status": "processing",
  "created_at": "ISO-8601",
  "pipeline_job_id": "uuid"
}
```

### Jobs

- `GET /jobs/{job_id}`

Job responses include `task_type` (`extract`, `embed`, `pipeline`) and optional `task_metadata` for pipeline step state.

### QA

- `POST /ask`
- Request body: `{ "question": "...", "doc_ids": ["uuid", ...] }`
- `doc_ids` is optional; omit or set `null` to search all ready documents.

### Review

- `POST /extractions/{extraction_id}/review`
- Request body: `{ "updated_data": {...}, "edited_by": "name-or-email" }`

## Concrete examples

### Upload

```bash
curl -s -F "file=@/absolute/path/to/sample.pdf" \
  "http://127.0.0.1:8000/documents"
```

### Ask question

```bash
curl -s -X POST "http://127.0.0.1:8000/ask" \
  -H "content-type: application/json" \
  -d '{"question":"What are the key requirements?","doc_ids":["<document_uuid>"]}'
```

### Example answer format

```json
{
  "answer": "Direct answer sentence.[1]\n\nKey requirements include:\n- Requirement A.[1]\n- Requirement B.[2]",
  "citations": [
    { "filename": "sample.pdf", "page_start": 10, "page_end": 10 },
    { "filename": "sample.pdf", "page_start": 12, "page_end": 12 }
  ]
}
```

## RAG and citations behavior

- Retrieval is hybrid: vector similarity + lexical reranking + rule-based boosting.
- Backend embeds the question and retrieves chunks from `embeddings` table, optionally scoped by `doc_ids`.
- QA model must emit internal `[[chunk:<id>]]` markers; backend converts these to numeric `[1]...[N]` in answer text.
- Citation objects are deduplicated by `(filename, page_start, page_end)` and capped at 4 entries.
- Citation pages are normalized to 1-indexed output; older 0-indexed values are corrected.
- If evidence is insufficient or markers are invalid/missing, API returns:
  - `answer`: `"Insufficient context in the provided documents. Please ask a narrower question."`
  - `citations`: `[]`

## Troubleshooting

- `422 validation_error` on `/ask`: request body must only include `question` and optional `doc_ids`/`document_ids`.
- Upload rejected with 400/413: ensure `.pdf`, allowed content type, and file size under `MAX_UPLOAD_MB`.
- Signed download fails (400/404/502): verify `storage_key` validity and file presence in Supabase bucket.
- Jobs remain `queued`: pipeline/extraction/embedding run in FastAPI background tasks; ensure API process is running.
- `Embedding dimension mismatch`: keep `OPENAI_EMBED_MODEL` and `OPENAI_EMBED_DIMS` aligned.

## License

MIT. See `LICENSE`.
