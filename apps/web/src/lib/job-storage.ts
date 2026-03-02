import type { JobResponse } from "@/lib/types";

const JOB_STORAGE_KEY = "paperbridge.jobs";

export function readJobsFromStorage(): JobResponse[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(JOB_STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.filter((entry): entry is JobResponse => {
      return typeof entry === "object" && entry !== null && typeof (entry as JobResponse).id === "string";
    });
  } catch {
    return [];
  }
}

export function writeJobsToStorage(jobs: JobResponse[]): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(JOB_STORAGE_KEY, JSON.stringify(jobs));
}
