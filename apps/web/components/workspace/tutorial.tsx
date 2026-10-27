"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { GraduationCap, X } from "lucide-react";
import type { IncidentSnapshot } from "./model";

/**
 * The guest tutorial (/try, PLAN §8.3): tools unlock one step at a time, and the incident lead
 * leaves a tip for each step, once, dismissible. Locking is guidance, not security: the API
 * accepts any action the scenario allows.
 */
type Step = {
  id: string;
  /** Tools this step adds to the rail. */
  unlocks: string[];
  title: string;
  body: string;
  done: (p: Progress) => boolean;
};

type Progress = { visited: ReadonlySet<string>; incident: IncidentSnapshot };

const ACTED = new Set(["deploy", "rollback", "action"]);
const PAST_ACTIVE = new Set<string>(["mitigated", "verifying", "resolved"]);

const STEPS: Step[] = [
  {
    id: "page",
    unlocks: ["overview", "logs"],
    title: "Start with the page",
    body: "Read the alert and the graphs on Overview: what is wrong, and since when? Then open Logs to see what the service is doing.",
    done: (p) => p.visited.has("logs"),
  },
  {
    id: "logs",
    unlocks: ["cache"],
    title: "Follow a request",
    body: "Look at what product requests do before they reach the database. If the cache never answers them, look at the cache itself. It's unlocked now.",
    done: (p) => p.visited.has("cache"),
  },
  {
    id: "changed",
    unlocks: ["code", "deploys"],
    title: "Ask what changed",
    body: "A healthy cache that stores nothing usually means a setting changed. Deploys lists recent changes and Code has the config. Fix it and deploy, or undo the change.",
    done: (p) => PAST_ACTIVE.has(p.incident.state) || p.incident.events.some((e) => ACTED.has(e.type)),
  },
  {
    id: "check",
    unlocks: [],
    title: "Prove it",
    body: "When the graphs settle, press “It's working again”, then “Check my fix”. The check replays real traffic against your change.",
    done: (p) => p.incident.state === "resolved",
  },
];

type Saved = { visited: string[]; dismissed: string[] };
const EMPTY = "";

// Progress per attempt: localStorage when it works, memory always (private windows and blocked
// storage still progress, they just forget on reload). An external store, so the server render
// and hydration both see "no progress" and the saved state applies right after.
const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function read(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? memory.get(key) ?? EMPTY;
  } catch {
    return memory.get(key) ?? EMPTY;
  }
}

function write(key: string, saved: Saved) {
  const raw = JSON.stringify(saved);
  memory.set(key, raw);
  try {
    window.localStorage.setItem(key, raw);
  } catch {
    // Memory only.
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function parse(raw: string): Saved {
  try {
    const saved = JSON.parse(raw) as Partial<Saved>;
    return { visited: saved.visited ?? [], dismissed: saved.dismissed ?? [] };
  } catch {
    return { visited: [], dismissed: [] };
  }
}

export type Tutorial = {
  /** Tools unlocked so far (null outside the tutorial: the scenario's own list applies). */
  unlocked: ReadonlySet<string> | null;
  step: { index: number; total: number; title: string; body: string } | null;
  dismiss: () => void;
};

export function useTutorial(
  attemptId: string,
  on: boolean,
  tool: string,
  incident: IncidentSnapshot,
): Tutorial {
  const key = `devgrill:tutorial:${attemptId}`;
  const raw = useSyncExternalStore(
    subscribe,
    () => (on ? read(key) : EMPTY),
    () => EMPTY,
  );
  const saved = useMemo(() => parse(raw), [raw]);
  // Opening a tool is what moves the first steps on. Writes read the store itself, not this
  // render's snapshot: during hydration that snapshot is still empty.
  useEffect(() => {
    if (!on) return;
    const now = parse(read(key));
    if (!now.visited.includes(tool)) write(key, { ...now, visited: [...now.visited, tool] });
  }, [on, key, tool]);

  return useMemo(() => {
    if (!on) return { unlocked: null, step: null, dismiss: () => {} };
    const progress = { visited: new Set(saved.visited), incident };
    let index = STEPS.findIndex((s) => !s.done(progress));
    if (index === -1) index = STEPS.length;
    const unlocked = new Set(STEPS.slice(0, index + 1).flatMap((s) => s.unlocks));
    const current = STEPS[index];
    return {
      unlocked,
      step:
        current && !saved.dismissed.includes(current.id)
          ? { index, total: STEPS.length, title: current.title, body: current.body }
          : null,
      dismiss: () => {
        if (!current) return;
        const now = parse(read(key));
        write(key, { ...now, dismissed: [...now.dismissed, current.id] });
      },
    };
  }, [on, key, saved, incident]);
}

/** The incident lead's tip for the current step: no motion, announced politely. */
export function TutorialTip({ tutorial }: { tutorial: Tutorial }) {
  const step = tutorial.step;
  return (
    <div
      role="status"
      aria-live="polite"
      className={step ? "border-b border-border bg-brand-subtle" : "sr-only"}
    >
      {step ? (
        <div className="flex items-start gap-3 px-4 py-3">
          <GraduationCap className="mt-0.5 size-4 shrink-0 text-brand-text" aria-hidden="true" />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="text-label font-semibold text-fg">
              <span className="font-normal text-fg-muted">
                Tip {step.index + 1} of {step.total}:{" "}
              </span>
              {step.title}
            </p>
            <p className="max-w-3xl text-label text-fg">{step.body}</p>
          </div>
          <button
            type="button"
            onClick={tutorial.dismiss}
            className="inline-flex h-7 shrink-0 items-center gap-1 rounded-sm px-2 text-label font-medium text-fg-muted hover:bg-raised hover:text-fg"
          >
            <X className="size-3.5" aria-hidden="true" />
            Got it
          </button>
        </div>
      ) : null}
    </div>
  );
}
