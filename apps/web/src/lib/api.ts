import { z } from "zod";

import {
  AskResponseSchema,
  DownloadDocumentResponseSchema,
  DocumentResponseSchema,
  ErrorResponseSchema,
  HealthResponseSchema,
  JobResponseSchema,
  ReviewEditResponseSchema,
  UploadDocumentResponseSchema,
  type AskResponse,
  type DownloadDocumentResponse,
  type DocumentResponse,
  type HealthResponse,
  type JobResponse,
  type ReviewEditResponse,
  type UploadDocumentResponse,
} from "@/lib/types";

const API_PREFIX = "/api/pb";

type JsonBody = Record<string, unknown>;

function buildApiPath(path: string): string {
  return `${API_PREFIX}${path.startsWith("/") ? path : `/${path}`}`;
}

async function parsePayload(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  if (contentType.startsWith("text/")) {
    return response.text();
  }
  return response.arrayBuffer();
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload) {
    return fallback;
  }

  if (typeof payload === "string") {
    return payload;
  }

  const parsed = ErrorResponseSchema.safeParse(payload);
  if (parsed.success) {
    if (parsed.data.detail) return parsed.data.detail;
    if (parsed.data.error?.message) return parsed.data.error.message;
    if (parsed.data.message) return parsed.data.message;
  }

  return fallback;
}

async function apiRequest<T>(path: string, init: RequestInit = {}, schema?: z.ZodType<T>): Promise<T> {
  const response = await fetch(buildApiPath(path), {
    ...init,
    cache: "no-store",
  });

  const payload = await parsePayload(response);

  if (!response.ok) {
    const fallback = `Request failed (${response.status})`;
    const errorMessage = extractErrorMessage(payload, fallback);

    // Attempt to parse request_id from standard error
    let requestId = "";
    if (payload && typeof payload === "object") {
      const parsed = ErrorResponseSchema.safeParse(payload);
      if (parsed.success && parsed.data.request_id) {
        requestId = ` [ReqID: ${parsed.data.request_id}]`;
      }
    }

    throw new Error(`${errorMessage}${requestId}`);
  }

  if (schema && payload !== undefined) {
    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      console.error("API response validation failed:", path, parsed.error);
      throw new Error(`Invalid API response from ${path}`);
    }
    return parsed.data;
  }

  return payload as T;
}

function jsonInit(method: string, body?: JsonBody): RequestInit {
  return {
    method,
    headers: {
      "content-type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  };
}

export async function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health", {}, HealthResponseSchema);
}

export async function listDocuments(skip = 0, limit = 20): Promise<DocumentResponse[]> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  return apiRequest<DocumentResponse[]>(`/documents?${params.toString()}`, {}, z.array(DocumentResponseSchema));
}

export async function getDocument(documentId: string): Promise<DocumentResponse> {
  return apiRequest<DocumentResponse>(`/documents/${encodeURIComponent(documentId)}`, {}, DocumentResponseSchema);
}

export async function uploadDocument(file: File): Promise<UploadDocumentResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return apiRequest<UploadDocumentResponse>(
    "/documents",
    {
      method: "POST",
      body: formData,
    },
    UploadDocumentResponseSchema,
  );
}

export async function uploadDocumentsBatch(files: File[]): Promise<UploadDocumentResponse[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return apiRequest<UploadDocumentResponse[]>(
    "/documents/batch",
    {
      method: "POST",
      body: formData,
    },
    z.array(UploadDocumentResponseSchema),
  );
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiRequest<void>(`/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  });
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return apiRequest<JobResponse>(`/jobs/${encodeURIComponent(jobId)}`, {}, JobResponseSchema);
}

export async function askQuestion(question: string, docIds?: string[]): Promise<AskResponse> {
  const body: JsonBody = {
    question,
  };

  if (docIds && docIds.length > 0) {
    body.doc_ids = docIds;
  } else if (docIds && docIds.length === 0) {
    // Specifically handle the case where we want all documents according to backend
    body.doc_ids = null;
  }

  return apiRequest<AskResponse>("/ask", jsonInit("POST", body), AskResponseSchema);
}

export async function submitExtractionReview(
  extractionId: string,
  updatedData: Record<string, unknown>,
  editedBy?: string,
): Promise<ReviewEditResponse> {
  return apiRequest<ReviewEditResponse>(
    `/extractions/${encodeURIComponent(extractionId)}/review`,
    {
      ...jsonInit("POST", {
        updated_data: updatedData,
        edited_by: editedBy ?? null,
      }),
    },
    ReviewEditResponseSchema,
  );
}

export async function getDocumentDownload(documentId: string): Promise<DownloadDocumentResponse> {
  return apiRequest<DownloadDocumentResponse>(
    `/documents/${encodeURIComponent(documentId)}/download`,
    {},
    DownloadDocumentResponseSchema,
  );
}
