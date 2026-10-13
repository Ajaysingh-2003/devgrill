import type { Metadata } from "next";
import Link from "next/link";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { PageHeader } from "@/components/page-header";
import { DAILY, scenario } from "@/lib/mock";

export const metadata: Metadata = { title: "Daily incident" };

export default function DailyPage() {
  const s = scenario(DAILY.scenario)!;
  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <PageHeader
        title="Daily incident"
        description="One incident a day, the same for everyone. It resets at midnight India time."
      />
      <section className="flex flex-col gap-4 rounded-md border border-border bg-surface p-6">
        <SevBadge sev={s.sev} showName size="md" />
        <h2 className="font-serif text-display-lg text-fg">{s.title}</h2>
        <p className="text-body-lg text-fg-muted">{s.symptom}.</p>
        <p className="text-body text-fg-muted">
          {DAILY.players.toLocaleString("en-IN")} engineers have played it today. Median time{" "}
          {DAILY.medianMinutes} minutes. Closes in {DAILY.closesIn}.
        </p>
        <Link
          href={`/drills/${s.track}/${s.slug}`}
          className="inline-flex h-10 w-fit items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
        >
          Read the briefing
        </Link>
      </section>
    </div>
  );
}
