import type { Citation } from "@/lib/types";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="text-slate-500 italic">No citations returned.</p>;
  }

  return (
    <ol className="space-y-2">
      {citations.map((citation, index) => (
        <li key={`${citation.filename}-${citation.page_start}-${citation.page_end}-${index}`} className="text-sm text-slate-700">
          <span className="font-medium break-words">{citation.filename}</span>
          <span className="ml-2 text-slate-500">
            {citation.page_start === citation.page_end
              ? `p. ${citation.page_start}`
              : `pp. ${citation.page_start}\u2013${citation.page_end}`}
          </span>
        </li>
      ))}
    </ol>
  );
}
