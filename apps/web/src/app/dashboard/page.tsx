"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmModal } from "@/components/confirm-modal";
import { JobList } from "@/components/job-list";
import { useJobs } from "@/components/providers/job-provider";
import { deleteDocument, getHealth, getJob, listDocuments, uploadDocumentsBatch } from "@/lib/api";
import type { DocumentResponse } from "@/lib/types";

const RECENT_LIMIT = 8;

function statusClass(status: DocumentResponse["status"]): string {
  if (status === "ready") return "status status-ok";
  if (status === "failed") return "status status-bad";
  if (status === "processing") return "status status-neutral";
  return "status status-neutral";
}

export default function DashboardPage() {
  const router = useRouter();
  const { jobs, registerJob } = useJobs();
  const [health, setHealth] = useState<string>("checking");
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const [deleteCandidate, setDeleteCandidate] = useState<DocumentResponse | null>(null);
  const [deleting, setDeleting] = useState(false);

  const recentJobs = useMemo(() => jobs.slice(0, 8), [jobs]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [healthResponse, docs] = await Promise.all([getHealth(), listDocuments(0, RECENT_LIMIT)]);
      setHealth(healthResponse.status || "unknown");
      setDocuments(docs);
    } catch (refreshError) {
      setHealth("down");
      setError(refreshError instanceof Error ? refreshError.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("pdfs") as HTMLInputElement | null;
    const files = fileInput?.files;

    if (!files || files.length === 0) {
      setError("Select at least one PDF to upload.");
      return;
    }

    try {
      setUploading(true);
      const responses = await uploadDocumentsBatch(Array.from(files));

      const batchItems = responses
        .filter((response) => response.pipeline_job_id)
        .map((response) => ({
          docId: response.id,
          jobId: response.pipeline_job_id as string,
          filename: response.filename,
        }));

      await Promise.all(
        batchItems.map(async (item) => {
          try {
            const job = await getJob(item.jobId);
            registerJob(job);
          } catch {
            // Ignore transient poll errors; processing page handles polling retries.
          }
        }),
      );

      form.reset();

      if (batchItems.length > 0) {
        sessionStorage.setItem("processing_batch", JSON.stringify(batchItems));
        router.push("/processing");
      } else {
        await refresh();
      }
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function confirmDelete() {
    if (!deleteCandidate) {
      return;
    }

    setDeleting(true);
    setError(null);

    try {
      await deleteDocument(deleteCandidate.id);
      setDeleteCandidate(null);
      await refresh();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Failed to delete document.");
    } finally {
      setDeleting(false);
    }
  }

  const healthClass =
    health === "ok" ? "status status-ok" : health === "checking" ? "status status-neutral" : "status status-bad";

  return (
    <section className="page-grid">
      <div className="panel">
        <h1>Dashboard</h1>
        <p className="muted">Upload PDFs and monitor processing to readiness for Ask.</p>

        <div className="inline-row">
          <span>Server health</span>
          <span className={healthClass}>{health}</span>
        </div>

        <form className="form-stack" onSubmit={handleUpload}>
          <label className="form-label" htmlFor="pdfs">
            Upload PDFs (Batch)
          </label>
          <input
            id="pdfs"
            name="pdfs"
            type="file"
            accept="application/pdf"
            multiple
            className="border border-dashed p-4 text-center cursor-pointer"
          />

          <div className="button-row">
            <button className="primary-button" type="submit" disabled={uploading}>
              {uploading ? "Uploading..." : "Upload"}
            </button>
            <button className="secondary-button" type="button" onClick={() => void refresh()} disabled={loading}>
              Refresh
            </button>
          </div>
        </form>

        {error ? <p className="error-text">{error}</p> : null}
      </div>

      <div className="panel">
        <div className="inline-row spread">
          <h2>Recent documents</h2>
          <Link href="/documents" className="link-button">
            View all
          </Link>
        </div>

        {loading ? <p className="muted">Loading documents...</p> : null}

        {!loading && documents.length === 0 ? <p className="muted">No uploaded documents yet.</p> : null}

        {!loading && documents.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Pages</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id}>
                  <td>
                    <Link href={`/documents/${document.id}`}>{document.filename}</Link>
                  </td>
                  <td>{document.total_pages}</td>
                  <td>
                    <span className={statusClass(document.status)}>{document.status}</span>
                  </td>
                  <td>{new Date(document.created_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      type="button"
                      className="danger-button small-button"
                      onClick={() => setDeleteCandidate(document)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>

      <div className="panel">
        <h2>Recent jobs</h2>
        <JobList jobs={recentJobs} emptyMessage="No jobs have been queued from this browser yet." />
      </div>

      <ConfirmModal
        open={Boolean(deleteCandidate)}
        title="Delete document"
        message={deleteCandidate ? `Delete '${deleteCandidate.filename}' and all related records?` : ""}
        busy={deleting}
        onCancel={() => setDeleteCandidate(null)}
        onConfirm={() => void confirmDelete()}
      />
    </section>
  );
}
