"use client";

import { RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { LogView } from "@devgrill/ui/components/devgrill/log-view";
import { MetricChart } from "@devgrill/ui/components/devgrill/metric-chart";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { StatusPill } from "@devgrill/ui/components/devgrill/status-pill";
import { CHARTS, CHART_TS, CODE_SAMPLE, LOGS, TERMINAL_LINES } from "@/lib/mock";

const markers = [
  { at: CHARTS.deployAt, label: "deploy" },
  { at: CHARTS.saleAt, label: "sale" },
];

export function OverviewPanel() {
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-overview"
      title="Overview"
      meta="product-api and its dependencies, last 60 minutes"
    >
      <div className="grid gap-x-6 gap-y-5 p-4 xl:grid-cols-2">
        <MetricChart
          title="p99 latency"
          summary="Rose from about 120 ms to 4.2 s right after 20:00; the target is 500 ms."
          timestamps={CHART_TS}
          series={[{ label: "p99", values: CHARTS.latency, color: 7 }]}
          format={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`)}
          threshold={{ value: 500, label: "SLO 500 ms" }}
          markers={markers}
          syncKey="incident"
          height={170}
        />
        <MetricChart
          title="Error rate"
          summary="Jumped from 0.2% to 18% at 20:00."
          timestamps={CHART_TS}
          series={[{ label: "5xx", values: CHARTS.errors, color: 4 }]}
          format={(v) => `${v.toFixed(v < 1 ? 1 : 0)}%`}
          threshold={{ value: 1, label: "1%" }}
          markers={markers}
          syncKey="incident"
          height={170}
        />
        <MetricChart
          title="Postgres CPU"
          summary="Climbed from 34% to 97% at 20:00."
          timestamps={CHART_TS}
          series={[{ label: "cpu", values: CHARTS.dbCpu, color: 5 }]}
          format={(v) => `${Math.round(v)}%`}
          markers={markers}
          syncKey="incident"
          height={170}
        />
        <MetricChart
          title="Cache hit rate"
          summary="Fell from 95% to 3% just after the 19:58 deploy, before the sale started."
          timestamps={CHART_TS}
          series={[{ label: "hit rate", values: CHARTS.cacheHit, color: 1 }]}
          format={(v) => `${Math.round(v)}%`}
          markers={markers}
          syncKey="incident"
          height={170}
        />
      </div>
    </PanelFrame>
  );
}

export function LogsPanel() {
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-logs"
      title="Logs"
      meta="service:product-api level ≥ info, last 15 minutes"
    >
      <div className="border-b border-border px-3 py-2">
        <label htmlFor="log-query" className="sr-only">
          Log query
        </label>
        <input
          id="log-query"
          name="query"
          autoComplete="off"
          spellCheck={false}
          defaultValue="service:product-api level>=info"
          className="h-8 w-full rounded-sm border border-border-input bg-surface px-2.5 font-mono text-mono text-fg"
        />
      </div>
      <LogView lines={LOGS} className="py-1" />
    </PanelFrame>
  );
}

export function DatabasePanel() {
  const rows = [
    ["SELECT * FROM products WHERE id = $1", "184,302", "212.4"],
    ["SELECT * FROM inventory WHERE product_id = $1", "181,977", "198.7"],
    ["SELECT * FROM reviews WHERE product_id = $1", "2,114", "14.2"],
  ];
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-database"
      title="Database"
      meta="Postgres 18, top queries by calls, last 5 minutes"
      actions={<StatusPill status="degraded" />}
    >
      <div className="grid grid-cols-3 gap-px border-b border-border bg-border">
        {[
          ["CPU", "97%"],
          ["Connections", "100 / 100"],
          ["Waiting for a connection", "812"],
        ].map(([k, v]) => (
          <div key={k} className="bg-surface px-4 py-3">
            <div className="text-caption text-fg-muted">{k}</div>
            <div className="font-mono text-heading-md font-semibold text-fg tabular-nums">{v}</div>
          </div>
        ))}
      </div>
      <table className="w-full text-left font-mono text-mono">
        <caption className="sr-only">Top queries by calls</caption>
        <thead>
          <tr className="border-b border-border text-caption text-fg-subtle">
            <th scope="col" className="px-4 py-2 font-medium">
              Query
            </th>
            <th scope="col" className="px-4 py-2 text-right font-medium">
              Calls
            </th>
            <th scope="col" className="px-4 py-2 text-right font-medium">
              Mean ms
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([q, calls, ms]) => (
            <tr key={q} className="border-b border-border last:border-b-0">
              <td className="px-4 py-2 text-fg">{q}</td>
              <td className="px-4 py-2 text-right text-warning-text tabular-nums">{calls}</td>
              <td className="px-4 py-2 text-right text-fg tabular-nums">{ms}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelFrame>
  );
}

export function CachePanel() {
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-cache"
      title="Cache"
      meta="Redis, keyspace and the keys the app asks for"
    >
      <div className="grid grid-cols-2 gap-px border-b border-border bg-border lg:grid-cols-4">
        {[
          ["Hit rate", "3%"],
          ["Memory", "88 MB / 1 GB"],
          ["Ops / s", "6,120"],
          ["Evictions", "0"],
        ].map(([k, v]) => (
          <div key={k} className="bg-surface px-4 py-3">
            <div className="text-caption text-fg-muted">{k}</div>
            <div className="font-mono text-heading-md font-semibold text-fg tabular-nums">{v}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-px bg-border xl:grid-cols-2">
        <section aria-labelledby="keys-stored" className="bg-surface p-4">
          <h3 id="keys-stored" className="text-label font-semibold text-fg-muted">
            Keys in Redis
          </h3>
          <ul className="mt-2 font-mono text-mono text-fg">
            {["product:1042", "product:1043", "product:2210", "product:0007"].map((k) => (
              <li key={k} className="py-0.5">
                {k}
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="keys-missed" className="bg-surface p-4">
          <h3 id="keys-missed" className="text-label font-semibold text-fg-muted">
            Keys the app missed, last 60 s
          </h3>
          <ul className="mt-2 font-mono text-mono">
            {[
              ["v2:product:1042", "12,384"],
              ["v2:product:1043", "9,911"],
              ["v2:product:2210", "4,402"],
            ].map(([k, n]) => (
              <li key={k} className="flex justify-between py-0.5">
                <span className="text-fg">{k}</span>
                <span className="text-warning-text tabular-nums">{n}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </PanelFrame>
  );
}

export function CodePanel() {
  const lines = CODE_SAMPLE.split("\n");
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-code"
      title="Code"
      meta="product-api/app/product_service.py"
      actions={
        <button
          type="button"
          className="h-7 rounded-sm bg-brand px-2.5 text-label font-semibold text-on-brand hover:bg-brand-hover"
        >
          Deploy
        </button>
      }
    >
      <pre className="overflow-x-auto py-3 font-mono text-mono leading-6" data-hotkeys="off">
        {lines.map((line, i) => (
          <div key={i} className="grid grid-cols-[3rem_1fr] hover:bg-raised">
            <span className="pr-3 text-right text-fg-subtle select-none">{i + 1}</span>
            <code className="pr-4 text-fg">{line || " "}</code>
          </div>
        ))}
      </pre>
    </PanelFrame>
  );
}

export function DeploysPanel() {
  const deploys = [
    {
      sha: "a91f3c2",
      at: "19:58",
      msg: "refactor: add version prefix to cache keys",
      by: "rahul",
      live: true,
    },
    { sha: "7bd21e0", at: "17:30", msg: "update product images", by: "meera", live: false },
    { sha: "3c0e9aa", at: "yesterday", msg: "bump redis client to 5.0.1", by: "arjun", live: false },
  ];
  return (
    <PanelFrame id="tool-panel" tab="tool-deploys" title="Deploys" meta="product-api">
      <ul className="divide-y divide-border">
        {deploys.map((d) => (
          <li key={d.sha} className="flex items-center gap-4 px-4 py-3">
            <code className="font-mono text-mono text-brand-text">{d.sha}</code>
            <time className="w-20 font-mono text-mono-sm text-fg-subtle">{d.at}</time>
            <span className="flex-1 text-body text-fg">
              {d.msg} <span className="text-fg-subtle">by {d.by}</span>
            </span>
            {d.live ? (
              <>
                <StatusPill status="healthy" label="Live" />
                <button
                  type="button"
                  onClick={() =>
                    toast("Rollback starts in phase 4", {
                      description: "The workspace is a design shell in phase 1.",
                    })
                  }
                  className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border-input px-2.5 text-label font-medium text-fg hover:bg-raised"
                >
                  <RotateCcw className="size-3.5" aria-hidden="true" />
                  Roll back to 7bd21e0
                </button>
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}

export function TerminalPanel() {
  return (
    <PanelFrame id="terminal" title="Terminal" meta="you@inc-4021-sandbox" bodyClassName="bg-sunken">
      <div className="p-3 font-mono text-mono leading-6" data-hotkeys="off">
        {TERMINAL_LINES.map((line, i) =>
          line.kind === "prompt" ? (
            <div key={i} className="mt-2 text-fg first:mt-0">
              <span className="text-success-text">$ </span>
              {line.text}
            </div>
          ) : (
            <pre key={i} className="whitespace-pre-wrap text-fg-muted">
              {line.text}
            </pre>
          ),
        )}
        <div className="mt-2 flex items-center text-fg">
          <span className="text-success-text">$&nbsp;</span>
          <span aria-hidden="true" className="inline-block h-4 w-2 bg-fg" />
          <span className="sr-only">Terminal ready. A real shell connects in phase 4.</span>
        </div>
      </div>
    </PanelFrame>
  );
}
