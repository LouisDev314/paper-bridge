# How To Test PaperBridge Backend

## 1) Preconditions

1. Configure `backend/.env` with:
   - `DATABASE_URL`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `OPENAI_API_KEY`
2. Apply SQL in `backend/app/db/migrations.sql` to your Postgres/Supabase DB.
3. Install dependencies and run API:
   ```bash
   cd backend
   uv sync
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## 2) Swagger-first smoke test plan

Open [http://localhost:8000/docs](http://localhost:8000/docs) and run in this order:

1. `GET /health`
   - Expect `200 {"status":"ok"}`.
2. `POST /documents`
   - Upload a small PDF.
   - Expect `200` with `id`, `filename`, `total_pages`.
3. `POST /documents/{document_id}/extract`
   - Expect queued job (`status=queued` or `processing`).
4. `POST /documents/{document_id}/embed`
   - Expect queued job.
5. `GET /jobs/{job_id}` (poll extraction + embedding jobs)
   - Expect terminal `done` / `needs_review`.
6. `POST /ask`
   - Payload example:
   ```json
   {
     "question": "Summarize key obligations in these contracts.",
     "doc_ids": ["<doc-id-1>", "<doc-id-2>"],
     "top_k": 8
   }
   ```
   - Expect `200` with `answer` + citations including `document_id`, `chunk_id`, page range, score.
7. `GET /documents/{document_id}/export.json`
   - Expect latest extraction JSON.
8. `GET /documents/{document_id}/export.csv`
   - Expect CSV payload.

## 3) Optional curl checks

```bash
# health
curl -s http://localhost:8000/health | jq

# upload
DOC=$(curl -s -F "file=@./sample.pdf" http://localhost:8000/documents | jq -r '.id')

# trigger extract/embed
EXTRACT_JOB=$(curl -s -X POST http://localhost:8000/documents/$DOC/extract | jq -r '.id')
EMBED_JOB=$(curl -s -X POST http://localhost:8000/documents/$DOC/embed | jq -r '.id')

# poll
curl -s http://localhost:8000/jobs/$EXTRACT_JOB | jq
curl -s http://localhost:8000/jobs/$EMBED_JOB | jq

# ask
curl -s -X POST http://localhost:8000/ask \
  -H "content-type: application/json" \
  -d "{\"question\":\"What is the total amount?\",\"doc_ids\":[\"$DOC\"],\"top_k\":6}" | jq
```

## 4) Minimal automated test plan (pytest)

Recommended initial suite (small but meaningful):

1. `test_health.py`
   - `GET /health` returns 200 and status payload.
2. `test_ask_schema.py`
   - `POST /ask` rejects invalid payloads (empty question, bad `doc_ids`, bad `top_k`).
3. `test_jobs_polling.py`
   - `GET /jobs/{missing_id}` returns 404 with `error` envelope.
4. `test_documents_validation.py`
   - upload rejects non-PDF and over-size payload.

Use dependency overrides/mocks for DB/OpenAI/Supabase to keep tests deterministic.

## 5) Deterministic verification checklist

- API starts and `/openapi.json` loads.
- Upload validates MIME, extension, and file size limit.
- Re-running embed for same doc does not duplicate vectors (job is idempotent by delete+rebuild).
- `POST /ask` supports multi-doc scoping via `doc_ids`.
- Error responses are consistent:
  ```json
  {"error":{"code":"...","message":"...","request_id":"..."}}
  ```
- `X-Request-ID` header is returned and request completion logs include latency.
