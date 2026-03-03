"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { getJob } from "@/lib/api";

type BatchItem = {
  docId: string;
  jobId: string;
  filename: string;
};

function JobStatusPoller({ item, onComplete }: { item: BatchItem; onComplete: (status: string) => void }) {
  const hasReported = useRef(false);

  const { data: job, error } = useQuery({
    queryKey: ["job", item.jobId],
    queryFn: () => getJob(item.jobId),
    refetchInterval: (query) => {
      const status = (query.state.data as { status?: string } | undefined)?.status;
      if (status && ["done", "failed"].includes(status)) {
        return false;
      }
      return 2000;
    },
  });

  useEffect(() => {
    if (hasReported.current) {
      return;
    }

    if (job?.status && ["done", "failed"].includes(job.status)) {
      hasReported.current = true;
      onComplete(job.status);
      return;
    }

    if (error) {
      hasReported.current = true;
      onComplete("failed");
    }
  }, [job?.status, error, onComplete]);

  const displayStatus = error ? "failed" : job?.status || "loading";
  const isOk = displayStatus === "done";
  const isErr = displayStatus === "failed";
  const statusClass = isOk ? "status-ok" : isErr ? "status-bad" : "status-neutral";

  return (
    <tr>
      <td>{item.filename}</td>
      <td>
        <span className="muted">{item.docId}</span>
      </td>
      <td>
        <span className={`status ${statusClass}`}>{displayStatus}</span>
      </td>
      <td>{error ? error.message : job?.error_message || "-"}</td>
    </tr>
  );
}

export default function ProcessingPage() {
  const router = useRouter();
  const [items] = useState<BatchItem[]>(() => {
    if (typeof window === "undefined") {
      return [];
    }

    try {
      const stored = sessionStorage.getItem("processing_batch");
      if (!stored) {
        return [];
      }
      return JSON.parse(stored) as BatchItem[];
    } catch {
      return [];
    }
  });
  const [completedMap, setCompletedMap] = useState<Record<string, string>>({});

  const handleComplete = (jobId: string, status: string) => {
    setCompletedMap((prev) => ({ ...prev, [jobId]: status }));
  };

  useEffect(() => {
    if (items.length === 0) return;

    const allFinished = items.every((item) => completedMap[item.jobId]);
    const anyFailed = items.some((item) => completedMap[item.jobId] === "failed");

    if (allFinished && !anyFailed) {
      const docIds = items.map((i) => i.docId).join(",");
      router.push(`/ask?docIds=${docIds}`);
    }
  }, [completedMap, items, router]);

  const handleManualNav = () => {
    if (items.length > 0) {
      const docIds = items.map((i) => i.docId).join(",");
      router.push(`/ask?docIds=${docIds}`);
    } else {
      router.push("/ask");
    }
  };

  if (items.length === 0) {
    return (
      <section className="page-grid">
        <div className="panel">
          <h1>Processing pipeline</h1>
          <p className="muted">No active batch found.</p>
          <button onClick={() => router.push("/dashboard")} className="primary-button top-gap">
            Go to Dashboard
          </button>
        </div>
      </section>
    );
  }

  const allFinished = items.every((item) => completedMap[item.jobId]);
  const anyFailed = items.some((item) => completedMap[item.jobId] === "failed");

  return (
    <section className="page-grid">
      <div className="panel">
        <div className="inline-row spread">
          <h1>{allFinished && !anyFailed ? "Processing complete!" : "Processing pipeline..."}</h1>
          <button
            type="button"
            className={allFinished && !anyFailed ? "primary-button" : "secondary-button"}
            onClick={handleManualNav}
          >
            Go to Ask now
          </button>
        </div>
        <p className="muted">
          Polling backend for auto-processing tasks. We will redirect you once everything succeeds.
        </p>

        <table className="data-table top-gap full-width">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Document ID</th>
              <th>Status</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <JobStatusPoller key={item.docId} item={item} onComplete={(status) => handleComplete(item.jobId, status)} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
