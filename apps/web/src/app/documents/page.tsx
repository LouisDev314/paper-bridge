"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmModal } from "@/components/confirm-modal";
import { useJobs } from "@/components/providers/job-provider";
import { deleteDocument, listDocuments, triggerEmbed, triggerExtract } from "@/lib/api";
import type { DocumentResponse } from "@/lib/types";

const PAGE_SIZE = 12;

type TaskType = "extract" | "embed";

export default function DocumentsPage() {
  const { registerJob } = useJobs();
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningAction, setRunningAction] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<DocumentResponse | null>(null);
  const [deleting, setDeleting] = useState(false);

  const canPrev = skip > 0;
  const canNext = documents.length === PAGE_SIZE;

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await listDocuments(skip, PAGE_SIZE);
      setDocuments(docs);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [skip]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  async function queueTask(documentId: string, task: TaskType) {
    setError(null);
    const key = `${documentId}:${task}`;
    setRunningAction(key);

    try {
      const job = task === "extract" ? await triggerExtract(documentId) : await triggerEmbed(documentId);
      registerJob(job);
      await loadDocuments();
    } catch (taskError) {
      setError(taskError instanceof Error ? taskError.message : `Failed to queue ${task} job.`);
    } finally {
      setRunningAction(null);
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
      await loadDocuments();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Failed to delete document.");
    } finally {
      setDeleting(false);
    }
  }

  const pageLabel = useMemo(() => {
    const pageNumber = Math.floor(skip / PAGE_SIZE) + 1;
    return `Page ${pageNumber}`;
  }, [skip]);

  return (
    <section className="page-grid">
      <div className="panel">
        <div className="inline-row spread">
          <h1>Documents</h1>
          <button type="button" className="secondary-button" onClick={() => void loadDocuments()} disabled={loading}>
            Refresh
          </button>
        </div>

        <p className="muted">Browse uploaded files, queue processing jobs, and delete records.</p>

        {error ? <p className="error-text">{error}</p> : null}

        {loading ? <p className="muted">Loading documents...</p> : null}

        {!loading && documents.length === 0 ? <p className="muted">No documents found for this page.</p> : null}

        {!loading && documents.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Pages</th>
                <th>Version</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => {
                const extractKey = `${document.id}:extract`;
                const embedKey = `${document.id}:embed`;

                return (
                  <tr key={document.id}>
                    <td>
                      <Link href={`/documents/${document.id}`}>{document.filename}</Link>
                    </td>
                    <td>{document.total_pages}</td>
                    <td>{document.version}</td>
                    <td>{new Date(document.created_at).toLocaleString()}</td>
                    <td>
                      <div className="button-row wrap">
                        <button
                          type="button"
                          className="small-button"
                          onClick={() => void queueTask(document.id, "extract")}
                          disabled={runningAction === extractKey}
                        >
                          {runningAction === extractKey ? "Queuing..." : "Extract"}
                        </button>
                        <button
                          type="button"
                          className="small-button"
                          onClick={() => void queueTask(document.id, "embed")}
                          disabled={runningAction === embedKey}
                        >
                          {runningAction === embedKey ? "Queuing..." : "Embed"}
                        </button>
                        <button type="button" className="danger-button" onClick={() => setDeleteCandidate(document)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}

        <div className="inline-row spread top-gap">
          <button
            type="button"
            className="secondary-button"
            disabled={!canPrev || loading}
            onClick={() => setSkip((current) => Math.max(current - PAGE_SIZE, 0))}
          >
            Previous
          </button>
          <span className="muted">{pageLabel}</span>
          <button
            type="button"
            className="secondary-button"
            disabled={!canNext || loading}
            onClick={() => setSkip((current) => current + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </div>

      <ConfirmModal
        open={Boolean(deleteCandidate)}
        title="Delete document"
        message={
          deleteCandidate
            ? `Delete '${deleteCandidate.filename}' and all related pages/jobs/extractions/embeddings?`
            : ""
        }
        busy={deleting}
        onCancel={() => setDeleteCandidate(null)}
        onConfirm={() => void confirmDelete()}
      />
    </section>
  );
}
