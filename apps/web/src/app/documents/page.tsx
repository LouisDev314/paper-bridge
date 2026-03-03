"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmModal } from "@/components/confirm-modal";
import { deleteDocument, getDocumentDownload, listDocuments } from "@/lib/api";
import type { DocumentResponse } from "@/lib/types";

const PAGE_SIZE = 12;

function statusClass(status: DocumentResponse["status"]): string {
  if (status === "ready") return "status status-ok";
  if (status === "failed") return "status status-bad";
  if (status === "processing") return "status status-neutral";
  return "status status-neutral";
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<DocumentResponse | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

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

  async function downloadDocumentFile(document: DocumentResponse) {
    setError(null);
    setDownloadingId(document.id);
    try {
      const { url } = await getDocumentDownload(document.id);
      window.location.assign(url);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "Failed to download document.");
    } finally {
      setDownloadingId(null);
    }
  }

  const pageLabel = useMemo(() => {
    const pageNumber = Math.floor(skip / PAGE_SIZE) + 1;
    return `Page ${pageNumber}`;
  }, [skip]);

  const filteredDocuments = useMemo(() => {
    if (!searchQuery.trim()) return documents;
    const lowerQuery = searchQuery.toLowerCase();
    return documents.filter((doc) => doc.filename.toLowerCase().includes(lowerQuery));
  }, [documents, searchQuery]);

  const canPrev = skip > 0;
  const canNext = documents.length === PAGE_SIZE;

  return (
    <section className="page-grid">
      <div className="panel">
        <div className="inline-row spread">
          <h1>Documents</h1>
          <button type="button" className="secondary-button" onClick={() => void loadDocuments()} disabled={loading}>
            Refresh
          </button>
        </div>

        <p className="muted">Browse uploaded files, track readiness, and delete records.</p>

        <div className="top-gap">
          <input
            type="search"
            placeholder="Search by filename..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.currentTarget.value)}
            className="w-full flex-1 max-w-sm"
          />
        </div>

        {error ? <p className="error-text top-gap">{error}</p> : null}

        {loading ? <p className="muted top-gap">Loading documents...</p> : null}

        {!loading && filteredDocuments.length === 0 ? <p className="muted top-gap">No documents found.</p> : null}

        {!loading && filteredDocuments.length > 0 ? (
          <table className="data-table top-gap full-width">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Pages</th>
                <th>Version</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredDocuments.map((document) => (
                <tr key={document.id}>
                  <td>
                    <Link href={`/documents/${document.id}`}>{document.filename}</Link>
                  </td>
                  <td>{document.total_pages}</td>
                  <td>{document.version}</td>
                  <td>
                    <span className={statusClass(document.status)}>{document.status}</span>
                  </td>
                  <td>{new Date(document.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="button-row wrap">
                      <button
                        type="button"
                        className="secondary-button small-button"
                        onClick={() => void downloadDocumentFile(document)}
                        disabled={downloadingId === document.id}
                      >
                        Download
                      </button>
                      <button
                        type="button"
                        className="danger-button small-button"
                        onClick={() => setDeleteCandidate(document)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
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
        message={deleteCandidate ? `Delete '${deleteCandidate.filename}' and all related records?` : ""}
        busy={deleting}
        onCancel={() => setDeleteCandidate(null)}
        onConfirm={() => void confirmDelete()}
      />
    </section>
  );
}
