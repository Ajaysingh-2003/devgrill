import type { Metadata } from "next";
import Link from "next/link";
import { Wordmark } from "@devgrill/ui/icons";
import { cn } from "@devgrill/ui/lib/utils";
import { ADMIN_ROWS } from "@/lib/mock";

export const metadata: Metadata = { title: "Content console" };

const STATUS_TONE: Record<string, string> = {
  published: "bg-success-subtle text-success-text",
  review: "bg-info-subtle text-info-text",
  draft: "bg-raised text-fg-muted",
};

/** T10 Admin content console (dense Control Room). */
export default function AdminPage() {
  return (
    <>
      <header className="border-b border-border">
        <div className="flex h-12 items-center gap-4 px-4">
          <Link href="/drills" aria-label="DevGrill home" className="rounded-sm">
            <Wordmark />
          </Link>
          <span className="text-label font-semibold text-fg-muted">Content console</span>
        </div>
      </header>
      <main id="main" className="flex flex-col gap-4 p-4">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Scenarios</h1>
          <p className="text-label text-fg-muted">2 need attention</p>
        </div>
        <div className="overflow-x-auto rounded-md border border-border bg-surface">
          <table className="w-full min-w-[52rem] text-left text-body">
            <caption className="sr-only">Scenarios with status, validation and play analytics</caption>
            <thead className="border-b border-border text-caption text-fg-subtle">
              <tr>
                {["Scenario", "Status", "Version", "Validation", "Solve rate", "Median time", "Flag"].map(
                  (h) => (
                    <th key={h} scope="col" className="px-3 py-2 font-medium">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {ADMIN_ROWS.map((r) => (
                <tr key={r.slug} className="border-b border-border last:border-b-0 hover:bg-raised">
                  <th scope="row" className="px-3 py-2 font-mono text-mono font-medium text-fg">
                    {r.slug}
                  </th>
                  <td className="px-3 py-2">
                    <span
                      className={cn(
                        "rounded-xs px-1.5 py-0.5 text-caption font-medium",
                        STATUS_TONE[r.status],
                      )}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-mono text-fg-muted">v{r.version}</td>
                  <td
                    className={cn(
                      "px-3 py-2 text-label font-medium",
                      r.validation === "pass" ? "text-success-text" : "text-danger-text",
                    )}
                  >
                    {r.validation === "pass" ? "Passes" : "Fails"}
                  </td>
                  <td className="px-3 py-2 font-mono text-mono text-fg tabular-nums">
                    {r.solveRate ? `${r.solveRate}%` : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-mono text-fg tabular-nums">{r.median}</td>
                  <td className="px-3 py-2 text-label text-warning-text">{r.flag ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </>
  );
}
