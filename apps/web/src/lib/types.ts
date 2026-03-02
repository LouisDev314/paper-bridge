export interface HealthResponse {
  status: string;
}

export interface DocumentResponse {
  id: string;
  filename: string;
  checksum_sha256: string;
  version: number;
  total_pages: number;
  created_at: string;
  pipeline_job_id?: string | null;
}

export interface JobResponse {
  id: string;
  document_id: string;
  task_type: string;
  status: string;
  error_message: string | null;
  task_metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  page_start: number;
  page_end: number;
  pdf_page_start: number;
  pdf_page_end: number;
  text: string;
  similarity_score?: number | null;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
}

export interface ReviewEditResponse {
  id: string;
  extraction_id: string;
  original_data: Record<string, unknown>;
  updated_data: Record<string, unknown>;
  edited_by: string | null;
  created_at: string;
}
