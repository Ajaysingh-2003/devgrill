"use client";

import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";
import { toast } from "sonner";
import { saveLeave } from "./actions";

const DAY = 86_400_000;

/** "2026-11-03" + n days, in plain calendar arithmetic (no time zones involved). */
function addDays(iso: string, n: number): string {
  return new Date(Date.parse(`${iso}T00:00:00Z`) + n * DAY).toISOString().slice(0, 10);
}

/** Consecutive days grouped into ranges, for listing. */
function ranges(days: string[]): [string, string][] {
  const out: [string, string][] = [];
  for (const d of [...days].sort()) {
    const last = out.at(-1);
    if (last && addDays(last[1], 1) === d) last[1] = d;
    else out.push([d, d]);
  }
  return out;
}

const formatDay = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });

/** On-call leave: days that never break your streak. Booked ahead, from today. */
export function LeaveSettings({ initial, today }: { initial: string[]; today: string }) {
  const [days, setDays] = useState(initial);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const fromId = useId();
  const toId = useId();
  const save = useMutation({
    mutationFn: (next: string[]) => saveLeave(next),
    onSuccess: (saved) => setDays(saved),
    onError: (err) => toast.error(err instanceof Error ? err.message : "Couldn’t save that. Try again."),
  });

  function book() {
    if (!from) return;
    const end = to && to >= from ? to : from;
    const added: string[] = [];
    for (let d = from; d <= end && added.length < 31; d = addDays(d, 1)) added.push(d);
    save.mutate([...new Set([...days, ...added])].sort());
    setFrom("");
    setTo("");
  }

  const max = addDays(today, 90);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor={fromId} className="text-label text-fg-muted">
            From
          </label>
          <input
            id={fromId}
            type="date"
            min={today}
            max={max}
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="h-9 rounded-sm border border-border-input bg-surface px-2 text-body text-fg"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={toId} className="text-label text-fg-muted">
            To (optional)
          </label>
          <input
            id={toId}
            type="date"
            min={from || today}
            max={max}
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="h-9 rounded-sm border border-border-input bg-surface px-2 text-body text-fg"
          />
        </div>
        <button
          type="button"
          disabled={!from || save.isPending}
          onClick={book}
          className="inline-flex h-9 items-center rounded-sm border border-border-strong px-3 text-label font-medium text-fg hover:bg-raised disabled:opacity-50"
        >
          Book leave
        </button>
      </div>
      {days.length ? (
        <ul className="flex flex-col divide-y divide-border rounded-sm border border-border">
          {ranges(days).map(([a, b]) => (
            <li key={a} className="flex items-center gap-3 px-3 py-2 text-body text-fg">
              <span className="flex-1">{a === b ? formatDay(a) : `${formatDay(a)} to ${formatDay(b)}`}</span>
              <button
                type="button"
                disabled={save.isPending}
                onClick={() => save.mutate(days.filter((d) => d < a || d > b))}
                aria-label={`Cancel leave ${a === b ? `on ${formatDay(a)}` : `from ${formatDay(a)} to ${formatDay(b)}`}`}
                className="rounded-sm px-2 py-1 text-label font-medium text-fg-muted hover:bg-raised hover:text-fg"
              >
                Cancel
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-label text-fg-subtle">No leave booked.</p>
      )}
    </div>
  );
}
