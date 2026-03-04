"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import React, { FormEvent, useCallback, useMemo, useState } from "react";

import { CitationList } from "@/components/citation-list";
import { askQuestion, listDocuments } from "@/lib/api";
import type { AskResponse, DocumentResponse } from "@/lib/types";

function statusClass(status: DocumentResponse["status"]): string {
  if (status === "ready") return "status status-ok";
  if (status === "failed") return "status status-bad";
  if (status === "processing") return "status status-neutral";
  return "status status-neutral";
}

function AskPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [question, setQuestion] = useState("");
  const [copiedAnswer, setCopiedAnswer] = useState(false);
  const [copiedMarkdown, setCopiedMarkdown] = useState(false);
  const selectedDocumentIds = useMemo(() => {
    const docIdsParam = searchParams.get("docIds");
    if (!docIdsParam) {
      return [];
    }
    return docIdsParam.split(",").filter(Boolean);
  }, [searchParams]);

  const updateUrlParams = useCallback((newIds: string[]) => {
    const params = new URLSearchParams(searchParams.toString());
    if (newIds.length > 0) {
      params.set("docIds", newIds.join(","));
    } else {
      params.delete("docIds");
    }
    router.replace(`?${params.toString()}`);
  }, [router, searchParams]);

  const { data: documents = [], isLoading: loadingDocs } = useQuery({
    queryKey: ["documents"],
    queryFn: () => listDocuments(0, 200),
  });

  const readyDocumentIds = useMemo(
    () => new Set(documents.filter((document) => document.status === "ready").map((document) => document.id)),
    [documents],
  );
  const selectableDocumentIds = useMemo(
    () => selectedDocumentIds.filter((documentId) => readyDocumentIds.has(documentId)),
    [readyDocumentIds, selectedDocumentIds],
  );

  const {
    mutate: submitQuestion,
    data: result,
    isPending: asking,
    error,
  } = useMutation<AskResponse, Error, void>({
    mutationFn: async () => askQuestion(question, selectableDocumentIds),
  });

  function toggleDocument(documentId: string) {
    if (!readyDocumentIds.has(documentId)) {
      return;
    }
    const newIds = selectableDocumentIds.includes(documentId)
      ? selectableDocumentIds.filter((id) => id !== documentId)
      : [...selectableDocumentIds, documentId];
    updateUrlParams(newIds);
  }

  function toggleAllDocuments(checked: boolean) {
    if (checked) {
      updateUrlParams([]);
    }
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCopiedAnswer(false);
    setCopiedMarkdown(false);
    submitQuestion();
  }

  async function copyAnswer() {
    if (!result) return;
    await navigator.clipboard.writeText(result.answer);
    setCopiedAnswer(true);
    setTimeout(() => setCopiedAnswer(false), 2000);
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <h1>Ask</h1>
        <p className="muted">Ask across all ready documents or choose specific ready documents.</p>

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
            className="w-full p-2 border rounded"
          />

          <button type="submit" className="primary-button top-gap w-fit" disabled={asking}>
            {asking ? 'Asking...' : 'Ask'}
          </button>
        </form>

        {error ? <p className="error-text top-gap">{error.message}</p> : null}
      </div>

      <div className="panel">
        <div className="inline-row spread border-b pb-4 mb-4">
          <h2>Document scope</h2>
          <span className="bg-slate-100 px-3 py-1 rounded-full text-sm font-medium">
            {selectableDocumentIds.length === 0 ? 'All ready documents' : `${selectableDocumentIds.length} selected`}
          </span>
        </div>

        <label className="flex items-start gap-3 p-3 bg-slate-50 border rounded-lg mb-4 cursor-pointer hover:bg-slate-100 transition-colors">
          <input
            type="checkbox"
            checked={selectableDocumentIds.length === 0}
            onChange={(event) => toggleAllDocuments(event.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600"
          />
          <span className="font-medium text-slate-900">All ready documents</span>
        </label>

        {loadingDocs ? <p className="text-slate-500 animate-pulse">Loading documents...</p> : null}

        {!loadingDocs && documents.length === 0 ? <p className="text-slate-500">No documents available.</p> : null}

        {!loadingDocs && documents.length > 0 ? (
          <ul className="space-y-2 max-h-[400px] overflow-y-auto pr-2 list-none">
            {documents.map((document) => {
              const ready = document.status === 'ready';
              const createdDate = new Date(document.created_at).toLocaleString();
              return (
                <li key={document.id}>
                  <label
                    className={[
                      'flex inline-row items-start gap-3 p-3 border rounded-lg transition-colors select-none',
                      ready
                        ? 'cursor-pointer hover:bg-slate-50'
                        : 'cursor-not-allowed bg-slate-50 opacity-70 pointer-events-none',
                    ].join(' ')}>
                    <input
                      type="checkbox"
                      checked={selectableDocumentIds.includes(document.id)}
                      onChange={() => toggleDocument(document.id)}
                      disabled={!ready}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600"
                    />
                    <p className="m-0 font-medium leading-snug text-slate-900 break-words">{document.filename}</p>
                    <p className="m-0 mt-1 text-xs text-slate-500">
                      Version {document.version} (created {createdDate})
                    </p>
                    {!ready ? (
                      <span className="mt-1 inline-block text-xs text-slate-500">Not selectable until ready.</span>
                    ) : null}
                    <span className={`${statusClass(document.status)} self-start`}>{document.status}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      {result ? (
        <div className="panel md:col-span-2">
          <div className="flex items-center justify-between border-b pb-4 mb-4">
            <h2>Answer</h2>
              <button
                type="button"
                onClick={copyAnswer}
                className="px-3 py-1.5 text-sm rounded bg-slate-100 hover:bg-slate-200 transition-colors">
                {copiedAnswer ? 'Copied!' : 'Copy Answer'}
              </button>
          </div>
          <div className="prose max-w-none text-slate-800 leading-relaxed whitespace-pre-wrap">{result.answer}</div>

          <div className="mt-8 pt-6 border-t">
            <h3 className="mb-4 text-lg font-semibold text-slate-900">Sources ({result.citations.length})</h3>
            <CitationList citations={result.citations} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function AskPage() {
  return (
    <React.Suspense fallback={<p className="muted p-8">Loading tools...</p>}>
      <AskPageContent />
    </React.Suspense>
  );
}
