-- Enable pgvector
create extension if not exists vector;

-- Documents
create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  filename text not null,
  content_type text not null,
  file_size_bytes bigint not null,
  storage_bucket text not null default 'paperbridge-documents',
  storage_key text not null, -- where original PDF is stored
  created_at timestamptz not null default now()
);

-- Jobs (status machine for reproducibility)
create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  job_type text not null, -- ingest|extract|embed|qa
  status text not null,   -- queued|processing|needs_review|done|failed
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

-- Pages (store per-page text, plus optional page image object key)
create table if not exists document_pages (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  page_number int not null,
  text text,
  text_quality_score float not null default 0,
  page_image_key text, -- optional: stored in Supabase Storage
  created_at timestamptz not null default now(),
  unique (document_id, page_number)
);

-- Extractions (store structured results + validation + provenance)
create table if not exists extractions (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references jobs(id) on delete cascade,
  schema_name text not null, -- invoice|spec_summary
  result_json jsonb not null,
  confidence_json jsonb,
  validation_errors jsonb,
  anomaly_flags jsonb,
  provenance_json jsonb,
  created_at timestamptz not null default now()
);

-- Review edits (human-in-the-loop)
create table if not exists review_edits (
  id uuid primary key default gen_random_uuid(),
  extraction_id uuid not null references extractions(id) on delete cascade,
  edited_json jsonb not null,
  edited_by text,
  created_at timestamptz not null default now()
);

-- Embeddings (chunk storage for RAG)
create table if not exists embeddings (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  chunk_id text not null,
  page_start int,
  page_end int,
  content text not null,
  embedding vector(1536), -- text-embedding-3-small
  created_at timestamptz not null default now()
);

-- Index for vector search
create index if not exists embeddings_vector_idx
on embeddings using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

-- Helpful query indexes
create index if not exists jobs_document_idx on jobs(document_id, created_at desc);
create index if not exists pages_document_idx on document_pages(document_id, page_number);
create index if not exists embeddings_document_idx on embeddings(document_id);