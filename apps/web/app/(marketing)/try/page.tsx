import type { Metadata } from "next";
import { Laptop } from "lucide-react";
import { TryStart } from "@/components/try-start";

export const metadata: Metadata = {
  title: "Try a five-minute incident",
  description:
    "No account needed: find out why a shop's cache stopped working, fix it and prove the fix holds.",
};

const STEPS = [
  { name: "Read the page", text: "An alert says the database is three times busier than usual." },
  { name: "Follow the clues", text: "Logs and the cache unlock as you go, with a tip at every step." },
  { name: "Fix it", text: "Change what broke and deploy it to your own practice system." },
  { name: "Check your fix", text: "We replay real traffic to prove it holds." },
];

export default function TryPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-10 px-4 py-16 sm:px-6 lg:py-24">
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-[clamp(2.25rem,5vw,3.5rem)] leading-[1.04] font-extrabold tracking-[-0.03em] text-fg">
          Fix a real outage in five minutes
        </h1>
        <p className="max-w-xl text-body-lg text-fg-muted">
          No account needed. A small shop added a cache and the database got busier, not quieter. You get the
          running system and the tools an on-call engineer would use.
        </p>
      </div>

      <ol className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2">
        {STEPS.map((s, i) => (
          <li key={s.name} className="flex gap-3 bg-surface p-4">
            <span className="font-mono text-mono-sm text-fg-subtle tabular-nums">{i + 1}</span>
            <span className="flex flex-col gap-1">
              <span className="text-body font-semibold text-fg">{s.name}</span>
              <span className="text-label text-fg-muted">{s.text}</span>
            </span>
          </li>
        ))}
      </ol>

      <div className="flex flex-col gap-4">
        <TryStart />
        <p className="flex items-center gap-2 text-label text-fg-subtle">
          <Laptop className="size-4" aria-hidden="true" />
          Needs a laptop or desktop screen. Sign in afterwards to keep your result.
        </p>
      </div>
    </div>
  );
}
