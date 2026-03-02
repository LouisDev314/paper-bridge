"use client";

import { createContext, useContext } from "react";

import { useJobTracker } from "@/hooks/use-job-tracker";

type JobContextValue = ReturnType<typeof useJobTracker>;

const JobContext = createContext<JobContextValue | null>(null);

export function JobProvider({ children }: { children: React.ReactNode }) {
  const value = useJobTracker();
  return <JobContext.Provider value={value}>{children}</JobContext.Provider>;
}

export function useJobs(): JobContextValue {
  const context = useContext(JobContext);
  if (!context) {
    throw new Error("useJobs must be used inside JobProvider");
  }
  return context;
}
