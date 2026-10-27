import type { Metadata } from "next";
import { Suspense } from "react";
import { CircleCheck, CircleDashed, CircleX } from "lucide-react";
import { adminScenarios } from "@devgrill/api-client";
import { cn } from "@devgrill/ui/lib/utils";
import { refusal } from "@/components/admin/forbidden";
import { ScenarioActions } from "@/components/admin/scenario-actions";
import { PageSkeleton } from "@/components/page-skeleton";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Content console" };

const STATUS_TONE: Record<string, string> = {
  published: "bg-success-subtle text-success-text",
  review: "bg-info-subtle text-info-text",
  draft: "bg-raised text-fg-muted",
  retired: "bg-raised text-fg-subtle",
};

/** The validation report's verdict: icon + label + colour. */
function Report({ ok }: { ok: boolean | null | undefined }) {
  if (ok == null)
    return (
      <span className="inline-flex items-center gap-1 text-fg-subtle">
        <CircleDashed className="size-3.5" aria-hidden="true" />
        No report
      </span>
    );
  return ok ? (
    <span className="inline-flex items-center gap-1 text-success-text">
      <CircleCheck className="size-3.5" aria-hidden="true" />
      Passed
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-danger-text">
      <CircleX className="size-3.5" aria-hidden="true" />
      Failed
    </span>
  );
}

async function ScenarioTable() {
  const { data, response } = await adminScenarios({ client: await api(), query: { limit: 100 } });
  if (!data) return refusal(response, "The content console");
  const inReview = data.items.filter((r) => r.status === "review").length;
  return (
    <>
      <p className="text-body text-fg-muted">
        {inReview ? `${inReview} waiting for review.` : "Nothing waiting for review."} Content is edited in
        git; this is where it moves from draft to review to published.
      </p>
      <div className="overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full min-w-[64rem] text-left text-body">
          <caption className="sr-only">Scenarios with status, report, version, plays and actions</caption>
          <thead className="border-b border-border text-caption text-fg-subtle">
            <tr>
              {["Scenario", "Track", "Status", "Report", "Version", "Attempts", "Resolved", "Actions"].map(
                (h) => (
                  <th key={h} scope="col" className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.slug} className="border-b border-border last:border-b-0 hover:bg-raised">
                <th scope="row" className="px-3 py-2 font-mono text-mono font-medium text-fg">
                  {r.slug}
                </th>
                <td className="px-3 py-2 text-fg-muted">{r.track_slug}</td>
                <td className="px-3 py-2">
                  <span
                    className={cn("rounded-xs px-1.5 py-0.5 text-caption font-medium", STATUS_TONE[r.status])}
                  >
                    {r.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-caption">
                  <Report ok={r.report_ok} />
                </td>
                <td className="px-3 py-2 font-mono text-mono text-fg-muted tabular-nums">
                  {r.version ? `v${r.version}` : "–"}
                </td>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">{r.attempts}</td>
                <td className="px-3 py-2 font-mono text-mono tabular-nums">{r.resolved}</td>
                <td className="px-3 py-2">
                  <ScenarioActions slug={r.slug} actions={r.actions ?? []} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Scenarios: status, validation report and the lifecycle actions your role allows. */
export default function AdminPage() {
  return (
    <>
      <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Scenarios</h1>
      <Suspense fallback={<PageSkeleton label="Loading scenarios" />}>
        <ScenarioTable />
      </Suspense>
    </>
  );
}
