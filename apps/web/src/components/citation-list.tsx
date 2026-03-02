import Link from "next/link";

import type { Citation } from "@/lib/types";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="text-slate-500 italic">No citations returned.</p>;
  }

  return (
    <ol className="space-y-4">
      {citations.map((citation, index) => (
        <li
          key={`${citation.chunk_id}-${citation.document_id}-${index}`}
          className="border rounded-lg overflow-hidden bg-white shadow-sm"
        >
          <div className="bg-slate-50 border-b px-4 py-2 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-sm">
              <span className="bg-blue-100 text-blue-800 font-medium px-2 py-0.5 rounded text-xs flex-shrink-0">
                Source {index + 1}
              </span>
              <span className="text-slate-600 truncate max-w-[200px]" title={citation.document_id}>
                Doc: {citation.document_id.slice(0, 8)}...
              </span>
              <span className="text-slate-500 px-2 border-l border-slate-300">
                Pages: {citation.pdf_page_start} - {citation.pdf_page_end}
              </span>
              {typeof citation.similarity_score === "number" && (
                <span className="text-emerald-600 px-2 border-l border-slate-300">
                  Score: {(citation.similarity_score * 100).toFixed(1)}%
                </span>
              )}
            </div>

            <Link
              href={`/documents/${citation.document_id}`}
              className="text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline transition-colors"
            >
              View Document →
            </Link>
          </div>

          <details className="group">
            <summary className="px-4 py-3 cursor-pointer text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors list-none">
              <div className="flex items-center justify-between">
                <span>View chunk text ({citation.text.length} chars)</span>
                <span className="transform group-open:rotate-180 transition-transform">▼</span>
              </div>
            </summary>
            <div className="px-4 py-3 border-t bg-slate-50">
              <p className="text-sm text-slate-700 whitespace-pre-wrap font-serif leading-relaxed">
                {citation.text}
              </p>
            </div>
          </details>
        </li>
      ))}
    </ol>
  );
}
