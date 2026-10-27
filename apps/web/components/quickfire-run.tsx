"use client";

import {
  answerCard,
  type QuickfireAnswerIn,
  type QuickfireAnswerOut,
  type QuickfireCardOut,
} from "@devgrill/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { QuickFireCard } from "@/components/quickfire-card";
import { ProblemError, browserApi, call } from "@/lib/browser-api";

const RUN_SECONDS = 180;
const STRIKES = 3;

/** A Quick Fire run: three minutes, three strikes, as many cards as you can read. */
export function QuickFireRun({ cards }: { cards: QuickfireCardOut[] }) {
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [result, setResult] = useState<QuickfireAnswerOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [right, setRight] = useState(0);
  const [strikes, setStrikes] = useState(0);
  const [startedAt] = useState(() => Date.now());
  const [now, setNow] = useState(startedAt);

  const left = Math.max(0, RUN_SECONDS - Math.floor((now - startedAt) / 1000));
  const card = cards[index];
  const over = strikes >= STRIKES || left === 0 || !card;

  useEffect(() => {
    if (over) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [over]);

  async function pick(key: string) {
    if (!card || result || busy) return;
    setPicked(key);
    setBusy(true);
    setError("");
    try {
      const out = await call(
        answerCard({
          client: browserApi(),
          path: { card_id: card.id },
          body: { choice: key as QuickfireAnswerIn["choice"] },
        }),
      );
      setResult(out);
      if (out.correct) setRight((n) => n + 1);
      else setStrikes((n) => n + 1);
    } catch (err) {
      setPicked(null);
      setError(err instanceof ProblemError ? err.message : "Couldn't check that answer. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function next() {
    setIndex((i) => i + 1);
    setPicked(null);
    setResult(null);
  }

  // Keys 1-4 pick, Enter moves on (instant: keyboard actions never animate).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || over) return;
      const n = Number(event.key);
      if (card && !result && n >= 1 && n <= card.options.length) void pick(card.options[n - 1]!.key);
      else if (result && event.key === "Enter" && !(event.target instanceof HTMLButtonElement)) next();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const answered = index + (result ? 1 : 0);
  const minutes = Math.floor(left / 60);
  const seconds = String(left % 60).padStart(2, "0");

  return (
    <div className="flex flex-1 flex-col gap-5">
      <div className="flex items-center gap-3">
        <p className="flex-1 text-caption text-fg-muted">
          {answered} answered, {right} right
        </p>
        <p className="flex gap-1">
          <span className="sr-only">{`${STRIKES - strikes} strikes left`}</span>
          {Array.from({ length: STRIKES }, (_, i) => (
            <span
              key={i}
              aria-hidden="true"
              className={
                i < strikes
                  ? "size-2.5 rounded-full bg-danger-solid"
                  : "size-2.5 rounded-full border border-border-strong"
              }
            />
          ))}
        </p>
        <p className="rounded-sm bg-raised px-2 py-1 font-mono text-mono font-semibold text-fg tabular-nums">
          <span className="sr-only">Time left </span>
          <span role="timer" aria-live="off">
            {minutes}:{seconds}
          </span>
        </p>
      </div>

      {over && !result ? (
        <section
          aria-labelledby="qf-end"
          className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5"
        >
          <h1 id="qf-end" className="font-display text-heading-lg font-extrabold tracking-tight text-fg">
            {right} right out of {answered}
          </h1>
          <p className="text-body text-fg-muted">
            {strikes >= STRIKES
              ? "Three strikes. Every wrong answer came with the reason: that's the practice."
              : left === 0
                ? "Time's up."
                : "You've seen every card in this deck."}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => router.refresh()}
              className="inline-flex h-11 items-center rounded-sm bg-brand px-5 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              Play again
            </button>
            <Link
              href="/drills"
              className="inline-flex h-11 items-center rounded-sm px-4 text-body font-medium text-fg hover:bg-raised"
            >
              Back to drills
            </Link>
          </div>
        </section>
      ) : card ? (
        <>
          <QuickFireCard
            card={card}
            picked={picked}
            result={result}
            busy={busy}
            onPick={(k) => void pick(k)}
          />
          {error ? (
            <p role="alert" className="text-body text-danger-text">
              {error}
            </p>
          ) : null}
          {result ? (
            <button
              type="button"
              onClick={next}
              aria-keyshortcuts="Enter"
              className="inline-flex h-11 items-center justify-center rounded-sm bg-brand px-5 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              {strikes >= STRIKES || left === 0 ? "See your result" : "Next card"}
            </button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
