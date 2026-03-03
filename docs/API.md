# API Guide

Base URL (local): `http://127.0.0.1:8000`

## Health

```bash
curl -s http://127.0.0.1:8000/health | jq
```

## Upload Single PDF

Upload always performs:
1. file store + parse pages
2. dedupe by checksum (always on)
3. pipeline queue (`extract -> embed`)

```bash
curl -s -F "file=@/absolute/path/to/sample.pdf" \
  "http://127.0.0.1:8000/documents" | jq
```

Response includes:
- document fields (`id`, `filename`, `version`, `status`, etc.)
- `pipeline_job_id`

## Batch Upload

```bash
curl -s \
  -F "files=@/absolute/path/to/a.pdf" \
  -F "files=@/absolute/path/to/b.pdf" \
  "http://127.0.0.1:8000/documents/batch" | jq
```

Returns a list of upload responses, each with `pipeline_job_id`.

## Documents

List:

```bash
curl -s "http://127.0.0.1:8000/documents?skip=0&limit=20" | jq
```

Each document includes a derived status:
- `uploaded`
- `processing`
- `ready`
- `failed`

Delete:

```bash
curl -i -X DELETE "http://127.0.0.1:8000/documents/<document_id>"
```

## Poll Jobs

```bash
curl -s "http://127.0.0.1:8000/jobs/<job_id>" | jq
```

Pipeline jobs return:
- `task_type: "pipeline"`
- `status: queued|processing|done|failed`
- `task_metadata.steps.extract` and `task_metadata.steps.embed`

## Ask

`top_k` is backend-controlled (`qa_top_k`, default `5`) and not part of request payload.

```bash
curl -s -X POST http://127.0.0.1:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"What does OVG stand for?"}' | jq
```

Scoped ask:

```bash
curl -s -X POST http://127.0.0.1:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"Summarize section 2","doc_ids":["<document_id>"]}' | jq
```

## Export + Review

```bash
curl -s "http://127.0.0.1:8000/documents/<document_id>/export.json" | jq
curl -s -O "http://127.0.0.1:8000/documents/<document_id>/export.csv"
```

Review endpoint:

```bash
curl -s -X POST "http://127.0.0.1:8000/extractions/<extraction_id>/review" \
  -H 'content-type: application/json' \
  -d '{"updated_data": {"key":"value"}, "edited_by":"reviewer@example.com"}' | jq
```
