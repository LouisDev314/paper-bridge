"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getJob } from "@/lib/api";

type BatchItem = {
  docId: string;
  jobId: string;
  filename: string;
};

function JobStatusPoller({ item, onComplete }: { item: BatchItem; onComplete: (status: string) => void }) {
  const [completeStatus, setCompleteStatus] = useState<string | null>(null);

  const { data: job, error } = useQuery({
    queryKey: ["job", item.jobId],
    queryFn: () => getJob(item.jobId),
    refetchInterval: 2000,
    enabled: completeStatus === null,
  });

  useEffect(() => {
    if (job?.status && ["completed", "succeeded", "failed"].includes(job.status)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCompleteStatus(job.status);
      onComplete(job.status);
    } else if (error) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCompleteStatus("failed");
      onComplete("failed");
    }
  }, [job?.status, error, onComplete]);

  const displayStatus = completeStatus || job?.status || "loading";
  const isOk = displayStatus === "completed" || displayStatus === "succeeded";
  const isErr = displayStatus === "failed" || Boolean(error);
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
  const [items, setItems] = useState<BatchItem[]>([]);
  const [completedMap, setCompletedMap] = useState<Record<string, string>>({});

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("processing_batch");
      if (stored) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setItems(JSON.parse(stored) as BatchItem[]);
      }
    } catch {
      // Ignore invalid shapes
    }
  }, []);

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
              <JobStatusPoller
                key={item.docId}
                item={item}
                onComplete={(status) => handleComplete(item.jobId, status)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
