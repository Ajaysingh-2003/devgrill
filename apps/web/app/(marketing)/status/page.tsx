import type { Metadata } from "next";
import Link from "next/link";
import { Hourglass, Wrench } from "lucide-react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";

export const metadata: Metadata = { title: "Status" };

/** T11 system states: the capacity queue and maintenance, shown together for review. */
export default function StatusPage() {
  return (
    <div className="mx-auto grid max-w-4xl gap-6 px-4 py-16 md:grid-cols-2">
      <section aria-label="Queue" className="rounded-md border border-border bg-surface">
        <EmptyState
          icon={Hourglass}
          title="You’re third in line"
          action={<span className="font-mono text-mono text-fg-muted">About 40 seconds</span>}
        >
          Everyone’s practising right now. Your drill starts as soon as there’s room; keep this tab open.
        </EmptyState>
      </section>
      <section aria-label="Maintenance" className="rounded-md border border-border bg-surface">
        <EmptyState
          icon={Wrench}
          title="Drills are paused for maintenance"
          action={
            <Link href="/quickfire" className="text-body font-medium text-brand-text hover:underline">
              Play Quick Fire meanwhile
            </Link>
          }
        >
          We’re upgrading our servers until 02:30 IST. Your streak is safe today.
        </EmptyState>
      </section>
    </div>
  );
}
