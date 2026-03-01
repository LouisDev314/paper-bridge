-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Core tables
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR NOT NULL,
    storage_key VARCHAR NOT NULL,
    checksum_sha256 VARCHAR(64),
    version INTEGER DEFAULT 1,
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

CREATE TABLE IF NOT EXISTS embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id VARCHAR NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    pdf_page_start INTEGER,
    pdf_page_end INTEGER,
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL
);

-- Backfills / compatibility for existing deployments
ALTER TABLE review_edits ADD COLUMN IF NOT EXISTS edited_by VARCHAR;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS checksum_sha256 VARCHAR(64);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;
UPDATE documents
SET checksum_sha256 = encode(digest(COALESCE(storage_key, ''), 'sha256'), 'hex')
WHERE checksum_sha256 IS NULL;
UPDATE documents SET version = 1 WHERE version IS NULL;
ALTER TABLE documents ALTER COLUMN checksum_sha256 SET NOT NULL;
ALTER TABLE documents ALTER COLUMN version SET NOT NULL;

ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS pdf_page_start INTEGER;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS pdf_page_end INTEGER;
UPDATE embeddings SET pdf_page_start = page_start WHERE pdf_page_start IS NULL;
UPDATE embeddings SET pdf_page_end = page_end WHERE pdf_page_end IS NULL;
ALTER TABLE embeddings ALTER COLUMN pdf_page_start SET NOT NULL;
ALTER TABLE embeddings ALTER COLUMN pdf_page_end SET NOT NULL;

-- Indexes and constraints
CREATE INDEX IF NOT EXISTS ix_jobs_document_id_status ON jobs (document_id, status);
CREATE INDEX IF NOT EXISTS ix_document_pages_document_id_page ON document_pages (document_id, page_number);
CREATE INDEX IF NOT EXISTS ix_extractions_document_id ON extractions (document_id);
CREATE INDEX IF NOT EXISTS ix_embeddings_document_id ON embeddings (document_id);
CREATE INDEX IF NOT EXISTS ix_embeddings_document_chunk ON embeddings (document_id, chunk_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_storage_key ON documents (storage_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_checksum_version ON documents (checksum_sha256, version);
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_pages_document_page ON document_pages (document_id, page_number);
CREATE UNIQUE INDEX IF NOT EXISTS uq_embeddings_document_chunk ON embeddings (document_id, chunk_id);

CREATE INDEX IF NOT EXISTS ix_documents_checksum ON documents (checksum_sha256);

CREATE INDEX IF NOT EXISTS ix_embeddings_embedding
    ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

DO $$
BEGIN
    CREATE INDEX IF NOT EXISTS ix_embeddings_embedding_hnsw
        ON embeddings USING hnsw (embedding vector_cosine_ops);
EXCEPTION
    WHEN OTHERS THEN
        -- hnsw may be unavailable or exceed maintenance_work_mem; ivfflat remains active.
        NULL;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_task
ON jobs (document_id, task_type)
WHERE status IN ('queued', 'processing');
