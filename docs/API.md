# API Guide

Base URL (local): `http://127.0.0.1:8000`

## Health

```bash
curl -s http://127.0.0.1:8000/health | jq
```

## Upload Single PDF

Baseline upload only (parse, no pipeline):

```bash
curl -s -F "file=@/absolute/path/to/sample.pdf" \
  "http://127.0.0.1:8000/documents?dedupe=true&auto_process=false" | jq
```

Auto pipeline upload (`parse -> extract -> embed`):

```bash
curl -s -F "file=@/absolute/path/to/sample.pdf" \
  "http://127.0.0.1:8000/documents?dedupe=true&auto_process=true" | jq
```

Response includes:
- document fields (`id`, `filename`, `version`, etc.)
- optional `pipeline_job_id`

## Batch Upload

```bash
curl -s \
  -F "files=@/absolute/path/to/a.pdf" \
  -F "files=@/absolute/path/to/b.pdf" \
  "http://127.0.0.1:8000/documents/batch?dedupe=true&auto_process=true" | jq
```

Returns a list of upload responses, each with optional `pipeline_job_id`.

## Manual Jobs (Backward Compatible)

Queue extraction:

```bash
curl -s -X POST "http://127.0.0.1:8000/documents/<document_id>/extract" | jq
```

Queue embedding:

```bash
curl -s -X POST "http://127.0.0.1:8000/documents/<document_id>/embed" | jq
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

```bash
curl -s -X POST http://127.0.0.1:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"What does OVG stand for?","top_k":6}' | jq
```

Scoped ask:

```bash
curl -s -X POST http://127.0.0.1:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"Summarize section 2","doc_ids":["<document_id>"],"top_k":6}' | jq
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
