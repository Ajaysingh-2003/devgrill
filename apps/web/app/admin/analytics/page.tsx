import type { Metadata } from "next";
import { Suspense } from "react";
import { TriangleAlert } from "lucide-react";
import { adminAnalytics } from "@devgrill/api-client";
import { refusal } from "@/components/admin/forbidden";
import { PageSkeleton } from "@/components/page-skeleton";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Scenario analytics" };

const pct = (x: number) => `${Math.round(x * 100)}%`;

async function Analytics() {
  const { data, response } = await adminAnalytics({ client: await api() });
  if (!data) return refusal(response, "Analytics");
  const flagged = data.filter((r) => r.flags.length);
  return (
    <>
      <p className="text-body text-fg-muted">
        Finished runs on every version. Flags appear from 10 runs on.{" "}
        {flagged.length ? `${flagged.length} flagged.` : "Nothing flagged."}
      </p>
      <div className="overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full min-w-[60rem] text-left text-body">
          <caption className="sr-only">
            Per scenario: runs, solve rate, leavers, median time, hints, flags
          </caption>
          <thead className="border-b border-border text-caption text-fg-subtle">
            <tr>
              {["Scenario", "Runs", "Solved", "Left", "Median time", "Hints", "Rating drift", "Flags"].map(
                (h) => (
                  <th key={h} scope="col" className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.slug} className="border-b border-border last:border-b-0">
                <th scope="row" className="px-3 py-2 font-mono text-mono font-medium text-fg">
                  {r.slug}
                </th>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">{r.attempts}</td>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">
                  {r.attempts ? pct(r.solve_rate) : "–"}
                </td>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">
                  {r.attempts ? pct(r.abandon_rate) : "–"}
                </td>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">
                  {r.median_minutes == null ? "–" : `${r.median_minutes} min`}
                  <span className="text-fg-subtle"> / est {r.est_minutes}</span>
                </td>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">{r.hints_per_attempt}</td>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">
                  {r.rating_drift > 0 ? "+" : ""}
                  {Math.round(r.rating_drift)}
                </td>
                <td className="px-3 py-2">
                  {r.flags.length ? (
                    <ul className="flex flex-col gap-0.5">
                      {r.flags.map((f) => (
                        <li key={f} className="inline-flex items-center gap-1 text-caption text-warning-text">
                          <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
                          {f}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-caption text-fg-subtle">–</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Per-scenario analytics with automatic flags (PLAN §11.4). */
export default function AnalyticsPage() {
  return (
    <>
      <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Analytics</h1>
      <Suspense fallback={<PageSkeleton label="Loading analytics" />}>
        <Analytics />
      </Suspense>
    </>
  );
}
