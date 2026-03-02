# Deployment

## Strategy

This repo is configured for **Strategy 1**:
- Deploy only `apps/web` (Next.js) to Vercel.
- Deploy `backend` (FastAPI) to a backend host (Render/Fly/Railway/etc.).
- Frontend calls backend through `/api/pb/*` proxy route using `NEXT_PUBLIC_API_BASE_URL`.

This avoids Vercel Python serverless constraints and is the most stable setup for the current codebase.

## Vercel (Frontend)

Create a Vercel project from this repository with:
- Framework Preset: `Next.js`
- Root Directory: `apps/web`
- Install Command: `pnpm -w install`
- Build Command: `pnpm -w build`
- Output Directory: leave default
- Node.js: 20+

Required Vercel environment variable:
- `NEXT_PUBLIC_API_BASE_URL` = your deployed backend URL (for example `https://paperbridge-api.onrender.com`)

No `vercel.json` is required for this monorepo setup.

## Backend Host (FastAPI)

Use `backend/Dockerfile` on your backend host.

Example container start command:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Backend required env vars:
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET`
- `OPENAI_API_KEY`
- Optional tuning: `CHAT_MODEL`, `OPENAI_EMBED_MODEL`, `OPENAI_EMBED_DIMS`, `LLM_TIMEOUT_S`, `LLM_RETRIES`, `CORS_ALLOW_ORIGINS`

Before first deploy, run SQL migration:
- `backend/app/db/migrations.sql`

## Build Verification Commands

From repo root:

```bash
pnpm -w install
pnpm -w build
pnpm --filter web build
```

From backend:

```bash
cd backend
.venv/bin/python -m unittest -v tests/test_api_contract.py tests/test_pipeline_api.py
```

## Troubleshooting

- Vercel build fails because env var missing:
  - Set `NEXT_PUBLIC_API_BASE_URL` in Vercel project settings.
- Frontend can load, but API calls fail:
  - Check backend URL health endpoint and CORS (`CORS_ALLOW_ORIGINS`).
- Pipeline job fails:
  - Poll `GET /jobs/{pipeline_job_id}` and inspect `error_message` + `task_metadata`.
- Slow or failed uploads:
  - Check `MAX_UPLOAD_MB`, storage credentials, and backend logs with request IDs.
