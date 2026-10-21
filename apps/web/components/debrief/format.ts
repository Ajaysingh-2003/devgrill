import type { ProbeResultOut, SloTarget } from "@devgrill/api-client";
import type { Probe } from "@devgrill/ui/components/devgrill/probe-table";

type Unit = { label: string; format: (v: number) => string };

const pct = (v: number) => `${(v * 100).toFixed(v < 0.01 && v > 0 ? 2 : 1)}%`;
const ms = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);
const plain = (v: number) => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(+v.toFixed(2)));

/** How the verifier's measurements read on the debrief (ADR 015). Unknown ones fall back. */
const UNITS: Record<string, Unit> = {
  p99_ms: { label: "p99", format: ms },
  p95_ms: { label: "p95", format: ms },
  error_rate: { label: "errors", format: pct },
  after_p99_ms: { label: "p99 after", format: ms },
  after_error_rate: { label: "errors after", format: pct },
  recovery_s: { label: "recovered in", format: (v) => `${plain(v)} s` },
  db_scans_per_request: { label: "database reads per request", format: plain },
  db_scans_per_s: { label: "database reads per second", format: plain },
  request_count_drift: { label: "request count drift", format: pct },
  error_rate_drift: { label: "error rate drift", format: pct },
  db_connections: { label: "Postgres connections", format: plain },
  visible_after_s: { label: "price visible after", format: (v) => `${plain(v)} s` },
  cache_max_memory_mb: { label: "cache memory limit", format: (v) => `${plain(v)} MB` },
  checks_failed: { label: "failed checks", format: plain },
};

function unit(key: string): Unit {
  return UNITS[key] ?? { label: key.replaceAll("_", " "), format: plain };
}

export function formatTarget(target: Record<string, SloTarget>): string {
  return Object.entries(target)
    .map(([key, t]) => {
      const u = unit(key);
      const bounds = [
        t.lt != null ? `under ${u.format(t.lt)}` : null,
        t.gt != null ? `over ${u.format(t.gt)}` : null,
      ].filter(Boolean);
      return `${u.label} ${bounds.join(" and ")}`;
    })
    .join("; ");
}

export function formatMeasured(measured: Record<string, number | null>, keys?: string[]): string {
  return (keys ?? Object.keys(measured))
    .filter((k) => k in measured)
    .map((k) => {
      const v = measured[k];
      const u = unit(k);
      return `${u.label} ${v == null ? "not measured" : u.format(v)}`;
    })
    .join("; ");
}

/** A verify result as a ProbeTable row. */
export function toProbeRow(p: ProbeResultOut): Probe {
  const target = p.target ?? {};
  const measured = p.measured ?? {};
  const targetKeys = Object.keys(target);
  const observed = formatMeasured(measured, targetKeys.length ? targetKeys : undefined);
  return {
    key: p.key,
    name: p.title,
    how: p.how,
    target: formatTarget(target) || "every check passes",
    observed: observed || (p.passed ? undefined : (p.detail ?? "").slice(0, 200)),
    outcome: p.passed == null ? "skipped" : p.passed ? "pass" : "fail",
  };
}

export function clock(seconds: number): string {
  // The page lands a moment before the clock starts: under a second early reads as 00:00.
  const sign = seconds <= -1 ? "-" : "";
  const s = Math.floor(Math.abs(seconds));
  return `${sign}${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function minutes(value: number): string {
  const total = Math.round(value * 60);
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}
