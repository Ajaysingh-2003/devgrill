import { listCaseFiles, type CaseFileSummary } from "@devgrill/api-client";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { CircleCheck } from "lucide-react";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { PageHeader } from "@/components/page-header";
import { PageSkeleton } from "@/components/page-skeleton";
import { PageTransition } from "@/components/page-transition";
import { api, sevNumber, unwrap } from "@/lib/api";

export const metadata: Metadata = {
  title: "Case files",
  description: "Real incidents, recorded. Read the evidence and name the cause, the first move and the fix.",
};

function CaseRow({ c }: { c: CaseFileSummary }) {
  return (
    <li>
      <Link
        href={`/case-files/${c.slug}`}
        className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-1 rounded-sm px-3 py-3 hover:bg-raised md:grid-cols-[6rem_1fr_8rem]"
      >
        <SevBadge sev={sevNumber(c.difficulty)} />
        <span className="flex min-w-0 flex-col">
          <span className="text-body font-semibold text-fg">{c.title}</span>
          <span className="truncate text-label text-fg-muted">{c.summary}</span>
        </span>
        {c.score === null ? null : (
          <span className="col-start-2 inline-flex items-center gap-1.5 text-label text-success-text md:col-start-auto">
            <CircleCheck className="size-4" strokeWidth={1.75} aria-hidden="true" />
            Scored {c.score}
          </span>
        )}
      </Link>
    </li>
  );
}

async function CaseFiles() {
  const { items } = await unwrap(listCaseFiles({ client: await api() }));
  if (!items.length) {
    return <p className="text-body text-fg-muted">No case files yet. They arrive with the next release.</p>;
  }
  const tracks = [...new Set(items.map((c) => c.track_title))];
  return (
    <div className="flex flex-col gap-8">
      {tracks.map((track) => (
        <section key={track} aria-labelledby={`track-${track}`} className="flex flex-col gap-2">
          <h2 id={`track-${track}`} className="text-heading-sm font-semibold text-fg">
            {track}
          </h2>
          <ul className="divide-y divide-border">
            {items
              .filter((c) => c.track_title === track)
              .map((c) => (
                <CaseRow key={c.slug} c={c} />
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** Case files: free for everyone, no sandbox, no sign-in (ADR 013). */
export default function CaseFilesPage() {
  return (
    <PageTransition>
      <div className="flex flex-col gap-8">
        <PageHeader
          title="Case files"
          description="Each one is a real run of an incident, recorded: logs, charts, deploys and code. Read the evidence, then name the cause, the first move and the fix. Free, and nothing to wait for. Each shares its incident with a live drill, so doing one gives the other away."
        />
        <Suspense fallback={<PageSkeleton />}>
          <CaseFiles />
        </Suspense>
      </div>
    </PageTransition>
  );
}
