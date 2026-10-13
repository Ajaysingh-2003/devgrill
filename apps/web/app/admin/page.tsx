import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ShieldAlert } from "lucide-react";
import { adminScenarios } from "@devgrill/api-client";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { Wordmark } from "@devgrill/ui/icons";
import { cn } from "@devgrill/ui/lib/utils";
import { PageSkeleton } from "@/components/page-skeleton";
import { ApiError, api } from "@/lib/api";

export const metadata: Metadata = { title: "Content console" };

const STATUS_TONE: Record<string, string> = {
  published: "bg-success-subtle text-success-text",
  review: "bg-info-subtle text-info-text",
  draft: "bg-raised text-fg-muted",
  retired: "bg-raised text-fg-subtle",
};

async function ScenarioTable() {
  const { data, response } = await adminScenarios({ client: await api(), query: { limit: 100 } });
  if (response?.status === 401 || response?.status === 403) {
    return (
      <EmptyState icon={ShieldAlert} title="The content console needs the admin role">
        Ask an admin to grant it, or add your GitHub login to ADMIN_GITHUB_LOGINS locally and sign in again.
      </EmptyState>
    );
  }
  if (!data) throw new ApiError(response?.status ?? 503, null, response?.headers.get("x-request-id") ?? null);
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-surface">
      <table className="w-full min-w-[52rem] text-left text-body">
        <caption className="sr-only">Scenarios with status, version and play counts</caption>
        <thead className="border-b border-border text-caption text-fg-subtle">
          <tr>
            {["Scenario", "Track", "Status", "Version", "Attempts", "Resolved", "Updated"].map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
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
              <td className="px-3 py-2 font-mono text-mono text-fg-muted tabular-nums">
                {r.version ? `v${r.version}` : "–"}
              </td>
              <td className="px-3 py-2 font-mono text-mono tabular-nums">{r.attempts}</td>
              <td className="px-3 py-2 font-mono text-mono tabular-nums">{r.resolved}</td>
              <td className="px-3 py-2 text-fg-muted">
                <time dateTime={r.updated_at}>{r.updated_at.slice(0, 10)}</time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** T10 Admin content console (dense Control Room). Read-only until phase 3 adds publishing. */
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
        <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Scenarios</h1>
        <Suspense fallback={<PageSkeleton label="Loading scenarios" />}>
          <ScenarioTable />
        </Suspense>
      </main>
    </>
  );
}
