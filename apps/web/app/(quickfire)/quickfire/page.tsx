import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { X } from "lucide-react";
import { quickfireDeck } from "@devgrill/api-client";
import { QuickFireRun } from "@/components/quickfire-run";
import { api, unwrap } from "@/lib/api";

export const metadata: Metadata = { title: "Quick Fire" };

async function Run() {
  const deck = await unwrap(quickfireDeck({ client: await api(), query: { limit: 30 } }));
  if (!deck.cards.length) {
    return (
      <p className="text-body text-fg-muted">No cards yet. They arrive with the next content release.</p>
    );
  }
  // A fresh deck each visit: keyed so "Play again" (a refresh) starts a new run.
  return <QuickFireRun key={deck.cards[0]!.id} cards={deck.cards} />;
}

/** T8 Quick Fire: mobile-first triage cards (Arcade layer). No sandbox, free for everyone. */
export default function QuickFirePage() {
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
        <p className="font-display text-heading-md font-extrabold tracking-tight text-fg">Quick Fire</p>
      </header>
      <main id="main" className="flex flex-1 flex-col gap-5">
        <Suspense fallback={<p className="text-body text-fg-muted">Shuffling the deck…</p>}>
          <Run />
        </Suspense>
        <p className="mt-auto text-center text-caption text-fg-subtle">
          Three minutes, three strikes. Keys 1 to 4 answer, Enter moves on.
        </p>
      </main>
    </div>
  );
}
