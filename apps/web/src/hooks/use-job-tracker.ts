"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getJob } from "@/lib/api";
import { readJobsFromStorage, writeJobsToStorage } from "@/lib/job-storage";
import type { JobResponse } from "@/lib/types";

const ACTIVE_STATUSES = new Set(["queued", "processing"]);
const MAX_STORED_JOBS = 80;

function sortJobs(jobs: JobResponse[]): JobResponse[] {
  return [...jobs].sort((left, right) => {
    return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  });
}

function mergeJob(existing: JobResponse[], incoming: JobResponse): JobResponse[] {
  const foundIndex = existing.findIndex((job) => job.id === incoming.id);
  if (foundIndex === -1) {
    return sortJobs([incoming, ...existing]).slice(0, MAX_STORED_JOBS);
  }

  const merged = [...existing];
  merged[foundIndex] = incoming;
  return sortJobs(merged).slice(0, MAX_STORED_JOBS);
}

export function useJobTracker() {
  const [jobs, setJobs] = useState<JobResponse[]>(() => sortJobs(readJobsFromStorage()));

  useEffect(() => {
    writeJobsToStorage(jobs);
  }, [jobs]);

  const registerJob = useCallback((job: JobResponse) => {
    setJobs((current) => mergeJob(current, job));
  }, []);

  useEffect(() => {
    const pending = jobs.filter((job) => ACTIVE_STATUSES.has(job.status));
    if (pending.length === 0) {
      return;
    }

    const interval = window.setInterval(() => {
      void Promise.all(
        pending.map(async (job) => {
          try {
            return await getJob(job.id);
          } catch {
            return null;
          }
        }),
      ).then((updates) => {
        setJobs((current) => {
          let merged = current;
          for (const update of updates) {
            if (update) {
              merged = mergeJob(merged, update);
            }
          }
          return merged;
        });
      });
    }, 3000);

    return () => {
      window.clearInterval(interval);
    };
  }, [jobs]);

  const jobsForDocument = useCallback(
    (documentId: string) => jobs.filter((job) => job.document_id === documentId),
    [jobs],
  );

  return useMemo(
    () => ({
      jobs,
      registerJob,
      jobsForDocument,
    }),
    [jobs, jobsForDocument, registerJob],
  );
}
