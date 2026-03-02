import Link from "next/link";

import type { Citation } from "@/lib/types";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="muted">No citations returned.</p>;
  }

  return (
    <ol className="citation-list">
      {citations.map((citation) => (
        <li key={`${citation.chunk_id}-${citation.document_id}`} className="citation-card">
          <p className="mono">
            chunk <strong>{citation.chunk_id}</strong> | pdf pages {citation.pdf_page_start}-{citation.pdf_page_end}
          </p>
          <p>{citation.text}</p>
          <Link href={`/documents/${citation.document_id}`} className="link-button">
            Open document
          </Link>
        </li>
      ))}
    </ol>
  );
}
