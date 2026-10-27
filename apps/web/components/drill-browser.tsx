"use client";

import { useDeferredValue, useId, useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { ScenarioCard } from "@devgrill/api-client";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { Input } from "@devgrill/ui/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@devgrill/ui/components/ui/toggle-group";
import { ScenarioRow, STATUS } from "@/components/scenario-row";
import { sevNumber } from "@/lib/format";

const SEVS = ["sev1", "sev2", "sev3", "sev4"] as const;
const PROGRESS = ["new", "attempted", "solved"] as const;
const PLANS = [
  { value: "free", label: "Free" },
  { value: "pro", label: "Pro" },
] as const;

/** Pressed filters read at a glance: a strong border, not just a tint. */
const ITEM = "data-pressed:border-fg data-pressed:bg-raised";

type Filters = { q: string; sev: string[]; progress: string[]; plan: string[] };
const NONE: Filters = { q: "", sev: [], progress: [], plan: [] };

function matches(s: ScenarioCard, f: Filters): boolean {
  const q = f.q.trim().toLowerCase();
  if (q && !`${s.title} ${s.summary} ${s.topic_title ?? ""} ${s.tags.join(" ")}`.toLowerCase().includes(q))
    return false;
  if (f.sev.length && !f.sev.includes(s.difficulty)) return false;
  if (f.progress.length && !f.progress.includes(s.progress ?? "new")) return false;
  if (f.plan.length && !f.plan.includes(s.access ?? "pro")) return false;
  return true;
}

/**
 * Every drill in one filterable list. The catalog is small, so filtering happens here,
 * instantly, on what the server already sent; no request per keystroke.
 */
export function DrillBrowser({ drills, signedIn }: { drills: ScenarioCard[]; signedIn: boolean }) {
  const [filters, setFilters] = useState<Filters>(NONE);
  const deferred = useDeferredValue(filters);
  const shown = useMemo(() => drills.filter((s) => matches(s, deferred)), [drills, deferred]);
  const active = filters.q !== "" || filters.sev.length + filters.progress.length + filters.plan.length > 0;
  const searchId = useId();
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));

  return (
    <div className="flex flex-col gap-4">
      <div role="search" className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <div className="relative md:w-64">
          <label htmlFor={searchId} className="sr-only">
            Search drills
          </label>
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-fg-subtle"
            aria-hidden="true"
          />
          <Input
            id={searchId}
            type="search"
            value={filters.q}
            onChange={(e) => set({ q: e.target.value })}
            placeholder="Search by name or topic"
            autoComplete="off"
            spellCheck={false}
            className="h-9 pl-8"
          />
        </div>
        <ToggleGroup
          multiple
          aria-label="Severity"
          value={filters.sev}
          onValueChange={(sev: string[]) => set({ sev })}
          variant="outline"
          size="sm"
          spacing={1}
        >
          {SEVS.map((sev) => (
            <ToggleGroupItem key={sev} value={sev} className={`px-1 [&_svg]:h-2.5! [&_svg]:w-10! ${ITEM}`}>
              <SevBadge sev={sevNumber(sev)} />
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {signedIn ? (
          <ToggleGroup
            multiple
            aria-label="Progress"
            value={filters.progress}
            onValueChange={(progress: string[]) => set({ progress })}
            variant="outline"
            size="sm"
            spacing={1}
          >
            {PROGRESS.map((p) => (
              <ToggleGroupItem key={p} value={p} className={ITEM}>
                {STATUS[p].label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        ) : null}
        <ToggleGroup
          multiple
          aria-label="Plan"
          value={filters.plan}
          onValueChange={(plan: string[]) => set({ plan })}
          variant="outline"
          size="sm"
          spacing={1}
        >
          {PLANS.map((p) => (
            <ToggleGroupItem key={p.value} value={p.value} className={ITEM}>
              {p.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {active ? (
          <button
            type="button"
            onClick={() => setFilters(NONE)}
            className="h-7 rounded-sm px-2 text-label text-fg-muted underline-offset-4 hover:text-fg hover:underline"
          >
            Clear filters
          </button>
        ) : null}
      </div>

      <p aria-live="polite" className="text-label text-fg-muted">
        {active
          ? `${shown.length} of ${drills.length} drill${drills.length === 1 ? "" : "s"}`
          : `${drills.length} drill${drills.length === 1 ? "" : "s"}`}
      </p>

      {shown.length ? (
        <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
          {shown.map((s) => (
            <ScenarioRow key={s.slug} s={s} showTrack />
          ))}
        </ul>
      ) : (
        <div className="flex flex-col items-start gap-2 rounded-md border border-dashed border-border px-4 py-6">
          <p className="text-body text-fg">No drills match these filters.</p>
          <button
            type="button"
            onClick={() => setFilters(NONE)}
            className="text-label font-medium text-brand-text underline-offset-4 hover:underline"
          >
            Clear filters
          </button>
        </div>
      )}
    </div>
  );
}
