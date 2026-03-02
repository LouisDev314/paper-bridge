import { z } from "zod";

export const HealthResponseSchema = z.object({
  status: z.string(),
});
export type HealthResponse = z.infer<typeof HealthResponseSchema>;

export const DocumentResponseSchema = z.object({
  id: z.string(),
  filename: z.string(),
  checksum_sha256: z.string(),
  version: z.number(),
  total_pages: z.number(),
  created_at: z.string(),
  pipeline_job_id: z.string().nullish(),
});
export type DocumentResponse = z.infer<typeof DocumentResponseSchema>;

export const UploadDocumentResponseSchema = DocumentResponseSchema;
export type UploadDocumentResponse = DocumentResponse;

export const JobResponseSchema = z.object({
  id: z.string(),
  document_id: z.string(),
  task_type: z.string(),
  status: z.string(),
  error_message: z.string().nullish(),
  task_metadata: z.record(z.string(), z.unknown()).nullish(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type JobResponse = z.infer<typeof JobResponseSchema>;

export const CitationSchema = z.object({
  chunk_id: z.string(),
  document_id: z.string(),
  page_start: z.number(),
  page_end: z.number(),
  pdf_page_start: z.number(),
  pdf_page_end: z.number(),
  text: z.string(),
  similarity_score: z.number().nullish(),
});
export type Citation = z.infer<typeof CitationSchema>;

export const AskResponseSchema = z.object({
  answer: z.string(),
  citations: z.array(CitationSchema),
});
export type AskResponse = z.infer<typeof AskResponseSchema>;

export const ReviewEditResponseSchema = z.object({
  id: z.string(),
  extraction_id: z.string(),
  original_data: z.record(z.string(), z.unknown()),
  updated_data: z.record(z.string(), z.unknown()),
  edited_by: z.string().nullish(),
  created_at: z.string(),
});
export type ReviewEditResponse = z.infer<typeof ReviewEditResponseSchema>;

export const ErrorResponseSchema = z.object({
  detail: z.string().optional(),
  error: z.object({ message: z.string() }).optional(),
  code: z.string().optional(),
  message: z.string().optional(),
  request_id: z.string().optional(),
});
export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;
