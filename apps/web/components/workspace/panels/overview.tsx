"use client";

import { Activity } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo } from "react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import type { ChartMarker } from "@devgrill/ui/components/devgrill/metric-chart";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { StatusPill } from "@devgrill/ui/components/devgrill/status-pill";
import { useIncident, useSource, useTelemetry } from "../context";
import { formatBytes, formatMs, formatPct } from "../model";

// uPlot loads with the first chart, not with the workspace route.
const MetricChart = dynamic(
  () => import("@devgrill/ui/components/devgrill/metric-chart").then((m) => m.MetricChart),
  { ssr: false, loading: () => <div className="h-[170px] rounded-sm bg-raised" aria-hidden="true" /> },
);

type Color = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
const CHARTS: Record<string, { title: string; format: (v: number) => string; color: Color }> = {
  p99_latency_ms: { title: "p99 latency, product pages", format: formatMs, color: 7 },
  error_rate: { title: "Error rate", format: formatPct, color: 4 },
  cache_hit_rate: { title: "Cache hit rate", format: formatPct, color: 1 },
  db_qps_product: { title: "Product reads on Postgres", format: (v) => `${Math.round(v)}/s`, color: 5 },
  request_rate: { title: "Requests", format: (v) => `${Math.round(v)}/s`, color: 2 },
  db_connections: { title: "Postgres connections", format: (v) => String(Math.round(v)), color: 3 },
  db_pool_in_use: { title: "API pool in use", format: (v) => String(Math.round(v)), color: 6 },
  orders_queue_depth: { title: "Orders waiting", format: (v) => String(Math.round(v)), color: 8 },
  cache_memory_bytes: { title: "Cache memory", format: formatBytes, color: 2 },
};
const MAX_CHARTS = 6;

export function OverviewPanel() {
  const { info } = useSource();
  const { samples } = useTelemetry();
  const { events, activeAt } = useIncident();

  // SLO metrics first (they decide "mitigated"), then the rest in the base app's order.
  const shown = useMemo(() => {
    const slo = Object.keys(info.slo);
    const rest = info.metrics.filter((m) => !slo.includes(m));
    return [...slo, ...rest].filter((m) => m in CHARTS).slice(0, MAX_CHARTS);
  }, [info]);

  const timestamps = useMemo(() => samples.map((s) => s.t), [samples]);
  const markers = useMemo<ChartMarker[]>(() => {
    const out: ChartMarker[] = [];
    if (activeAt) out.push({ at: activeAt / 1000, label: "paged" });
    for (const e of events) {
      if (e.type === "deploy" || e.type === "rollback") {
        out.push({
          at: new Date(e.ts).getTime() / 1000,
          label: `${e.type} ${String(e.payload.sha ?? "")}`.trim(),
        });
      }
    }
    return out;
  }, [events, activeAt]);

  // One summary in the header; each chart draws its own SLO line and breach.
  const latest = samples.at(-1)?.values ?? {};
  const slos = Object.entries(info.slo).map(([metric, target]) => {
    const value = latest[metric];
    if (value === null || value === undefined) return null;
    return (target.lt == null || value < target.lt) && (target.gt == null || value > target.gt);
  });
  const known = slos.filter((ok) => ok !== null);
  const breaching = slos.filter((ok) => ok === false).length;
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-overview"
      title="Overview"
      meta="Sampled every 2 s from the system's own metrics"
      actions={
        slos.length ? (
          <StatusPill
            status={known.length === 0 ? "unknown" : breaching ? "firing" : "healthy"}
            label={
              known.length === 0
                ? "SLO: no data yet"
                : breaching
                  ? `${breaching} of ${slos.length} SLOs breaching`
                  : slos.length === 1
                    ? "SLO holds"
                    : "Every SLO holds"
            }
          />
        ) : null
      }
    >
      {samples.length === 0 ? (
        <EmptyState icon={Activity} title="Collecting the first samples" compact>
          Charts fill in every 2 seconds once the sandbox is serving traffic.
        </EmptyState>
      ) : (
        <div className="grid gap-x-6 gap-y-5 p-4 xl:grid-cols-2">
          {shown.map((metric) => {
            const chart = CHARTS[metric]!;
            const target = info.slo[metric];
            const threshold = target?.lt ?? target?.gt;
            const values = samples.map((s) => s.values[metric] ?? null);
            const last = values.findLast((v) => v !== null);
            const summary =
              last == null
                ? `${chart.title}: no data yet.`
                : `${chart.title} is ${chart.format(last)}${threshold != null ? `; the SLO is ${target?.lt != null ? "under" : "over"} ${chart.format(threshold)}` : ""}.`;
            return (
              <MetricChart
                key={metric}
                title={chart.title}
                summary={summary}
                timestamps={timestamps}
                series={[{ label: chart.title, values, color: chart.color }]}
                format={chart.format}
                threshold={
                  threshold != null
                    ? { value: threshold, label: `SLO ${chart.format(threshold)}` }
                    : undefined
                }
                markers={markers}
                syncKey="incident"
                height={170}
              />
            );
          })}
        </div>
      )}
    </PanelFrame>
  );
}
