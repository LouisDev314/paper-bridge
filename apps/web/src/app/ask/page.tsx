"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { CitationList } from "@/components/citation-list";
import { askQuestion, listDocuments } from "@/lib/api";
import type { AskResponse, DocumentResponse } from "@/lib/types";

export default function AskPage() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(8);
  const [asking, setAsking] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);

  useEffect(() => {
    void (async () => {
      setLoadingDocs(true);
      try {
        const docs = await listDocuments(0, 200);
        setDocuments(docs);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load documents.");
      } finally {
        setLoadingDocs(false);
      }
    })();
  }, []);

  const selectedCount = useMemo(() => selectedDocumentIds.length, [selectedDocumentIds]);

  function toggleDocument(documentId: string) {
    setSelectedDocumentIds((current) => {
      if (current.includes(documentId)) {
        return current.filter((id) => id !== documentId);
      }
      return [...current, documentId];
    });
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAsking(true);
    setError(null);

    try {
      const response = await askQuestion(
        question,
        selectedDocumentIds.length > 0 ? selectedDocumentIds : undefined,
        topK,
      );
      setResult(response);
    } catch (askError) {
      setError(askError instanceof Error ? askError.message : "Failed to submit question.");
      setResult(null);
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <h1>Ask</h1>
        <p className="muted">
          Ask across all embedded documents or select specific documents to scope retrieval.
        </p>

        <form className="form-stack" onSubmit={handleAsk}>
          <label className="form-label" htmlFor="global-question">
            Question
          </label>
          <textarea
            id="global-question"
            value={question}
            onChange={(event) => setQuestion(event.currentTarget.value)}
            minLength={3}
            required
            rows={4}
            placeholder="What do these documents say about..."
          />

          <label className="form-label" htmlFor="global-top-k">
            Top K (1-50)
          </label>
          <input
            id="global-top-k"
            type="number"
            min={1}
            max={50}
            value={topK}
            onChange={(event) => setTopK(Number(event.currentTarget.value) || 1)}
          />

          <button type="submit" className="primary-button" disabled={asking}>
            {asking ? "Asking..." : "Ask"}
          </button>
        </form>

        {error ? <p className="error-text">{error}</p> : null}
      </div>

      <div className="panel">
        <div className="inline-row spread">
          <h2>Document scope</h2>
          <span className="muted">{selectedCount} selected</span>
        </div>

        {loadingDocs ? <p className="muted">Loading documents...</p> : null}

        {!loadingDocs && documents.length === 0 ? <p className="muted">No documents available.</p> : null}

        {!loadingDocs && documents.length > 0 ? (
          <ul className="selection-list">
            {documents.map((document) => (
              <li key={document.id} className="selection-item">
                <label>
                  <input
                    type="checkbox"
                    checked={selectedDocumentIds.includes(document.id)}
                    onChange={() => toggleDocument(document.id)}
                  />
                  <span>{document.filename}</span>
                </label>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {result ? (
        <div className="panel">
          <h2>Answer</h2>
          <p>{result.answer}</p>
          <h3>Citations</h3>
          <CitationList citations={result.citations} />
        </div>
      ) : null}
    </section>
  );
}
