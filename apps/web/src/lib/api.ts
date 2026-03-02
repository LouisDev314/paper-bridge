import type { AskResponse, DocumentResponse, HealthResponse, JobResponse, ReviewEditResponse } from "@/lib/types";

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

  if (typeof payload === "object") {
    const asRecord = payload as Record<string, unknown>;
    if (typeof asRecord.detail === "string") {
      return asRecord.detail;
    }

    const error = asRecord.error;
    if (error && typeof error === "object" && typeof (error as Record<string, unknown>).message === "string") {
      return (error as Record<string, string>).message;
    }
  }

  return fallback;
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(buildApiPath(path), {
    ...init,
    cache: "no-store",
  });

  const payload = await parsePayload(response);

  if (!response.ok) {
    const fallback = `Request failed (${response.status})`;
    throw new Error(extractErrorMessage(payload, fallback));
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
  return apiRequest<HealthResponse>("/health");
}

export async function listDocuments(skip = 0, limit = 20): Promise<DocumentResponse[]> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  return apiRequest<DocumentResponse[]>(`/documents?${params.toString()}`);
}

export async function getDocument(documentId: string): Promise<DocumentResponse> {
  return apiRequest<DocumentResponse>(`/documents/${encodeURIComponent(documentId)}`);
}

export async function uploadDocument(file: File, dedupe = true, autoProcess = false): Promise<DocumentResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const params = new URLSearchParams({ dedupe: String(dedupe), auto_process: String(autoProcess) });
  return apiRequest<DocumentResponse>(`/documents?${params.toString()}`, {
    method: "POST",
    body: formData,
  });
}

export async function uploadDocumentsBatch(
  files: File[],
  dedupe = true,
  autoProcess = false,
): Promise<DocumentResponse[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const params = new URLSearchParams({ dedupe: String(dedupe), auto_process: String(autoProcess) });
  return apiRequest<DocumentResponse[]>(`/documents/batch?${params.toString()}`, {
    method: "POST",
    body: formData,
  });
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiRequest<void>(`/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  });
}

export async function triggerExtract(documentId: string): Promise<JobResponse> {
  return apiRequest<JobResponse>(`/documents/${encodeURIComponent(documentId)}/extract`, {
    method: "POST",
  });
}

export async function triggerEmbed(documentId: string): Promise<JobResponse> {
  return apiRequest<JobResponse>(`/documents/${encodeURIComponent(documentId)}/embed`, {
    method: "POST",
  });
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return apiRequest<JobResponse>(`/jobs/${encodeURIComponent(jobId)}`);
}

export async function askQuestion(question: string, docIds?: string[], topK?: number): Promise<AskResponse> {
  const body: JsonBody = {
    question,
  };

  if (docIds && docIds.length > 0) {
    body.doc_ids = docIds;
  }

  if (typeof topK === "number" && Number.isFinite(topK)) {
    body.top_k = topK;
  }

  return apiRequest<AskResponse>("/ask", jsonInit("POST", body));
}

export async function submitExtractionReview(
  extractionId: string,
  updatedData: Record<string, unknown>,
  editedBy?: string,
): Promise<ReviewEditResponse> {
  return apiRequest<ReviewEditResponse>(`/extractions/${encodeURIComponent(extractionId)}/review`, {
    ...jsonInit("POST", {
      updated_data: updatedData,
      edited_by: editedBy ?? null,
    }),
  });
}

export function getExportUrl(documentId: string, format: "json" | "csv"): string {
  return buildApiPath(`/documents/${encodeURIComponent(documentId)}/export.${format}`);
}
