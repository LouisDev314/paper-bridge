import Link from "next/link";

import type { JobResponse } from "@/lib/types";

interface JobListProps {
  jobs: JobResponse[];
  emptyMessage: string;
}

function statusClass(status: string): string {
  if (status === "done") return "status status-ok";
  if (status === "failed") return "status status-bad";
  if (status === "needs_review") return "status status-warn";
  return "status status-neutral";
}

export function JobList({ jobs, emptyMessage }: JobListProps) {
  if (jobs.length === 0) {
    return <p className="muted">{emptyMessage}</p>;
  }

  return (
    <ul className="job-list">
      {jobs.map((job) => (
        <li key={job.id} className="job-row">
          <div>
            <strong>{job.task_type}</strong>
            <p className="muted mono">{job.id}</p>
            <p className="muted">Updated {new Date(job.updated_at).toLocaleString()}</p>
            {job.error_message ? <p className="error-text">{job.error_message}</p> : null}
          </div>
          <div className="job-meta">
            <span className={statusClass(job.status)}>{job.status}</span>
            <Link href={`/documents/${job.document_id}`} className="link-button">
              Document
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}
