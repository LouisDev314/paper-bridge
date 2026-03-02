# Local Development

## Prerequisites

- Node.js 20+
- `pnpm` 9+
- Python 3.12+
- `uv` (recommended for backend)
- Supabase project with:
  - Postgres database
  - Storage bucket (default: `paperbridge-documents`)
- OpenAI API key

## 1) Backend Setup

From repo root:

```bash
cd backend
cp .env.example .env
```

Set values in `backend/.env`:
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`
- Optional: `CORS_ALLOW_ORIGINS`, `UPLOAD_RATE_LIMIT_PER_MINUTE`, `ASK_RATE_LIMIT_PER_MINUTE`

Apply SQL migration in Supabase SQL editor:

```sql
-- paste and run:
backend/app/db/migrations.sql
```

Install backend dependencies and run API:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 2) Frontend Setup

From repo root:

```bash
pnpm -w install
cp apps/web/.env.example apps/web/.env.local
```

Set in `apps/web/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Run web app:

```bash
pnpm --filter web dev
```

## 3) End-to-End Flow (Upload -> Pipeline -> Ask)

Smoke command (from repo root):

```bash
cd backend
uv run python ../scripts/smoke_pipeline.py --file /absolute/path/to/sample.pdf --auto-process
```

This command:
- uploads the PDF
- queues the pipeline job
- polls until job reaches terminal state

Then query:

```bash
curl -s -X POST http://127.0.0.1:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"Summarize the main finding in one sentence.","top_k":6}' | jq
```

## Common Errors

- `Upload rate limit exceeded`
  - Reduce upload frequency or raise `UPLOAD_RATE_LIMIT_PER_MINUTE`.
- `Failed to parse PDF document`
  - Confirm file is a valid PDF and below `MAX_UPLOAD_MB`.
- `Unable to reach backend API from proxy route`
  - Check `NEXT_PUBLIC_API_BASE_URL` and backend health endpoint.
- `Embedding dimension mismatch`
  - Keep `OPENAI_EMBED_MODEL` and `OPENAI_EMBED_DIMS` aligned.
- Jobs stuck in `queued`
  - Confirm app process is alive; background tasks run in API process.
