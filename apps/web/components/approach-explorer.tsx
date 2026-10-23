"use client";

import { useState } from "react";
import { ApproachList, type Approach } from "@devgrill/ui/components/devgrill/approach-list";

export type ExplorerApproach = Approach & {
  idea: string;
  /** The approach's patch (or a sketch of it). */
  code: string | null;
  /** Measured numbers worth comparing, if any: [label, value]. */
  stats?: [string, string][];
  pros: string[];
  cons: string[];
};

/** "Your fix next to the other ways to fix it": pick one, see its idea, code, numbers and trade-offs. */
export function ApproachExplorer({
  approaches,
  label = "Ways to fix it",
}: {
  approaches: ExplorerApproach[];
  label?: string;
}) {
  const [selected, setSelected] = useState((approaches.find((a) => a.yours) ?? approaches[0])?.id ?? "");
  const a = approaches.find((x) => x.id === selected) ?? approaches[0];
  if (!a) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <ApproachList approaches={approaches} value={a.id} onValueChange={setSelected} label={label} />
      {/* Not a live region: the radio selection announces the change; details sit beside it. */}
      <article className="flex min-w-0 flex-col gap-4 rounded-md border border-border bg-surface p-5">
        <h3 className="text-heading-md font-semibold text-fg">{a.name}</h3>
        <p className="text-body-lg text-fg-muted">{a.idea}</p>
        {a.code ? (
          // Long patch lines scroll sideways; focusable so the keyboard can scroll them too.
          <pre
            tabIndex={0}
            aria-label={`${a.name}: the change`}
            className="overflow-x-auto rounded-sm bg-sunken p-3 font-mono text-mono text-fg"
          >
            {a.code}
          </pre>
        ) : null}
        {a.stats?.length ? (
          <dl className="grid gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-3">
            {a.stats.map(([k, v]) => (
              <div key={k} className="bg-surface px-3 py-2.5">
                <dt className="text-caption text-fg-muted">{k}</dt>
                <dd className="font-mono text-heading-md font-semibold text-fg tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          {a.pros.length ? (
            <div className="rounded-sm bg-success-subtle px-3 py-2.5">
              <p className="text-caption font-semibold text-success-text">Good at</p>
              <ul className="mt-1 flex flex-col gap-1 text-body text-fg">
                {a.pros.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {a.cons.length ? (
            <div className="rounded-sm bg-warning-subtle px-3 py-2.5">
              <p className="text-caption font-semibold text-warning-text">Costs you</p>
              <ul className="mt-1 flex flex-col gap-1 text-body text-fg">
                {a.cons.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </article>
    </div>
  );
}
