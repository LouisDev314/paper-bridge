"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { JobList } from "@/components/job-list";
import { useJobs } from "@/components/providers/job-provider";
import { getHealth, listDocuments, triggerEmbed, triggerExtract, uploadDocument } from "@/lib/api";
import type { DocumentResponse } from "@/lib/types";

const RECENT_LIMIT = 8;

type TaskType = "extract" | "embed";

export default function DashboardPage() {
  const { jobs, registerJob } = useJobs();
  const [health, setHealth] = useState<string>("checking");
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dedupe, setDedupe] = useState(true);
  const [runningAction, setRunningAction] = useState<string | null>(null);

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
      for (const file of Array.from(files)) {
        await uploadDocument(file, dedupe);
      }
      form.reset();
      setDedupe(true);
      await refresh();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function queueTask(documentId: string, task: TaskType) {
    setError(null);
    const actionKey = `${documentId}:${task}`;
    setRunningAction(actionKey);

    try {
      const job = task === "extract" ? await triggerExtract(documentId) : await triggerEmbed(documentId);
      registerJob(job);
      await refresh();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : `Failed to queue ${task} job.`);
    } finally {
      setRunningAction(null);
    }
  }

  const healthClass = health === "ok" ? "status status-ok" : health === "checking" ? "status status-neutral" : "status status-bad";

  return (
    <section className="page-grid">
      <div className="panel">
        <h1>Dashboard</h1>
        <p className="muted">Upload PDFs, queue extract/embed jobs, and monitor the backend.</p>

        <div className="inline-row">
          <span>API health</span>
          <span className={healthClass}>{health}</span>
        </div>

        <form className="form-stack" onSubmit={handleUpload}>
          <label className="form-label" htmlFor="pdfs">
            Upload PDFs
          </label>
          <input id="pdfs" name="pdfs" type="file" accept="application/pdf" multiple />

          <label className="inline-row">
            <input
              type="checkbox"
              checked={dedupe}
              onChange={(event) => setDedupe(event.currentTarget.checked)}
            />
            <span>Enable checksum dedupe</span>
          </label>

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
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}
      </div>

      <div className="panel">
        <h2>Recent jobs</h2>
        <JobList jobs={recentJobs} emptyMessage="No jobs have been queued from this browser yet." />
      </div>
    </section>
  );
}
