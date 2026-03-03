# PaperBridge Docs

PaperBridge is a document intelligence system with a Next.js frontend and a FastAPI backend.

Core capabilities:
- PDF upload + parse
- Automatic extraction + embedding pipeline
- Ask endpoint with citations
- Document status model (`uploaded | processing | ready | failed`)

## Architecture

```text
Browser (Next.js app on Vercel)
        |
        |  /api/pb/* proxy route
        v
FastAPI backend (separate host: Render/Fly/Railway/etc.)
        |
        +--> Supabase Postgres (documents/pages/jobs/extractions/embeddings + pgvector)
        |
        +--> Supabase Storage (PDFs + optional rendered page images)
        |
        +--> OpenAI APIs (extraction + embeddings + QA)
```

## Job Model

`jobs` table supports:
- `task_type="extract"`
- `task_type="embed"`
- `task_type="pipeline"` with `task_metadata.steps.extract/embed` state

Pipeline flow:
- Upload parses PDF synchronously.
- Upload always queues/reuses a pipeline job.
- Pipeline runs extraction then embedding, with idempotent skip/resume logic.
- Poll with `GET /jobs/{job_id}`.

## Documentation Index

- [Local development](./LOCAL_DEV.md)
- [API reference + curl examples](./API.md)
- [Deployment (Vercel + backend host)](./DEPLOYMENT.md)
