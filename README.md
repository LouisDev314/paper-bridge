# Paper Bridge — AI-Native Document Intelligence Platform

Paper Bridge is a full-stack **AI document intelligence system** for extracting structured data, running retrieval-augmented Q&A, and performing semantic search over heterogeneous PDF documents. It is designed as a backend-first platform with a modern web frontend, emphasizing production-grade API design, schema-enforced LLM outputs, and scalable vector search.

The system ingests PDFs (e.g. engineering specs, manuals, invoices), processes them at page-level granularity, and builds an embeddings-backed index using PostgreSQL + pgvector. On top of this index, Paper Bridge exposes APIs for structured extraction, validation of fields, and citation-grounded question answering across multiple documents.  

The goal is to demonstrate a realistic AI platform architecture suitable for backend / ML / AI engineering work: async Python services, FastAPI-based APIs, RAG over pgvector, and a Next.js dashboard for interacting with the system.

---

### Table of Contents

- [Core Features](#core-features)
- [System Architecture](#system-architecture)
  - [High-Level Diagram](#high-level-diagram)
  - [Ingestion Pipeline](#ingestion-pipeline)
  - [Extraction Pipeline](#extraction-pipeline)
  - [RAG Pipeline](#rag-pipeline)
- [Tech Stack](#tech-stack)
- [API Flows](#api-flows)
  - [1. Upload](#1-upload)
  - [2. Embed](#2-embed)
  - [3. Ask](#3-ask)
- [Local Development](#local-development)
  - [Environment Variables](#environment-variables)
  - [Backend Setup (FastAPI)](#backend-setup-fastapi)
  - [Frontend Setup (Nextjs)](#frontend-setup-nextjs)
- [Design Decisions](#design-decisions)
  - [Why pgvector](#why-pgvector)
  - [Why Schema Enforcement](#why-schema-enforcement)
  - [Why FastAPI](#why-fastapi)
- [Future Improvements](#future-improvements)
- [License](#license)

---

## Core Features

- **PDF ingestion (page-level)**: Upload multi-page PDFs (specs, manuals, invoices). Pages are normalized, parsed to text, and chunked for downstream processing.
- **Text chunking + embeddings storage**: Chunks are embedded using OpenAI embeddings and stored in PostgreSQL with pgvector for similarity search.
- **Vector similarity search**: Fast semantic search across multiple documents using pgvector indexes.
- **Citation-based answer generation**: RAG pipeline that retrieves top chunks and generates answers grounded in source text, with per-chunk citations (page / document IDs).
- **Schema-enforced structured extraction**: LLM outputs are constrained to a predefined JSON schema (e.g. invoice fields, spec metadata), with validation on the backend.
- **Multi-document querying**: Queries can span multiple documents by default; retrieval is not limited to a single file.
- **Production-style API**: Clear separation of concerns (ingestion, embedding, querying, extraction), async endpoints, and explicit error handling.

---

## System Architecture

### High-Level Diagram

```mermaid
flowchart LR
    subgraph Client
        UI[Next.js Frontend]
        Dev[API Client / cURL]
    end

    subgraph Backend[FastAPI Backend]
        UP[Upload Service]
        PARSE[PDF Parser & Chunker]
        EMB[Embedding Worker]
        RAG[Q&A / RAG Service]
        EXT[Schema Extraction Service]
        VAL[Validation Layer]
    end

    subgraph DB[Supabase PostgreSQL + pgvector]
        METADATA[(documents, pages, chunks)]
        VEC[(pgvector index)]
        FIELDS[(extracted_fields, validation_status)]
    end

    subgraph OpenAI[OpenAI API]
        LLM[LLM (chat/completions)]
        EMBAPI[Embeddings API]
    end

    Client -->|Upload PDF| UP
    UP --> PARSE
    PARSE -->|chunk text| METADATA
    PARSE -->|enqueue| EMB
    EMB -->|compute embeddings| EMBAPI
    EMB -->|store vectors| VEC

    Client -->|Ask question| RAG
    RAG -->|nearest neighbors| VEC
    RAG -->|load chunks| METADATA
    RAG -->|prompt with context| LLM
    RAG -->|answer + citations| Client

    Client -->|Request extraction| EXT
    EXT -->|LLM with JSON schema| LLM
    EXT --> VAL
    VAL -->|validated fields| FIELDS
    Client -->|read fields + status| FIELDS
```

### Ingestion Pipeline

- **1. PDF Upload**
  - Client uploads a PDF via a FastAPI endpoint.
  - File is stored (local disk, object storage, or Supabase storage) and registered in a `documents` table with metadata (name, source, type).
- **2. Page-level Parsing**
  - PDF is split into pages and each page is parsed to raw text.
  - Pages are stored in a `pages` table linked to the parent document.
- **3. Chunking**
  - Each page is chunked into overlapping text segments based on token / character limits.
  - Chunks are stored in a `chunks` table with references to page and document IDs.
- **4. Embedding Enqueue**
  - New chunks are queued for embedding (synchronous or background task).
  - Status fields (`pending`, `embedded`) are tracked for observability.

### Extraction Pipeline

- **1. Schema Definition**
  - Backend defines JSON schemas (e.g. Pydantic models) for each extraction type (invoice, spec, generic fields, etc.).
- **2. LLM Call with Schema Enforcement**
  - Text context (page/chunk-level) is passed to the OpenAI LLM with instructions and a strict schema (JSON mode / function calling style).
  - The model must return a JSON object conforming to the schema, including field types and validation rules.
- **3. Validation & Storage**
  - The response is validated server-side against the schema; invalid responses are rejected or retried.
  - Valid structured data is stored in `extracted_fields`, along with quality signals (confidence, missing fields, validation status).
- **4. Post-Validation Rules**
  - Additional programmatic validations (range checks, regex, cross-field consistency) are run before marking extraction as `valid`.

### RAG Pipeline

- **1. Query Ingestion**
  - User sends a natural language question (optionally filtered by document IDs, tags, date ranges).
- **2. Embedding + Retrieval**
  - Query is embedded via OpenAI embeddings.
  - pgvector is used to perform KNN search against the `chunks` embeddings, constrained by filters if provided.
- **3. Context Assembly**
  - Top-k chunks (from potentially multiple documents) are deduplicated, sorted, and formatted with document/page references.
- **4. Answer Generation**
  - A prompt instructs the LLM to:
    - Answer based only on retrieved context.
    - Provide citations (document/page or chunk IDs).
    - Explicitly say “I don’t know” when evidence is missing.
- **5. Response**
  - The API returns:
    - The answer text.
    - The list of citations (including document + page identifiers).
    - Retrieval diagnostics (similarity scores, number of documents touched).

---

## Tech Stack

- **Backend**
  - **Language**: Python (async I/O)
  - **Framework**: FastAPI
  - **Database**: PostgreSQL (Supabase)
  - **Vector Search**: pgvector extension
  - **LLM & Embeddings**: OpenAI API
- **Frontend**
  - **Framework**: Next.js (App Router)
  - **Language**: TypeScript
  - **Styling**: Tailwind CSS
- **Deployment**
  - Frontend: Vercel
  - Backend: Connected to Supabase PostgreSQL (and configurable for other infra)

---

## API Flows

Below are example REST-style flows that demonstrate how a client interacts with the system. Endpoint paths and payloads are representative of a production-style design.

### 1. Upload

**Endpoint**

- `POST /api/v1/documents/upload`

**Request (multipart/form-data)**

```bash
curl -X POST https://your-backend.example.com/api/v1/documents/upload \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@/path/to/document.pdf" \
  -F "type=invoice" \
  -F "source=internal"
```

**Sample JSON Response**

```json
{
  "document_id": "doc_123",
  "filename": "document.pdf",
  "type": "invoice",
  "status": "ingested",
  "pages": 12
}
```

This triggers parsing into pages and chunks and enqueues those chunks for embedding.

### 2. Embed

In many deployments, embedding happens automatically after upload. The API can also expose an explicit control surface.

**Endpoint**

- `POST /api/v1/embeddings/run`

**Request**

```bash
curl -X POST https://your-backend.example.com/api/v1/embeddings/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "document_id": "doc_123",
    "max_chunks": 500
  }'
```

**Sample JSON Response**

```json
{
  "document_id": "doc_123",
  "queued_chunks": 180,
  "embedded_chunks": 180,
  "status": "completed"
}
```

### 3. Ask

**Endpoint**

- `POST /api/v1/rag/ask`

**Request**

```bash
curl -X POST https://your-backend.example.com/api/v1/rag/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "query": "What is the maximum operating temperature specified in these documents?",
    "filters": {
      "document_ids": ["doc_123", "doc_456"]
    },
    "top_k": 8
  }'
```

**Sample JSON Response**

```json
{
  "answer": "The maximum operating temperature is 85°C, as specified in document doc_123 on page 5.",
  "citations": [
    {
      "document_id": "doc_123",
      "page_number": 5,
      "chunk_id": "chunk_987",
      "score": 0.89
    },
    {
      "document_id": "doc_456",
      "page_number": 3,
      "chunk_id": "chunk_654",
      "score": 0.83
    }
  ],
  "retrieval": {
    "total_chunks_searched": 6000,
    "top_k": 8,
    "unique_documents": 2
  }
}
```

A similar pattern can be used for structured extraction:

- `POST /api/v1/extractions/run` (e.g. for invoice fields)
- `GET /api/v1/extractions/{document_id}` to fetch validated fields.

---

## Local Development

### Environment Variables

Create a `.env` file (or equivalent) for both backend and frontend. Representative variables:

```bash
# Backend
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/paper_bridge
PGVECTOR_ENABLED=true

# Optional: Supabase-style DSN
SUPABASE_DB_URL=postgresql://user:password@db.host:6543/postgres

# CORS / API
BACKEND_PORT=8000
BACKEND_HOST=0.0.0.0
ALLOWED_ORIGINS=http://localhost:3000

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

> Note: For Supabase, the `DATABASE_URL` should point at the Supabase Postgres instance with pgvector enabled.

### Backend Setup (FastAPI)

1. **Install dependencies**

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows

   pip install -r requirements.txt
   ```

2. **Enable pgvector and migrate**

   Ensure the pgvector extension is installed and enabled:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

   Then run migrations (via Alembic or your chosen tool):

   ```bash
   alembic upgrade head
   ```

3. **Run the backend**

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   - FastAPI docs should be available at `http://localhost:8000/docs`.

### Frontend Setup (Next.js)

1. **Install dependencies**

   ```bash
   cd apps/web
   pnpm -w install
   ```

2. **Configure environment**

   ```bash
   cp apps/web/.env.example apps/web/.env.local
   ```

   - Ensure `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local` points to your running backend (e.g. `http://127.0.0.1:8000`).

3. **Run the dev server**

   ```bash
   pnpm -w dev
   ```

   - Next.js app should be available at `http://localhost:3000`.

The typical workflow in development is:

1. Start Postgres (local or Supabase).
2. Start FastAPI backend (port 8000).
3. Start Next.js frontend (port 3000).
4. Upload PDFs and experiment with ingestion, extraction, and RAG flows from the UI or via API clients.

---

## Design Decisions

### Why pgvector

- **Native to PostgreSQL**: pgvector keeps embeddings and metadata in a single system of record, simplifying deployment and operational overhead.
- **Reasonable performance**: For many production workloads, pgvector provides strong performance characteristics without needing a separate vector database.
- **Transactional consistency**: Vector data and structured metadata (documents, pages, extractions) live in the same transactional boundary, which simplifies updates, deletes, and permission models.

### Why Schema Enforcement

- **Reliability of LLM outputs**: Free-form LLM responses are hard to trust in production. Enforcing a JSON schema (e.g. via Pydantic + JSON mode / function calling) makes outputs predictable and parseable.
- **Validation & monitoring**: Once a schema is defined, standard validation techniques can be used to enforce required fields, ranges, and formats, which is critical for business-facing structured data (e.g. invoices).
- **Downstream integration**: Many consuming systems expect strict data contracts. Schema enforcement at the LLM boundary ensures compatibility with downstream services and analytics.

### Why FastAPI

- **Async-first design**: FastAPI’s async support fits well with I/O-heavy AI workloads (database calls, external APIs like OpenAI).
- **Type-driven development**: Automatic OpenAPI generation and Pydantic-based models make APIs self-documenting and strongly typed.
- **Performance and ergonomics**: It offers good performance with an ergonomic developer experience well-suited to modern Python backends.

---

## Future Improvements

- **Background workers / queueing**: Move heavy operations (embedding, large-batch extraction) to dedicated worker processes using Celery, RQ, or a similar system.
- **More retrieval strategies**: Experiment with hybrid search (BM25 + vectors), re-ranking models, and adaptive context windows.
- **Multi-tenant architecture**: Add robust auth, per-tenant namespaces, and row-level security for real-world multi-team deployments.
- **Observability and metrics**: Integrate tracing, metrics, and structured logs around LLM calls, retrieval quality, and validation failures.
- **Model abstraction layer**: Add a generic model provider interface to swap between OpenAI and other LLM / embedding providers as needed.

---

## License

This project is licensed under the **MIT License**. See the `LICENSE` file for details.
