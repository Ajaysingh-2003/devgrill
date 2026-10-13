import type { Metadata } from "next";
import Link from "next/link";
import { X } from "lucide-react";
import { QuickFireCard } from "@/components/quickfire-card";
import { QUICKFIRE } from "@/lib/mock";

export const metadata: Metadata = { title: "Quick Fire" };

/** T8 Quick Fire: mobile-first triage cards (Arcade layer). Light on JavaScript by design. */
export default function QuickFirePage() {
  const { run, card } = QUICKFIRE;
  const minutes = Math.floor(run.remainingSec / 60);
  const seconds = String(run.remainingSec % 60).padStart(2, "0");
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col gap-5 px-4 py-5">
      <header className="flex items-center gap-3">
        <Link
          href="/drills"
          aria-label="End the run"
          className="grid size-10 place-items-center rounded-sm text-fg-muted hover:bg-raised"
        >
          <X className="size-5" aria-hidden="true" />
        </Link>
        <div className="flex-1">
          <p className="font-display text-heading-md font-extrabold tracking-tight text-fg">Quick Fire</p>
          <p className="text-caption text-fg-muted">
            {run.answered} answered, score {run.score}
          </p>
        </div>
        <p className="flex gap-1">
          <span className="sr-only">{`${3 - run.strikes} strikes left`}</span>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              aria-hidden="true"
              className={
                i < run.strikes
                  ? "size-2.5 rounded-full bg-danger-solid"
                  : "size-2.5 rounded-full border border-border-strong"
              }
            />
          ))}
        </p>
        <p className="rounded-sm bg-raised px-2 py-1 font-mono text-mono font-semibold text-fg tabular-nums">
          <span className="sr-only">Time left </span>
          {minutes}:{seconds}
        </p>
      </header>
      <main id="main" className="flex flex-1 flex-col gap-5">
        <QuickFireCard prompt={card.prompt} evidence={card.evidence} options={card.options} />
        <p className="mt-auto text-center text-caption text-fg-subtle">
          Three strikes end the run. Runs count toward your streak.
        </p>
      </main>
    </div>
  );
}
