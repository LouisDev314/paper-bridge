"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { CitationList } from "@/components/citation-list";
import { JobList } from "@/components/job-list";
import { useJobs } from "@/components/providers/job-provider";
import { askQuestion, getDocument, getDocumentDownload } from "@/lib/api";
import type { AskResponse, DocumentResponse } from "@/lib/types";

type TabKey = "ask" | "jobs";

function statusClass(status: DocumentResponse["status"]): string {
  if (status === "ready") return "status status-ok";
  if (status === "failed") return "status status-bad";
  if (status === "processing") return "status status-neutral";
  return "status status-neutral";
}

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const documentId = Array.isArray(params.id) ? params.id[0] : params.id;

  const { jobsForDocument } = useJobs();
  const [documentRecord, setDocumentRecord] = useState<DocumentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<TabKey>("ask");
  const [question, setQuestion] = useState("");
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [asking, setAsking] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const documentJobs = useMemo(() => jobsForDocument(documentId), [documentId, jobsForDocument]);

  const refreshDocument = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const doc = await getDocument(documentId);
      setDocumentRecord(doc);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load document.");
      setDocumentRecord(null);
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void refreshDocument();
  }, [refreshDocument]);

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!documentRecord || documentRecord.status !== "ready") {
      return;
    }

    setAsking(true);
    setError(null);

    try {
      const response = await askQuestion(question, [documentId]);
      setAskResult(response);
      setActiveTab("ask");
    } catch (askError) {
      setError(askError instanceof Error ? askError.message : "Failed to submit question.");
      setAskResult(null);
    } finally {
      setAsking(false);
    }
  }

  const canAsk = documentRecord?.status === "ready";

  async function handleDownload() {
    if (!documentRecord || downloading) {
      return;
    }
    setError(null);
    setDownloading(true);
    try {
      const { url } = await getDocumentDownload(documentRecord.id);
      window.location.assign(url);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "Failed to download document.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="page-grid">
      <div className="panel">
        {loading ? <p className="muted">Loading document...</p> : null}

        {!loading && !documentRecord ? <p className="error-text">Document not found.</p> : null}

        {!loading && documentRecord ? (
          <>
            <div className="inline-row spread">
              <h1 className="m-0 break-words">{documentRecord.filename}</h1>
              <button type="button" className="secondary-button" onClick={() => void refreshDocument()}>
                Refresh
              </button>
            </div>

            <div className="muted flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <p>Pages: {documentRecord.total_pages}</p>
              <p>Version: {documentRecord.version}</p>
              <p>Created at: {new Date(documentRecord.created_at).toLocaleString()}</p>
            </div>
            <p className="top-gap m-0">
              <span className={statusClass(documentRecord.status)}>{documentRecord.status}</span>
            </p>

            <div className="button-row wrap top-gap">
              <button type="button" className="link-button" onClick={() => void handleDownload()} disabled={downloading}>
                Download
              </button>
            </div>
          </>
        ) : null}

        {error ? <p className="error-text">{error}</p> : null}
      </div>

      <div className="panel">
        <div className="button-row">
          <button
            type="button"
            className={activeTab === "ask" ? "primary-button" : "secondary-button"}
            onClick={() => setActiveTab("ask")}
          >
            Ask (document scoped)
          </button>
          <button
            type="button"
            className={activeTab === "jobs" ? "primary-button" : "secondary-button"}
            onClick={() => setActiveTab("jobs")}
          >
            Jobs
          </button>
        </div>

        {activeTab === "ask" ? (
          <div className="top-gap">
            {!canAsk ? <p className="muted">This document is not ready yet. Wait for processing to complete.</p> : null}
            <form className="form-stack" onSubmit={handleAsk}>
              <label className="form-label" htmlFor="doc-question">
                Question
              </label>
              <textarea
                id="doc-question"
                value={question}
                onChange={(event) => setQuestion(event.currentTarget.value)}
                minLength={3}
                required
                rows={4}
                placeholder="Ask a question about this document..."
              />

              <button type="submit" className="primary-button" disabled={asking || !canAsk}>
                {asking ? "Asking..." : "Ask"}
              </button>
            </form>

            {askResult ? (
              <div className="result-card top-gap">
                <h3>Answer</h3>
                <div className="whitespace-pre-wrap">{askResult.answer}</div>
                <h3>Citations</h3>
                <CitationList citations={askResult.citations} />
              </div>
            ) : null}
          </div>
        ) : null}

        {activeTab === "jobs" ? (
          <div className="top-gap">
            <JobList jobs={documentJobs} emptyMessage="No local job history for this document yet." />
          </div>
        ) : null}
      </div>
    </section>
  );
}
