"use client";

import { useState } from "react";
import { ApproachList } from "@devgrill/ui/components/devgrill/approach-list";
import { APPROACHES } from "@/lib/mock";

/** "Your fix vs every other approach": pick one, see its idea, code, numbers and trade-offs. */
export function ApproachExplorer() {
  const [selected, setSelected] = useState(APPROACHES.find((a) => a.yours)!.id);
  const a = APPROACHES.find((x) => x.id === selected)!;
  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <ApproachList
        approaches={APPROACHES}
        value={selected}
        onValueChange={setSelected}
        label="Approaches players used"
      />
      {/* Not a live region: the radio selection announces the change; details sit beside it. */}
      <article className="flex min-w-0 flex-col gap-4 rounded-md border border-border bg-surface p-5">
        <h3 className="text-heading-md font-semibold text-fg">{a.name}</h3>
        <p className="text-body-lg text-fg-muted">{a.idea}</p>
        <pre className="overflow-x-auto rounded-sm bg-sunken p-3 font-mono text-mono text-fg">{a.code}</pre>
        <dl className="grid gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-3">
          {[
            ["p99 during the 10x replay", a.p99],
            ["Database hits when the hot key expires", a.dbAtExpiry],
            ["Worst data staleness", a.staleness],
          ].map(([k, v]) => (
            <div key={k} className="bg-surface px-3 py-2.5">
              <dt className="text-caption text-fg-muted">{k}</dt>
              <dd className="font-mono text-heading-md font-semibold text-fg tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-sm bg-success-subtle px-3 py-2.5">
            <p className="text-caption font-semibold text-success-text">Good at</p>
            <p className="text-body text-fg">{a.pro}</p>
          </div>
          <div className="rounded-sm bg-warning-subtle px-3 py-2.5">
            <p className="text-caption font-semibold text-warning-text">Costs you</p>
            <p className="text-body text-fg">{a.con}</p>
          </div>
        </div>
      </article>
    </div>
  );
}
