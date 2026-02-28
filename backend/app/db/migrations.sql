-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR NOT NULL,
    storage_key VARCHAR NOT NULL,
    total_pages INTEGER DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    task_type VARCHAR NOT NULL,
    status VARCHAR DEFAULT 'queued',
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT,
    text_quality_score FLOAT,
    page_image_key VARCHAR
);

CREATE TABLE IF NOT EXISTS extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    data JSONB NOT NULL,
    status VARCHAR DEFAULT 'PASSED',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_edits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
    original_data JSONB NOT NULL,
    updated_data JSONB NOT NULL,
    edited_by VARCHAR,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE review_edits ADD COLUMN IF NOT EXISTS edited_by VARCHAR;

CREATE TABLE IF NOT EXISTS embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id VARCHAR NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_jobs_document_id_status ON jobs (document_id, status);
CREATE INDEX IF NOT EXISTS ix_document_pages_document_id_page ON document_pages (document_id, page_number);
CREATE INDEX IF NOT EXISTS ix_extractions_document_id ON extractions (document_id);
CREATE INDEX IF NOT EXISTS ix_embeddings_document_id ON embeddings (document_id);
CREATE INDEX IF NOT EXISTS ix_embeddings_document_chunk ON embeddings (document_id, chunk_id);

-- IVFFlat index for cosine distance. This requires some data to be perfectly optimal, but we will create it here.
CREATE INDEX IF NOT EXISTS ix_embeddings_embedding ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
