import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { adminAudit } from "@devgrill/api-client";
import { refusal } from "@/components/admin/forbidden";
import { PageSkeleton } from "@/components/page-skeleton";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Audit log" };

const PAGE = 50;

async function Log({ searchParams }: { searchParams: PageProps<"/admin/audit">["searchParams"] }) {
  const raw = (await searchParams).before;
  const before = Number(Array.isArray(raw) ? raw[0] : raw) || undefined;
  const { data, response } = await adminAudit({ client: await api(), query: { before, limit: PAGE } });
  if (!data) return refusal(response, "The audit log");
  if (!data.length) return <p className="text-body text-fg-muted">No entries yet.</p>;
  return (
    <>
      <div className="overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full min-w-[56rem] text-left text-body">
          <caption className="sr-only">Admin and content actions, newest first</caption>
          <thead className="border-b border-border text-caption text-fg-subtle">
            <tr>
              {["When (UTC)", "Who", "Action", "Target", "Details"].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id} className="border-b border-border align-top last:border-b-0">
                <td className="px-3 py-2 font-mono text-mono-sm whitespace-nowrap text-fg-muted">
                  <time dateTime={e.ts}>{e.ts.slice(0, 16).replace("T", " ")}</time>
                </td>
                <td className="px-3 py-2 text-fg">{e.actor ?? "system"}</td>
                <th scope="row" className="px-3 py-2 font-mono text-mono font-medium text-fg">
                  {e.action}
                </th>
                <td className="px-3 py-2 font-mono text-mono-sm text-fg-muted">{e.target}</td>
                <td className="px-3 py-2 font-mono text-mono-sm wrap-anywhere text-fg-muted">
                  {Object.entries(e.data)
                    .filter(([, v]) => v !== null && v !== undefined)
                    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
                    .join("; ") || "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.length === PAGE ? (
        <Link
          href={`/admin/audit?before=${data.at(-1)!.id}`}
          className="w-fit text-body font-medium text-brand-text hover:underline"
        >
          Older entries
        </Link>
      ) : null}
    </>
  );
}

/** Every admin and content action, who did it and to what (admins only). */
export default function AuditPage({ searchParams }: PageProps<"/admin/audit">) {
  return (
    <>
      <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Audit log</h1>
      <Suspense fallback={<PageSkeleton label="Loading the audit log" />}>
        <Log searchParams={searchParams} />
      </Suspense>
    </>
  );
}
