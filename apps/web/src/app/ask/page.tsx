"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import React, { FormEvent, useEffect, useState } from "react";

import { CitationList } from "@/components/citation-list";
import { askQuestion, listDocuments } from "@/lib/api";
import type { AskResponse } from "@/lib/types";

function AskPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(8);
  const [copiedAnswer, setCopiedAnswer] = useState(false);
  const [copiedMarkdown, setCopiedMarkdown] = useState(false);

  // Sync docIds from URL on mount
  useEffect(() => {
    const docIdsParam = searchParams.get("docIds");
    if (docIdsParam) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedDocumentIds(docIdsParam.split(",").filter(Boolean));
    }
  }, [searchParams]);

  // Update URL when selection changes
  const updateUrlParams = (newIds: string[]) => {
    const params = new URLSearchParams(searchParams.toString());
    if (newIds.length > 0) {
      params.set("docIds", newIds.join(","));
    } else {
      params.delete("docIds");
    }
    router.replace(`?${params.toString()}`);
  };

  const { data: documents = [], isLoading: loadingDocs } = useQuery({
    queryKey: ["documents"],
    queryFn: () => listDocuments(0, 200),
  });

  const {
    mutate: submitQuestion,
    data: result,
    isPending: asking,
    error,
  } = useMutation<AskResponse, Error, void>({
    mutationFn: async () => {
      return askQuestion(question, selectedDocumentIds, topK);
    },
  });

  function toggleDocument(documentId: string) {
    setSelectedDocumentIds((current) => {
      const newIds = current.includes(documentId) ? current.filter((id) => id !== documentId) : [...current, documentId];
      updateUrlParams(newIds);
      return newIds;
    });
  }

  function toggleAllDocuments(checked: boolean) {
    if (checked) {
      setSelectedDocumentIds([]);
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

  async function copyMarkdown() {
    if (!result) return;
    let md = `**Question**: ${question}\n\n**Answer**: ${result.answer}\n\n### Citations\n`;
    result.citations.forEach((c, i) => {
      md += `\n[${i + 1}] Document: ${c.document_id} (Pages ${c.pdf_page_start}-${c.pdf_page_end
        })\n> ${c.text.trim()}\n`;
    });
    await navigator.clipboard.writeText(md);
    setCopiedMarkdown(true);
    setTimeout(() => setCopiedMarkdown(false), 2000);
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <h1>Ask</h1>
        <p className="muted">Ask across all embedded documents or select specific documents to scope retrieval.</p>

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
            className="w-full p-2 border rounded max-w-[200px]"
          />

          <button type="submit" className="primary-button top-gap w-fit" disabled={asking}>
            {asking ? "Asking..." : "Ask"}
          </button>
        </form>

        {error ? <p className="error-text top-gap">{error.message}</p> : null}
      </div>

      <div className="panel">
        <div className="inline-row spread border-b pb-4 mb-4">
          <h2>Document scope</h2>
          <span className="bg-slate-100 px-3 py-1 rounded-full text-sm font-medium">
            {selectedDocumentIds.length === 0 ? "All documents" : `${selectedDocumentIds.length} selected`}
          </span>
        </div>

        <label className="flex items-center space-x-2 p-3 bg-slate-50 border rounded-lg mb-4 cursor-pointer hover:bg-slate-100 transition-colors">
          <input
            type="checkbox"
            checked={selectedDocumentIds.length === 0}
            onChange={(e) => toggleAllDocuments(e.target.checked)}
            className="w-4 h-4 text-blue-600"
          />
          <span className="font-medium text-slate-900">All documents</span>
        </label>

        {loadingDocs ? <p className="text-slate-500 animate-pulse">Loading documents...</p> : null}

        {!loadingDocs && documents.length === 0 ? <p className="text-slate-500">No documents available.</p> : null}

        {!loadingDocs && documents.length > 0 ? (
          <ul className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
            {documents.map((document) => (
              <li key={document.id}>
                <label className="flex items-start space-x-3 p-3 border rounded-lg cursor-pointer hover:bg-slate-50 transition-colors">
                  <input
                    type="checkbox"
                    checked={selectedDocumentIds.includes(document.id)}
                    onChange={() => toggleDocument(document.id)}
                    className="w-4 h-4 mt-1 text-blue-600"
                  />
                  <div className="flex flex-col">
                    <span className="font-medium text-slate-900 break-all">{document.filename}</span>
                    <span className="text-xs text-slate-500 mt-1 uppercase tracking-wider">ID: {document.id}</span>
                  </div>
                </label>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {result ? (
        <div className="panel md:col-span-2">
          <div className="flex items-center justify-between border-b pb-4 mb-4">
            <h2>Answer</h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={copyAnswer}
                className="px-3 py-1.5 text-sm rounded bg-slate-100 hover:bg-slate-200 transition-colors"
              >
                {copiedAnswer ? "Copied!" : "Copy Answer"}
              </button>
              <button
                type="button"
                onClick={copyMarkdown}
                className="px-3 py-1.5 text-sm rounded bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
              >
                {copiedMarkdown ? "Copied!" : "Copy Markdown"}
              </button>
            </div>
          </div>
          <div className="prose max-w-none text-slate-800 leading-relaxed whitespace-pre-wrap">
            {result.answer}
          </div>

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
