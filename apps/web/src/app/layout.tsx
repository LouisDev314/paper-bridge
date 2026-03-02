import type { Metadata } from "next";

import { Navigation } from "@/components/navigation";
import { JobProvider } from "@/components/providers/job-provider";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "PaperBridge",
  description: "PaperBridge frontend for upload, extraction, embeddings, and grounded QA.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <JobProvider>
          <div className="app-shell">
            <Navigation />
            <main className="main-shell">{children}</main>
          </div>
        </JobProvider>
      </body>
    </html>
  );
}
