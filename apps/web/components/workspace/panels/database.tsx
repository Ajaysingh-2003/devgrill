"use client";

import type { DbInsightsOut, QueryOut } from "@devgrill/api-client";
import { Database, Play, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { cn } from "@devgrill/ui/lib/utils";
import { useAction, usePoll, useSource } from "../context";

const POLL_MS = 5000;

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="bg-surface px-4 py-3">
      <div className="text-caption text-fg-muted">{label}</div>
      <div className={cn("font-mono text-heading-md font-semibold text-fg tabular-nums", tone)}>{value}</div>
    </div>
  );
}

export function DatabasePanel() {
  const { actions } = useSource();
  const previous = useRef<{ at: number; calls: Map<string, number> } | null>(null);
  const [rates, setRates] = useState<Map<string, number>>(new Map());
  const poll = usePoll(async () => {
    const data = await actions.db();
    // Calls per second between two polls: what is busy *now*, not since the start.
    const now = Date.now();
    const calls = new Map(data.top.map((t) => [t.query, t.calls]));
    const prev = previous.current;
    if (prev) {
      const seconds = (now - prev.at) / 1000;
      setRates(
        new Map(
          data.top.map((t) => [
            t.query,
            Math.max(0, (t.calls - (prev.calls.get(t.query) ?? t.calls)) / seconds),
          ]),
        ),
      );
    }
    previous.current = { at: now, calls };
    return data;
  }, POLL_MS);
  const data: DbInsightsOut | null = poll.data;
  const total = data?.connections.reduce((n, c) => n + c.n, 0) ?? 0;
  const blocked = data?.active.filter((a) => a.blocked_by.length > 0) ?? [];

  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-database"
      title="Database"
      meta={poll.error ? `Last refresh failed: ${poll.error}` : "Postgres, refreshed every 5 s"}
    >
      {!data ? (
        <EmptyState
          icon={Database}
          title={poll.loading ? "Asking Postgres…" : "Postgres isn't answering"}
          compact
        >
          {poll.error ?? "Statements, connections and locks show here."}
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-px border-b border-border bg-border">
            <Tile
              label="Connections"
              value={`${total} / ${data.max_connections}`}
              tone={total > data.max_connections * 0.8 ? "text-warning-text" : undefined}
            />
            <Tile label="Running now" value={String(data.active.length)} />
            <Tile
              label="Waiting on a lock"
              value={String(blocked.length)}
              tone={blocked.length ? "text-danger-text" : undefined}
            />
          </div>
          <table className="w-full text-left font-mono text-mono">
            <caption className="px-4 pt-3 text-left text-label font-semibold text-fg-muted">
              Busiest statements (pg_stat_statements)
            </caption>
            <thead>
              <tr className="border-b border-border text-caption text-fg-subtle">
                <th scope="col" className="px-4 py-2 font-medium">
                  Statement
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Calls/s
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
              {data.top.map((t) => (
                <tr key={t.query} className="border-b border-border align-top last:border-b-0">
                  <td className="max-w-0 truncate px-4 py-2 text-fg" title={t.query}>
                    {t.query}
                  </td>
                  <td className="px-4 py-2 text-right text-warning-text tabular-nums">
                    {rates.has(t.query) ? rates.get(t.query)!.toFixed(1) : "…"}
                  </td>
                  <td className="px-4 py-2 text-right text-fg tabular-nums">{t.calls.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right text-fg tabular-nums">{t.mean_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.active.length ? (
            <table className="mt-2 w-full text-left font-mono text-mono">
              <caption className="px-4 pt-3 text-left text-label font-semibold text-fg-muted">
                Running now
              </caption>
              <thead>
                <tr className="border-b border-border text-caption text-fg-subtle">
                  <th scope="col" className="px-4 py-2 font-medium">
                    pid
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    For
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Waiting on
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Statement
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.active.map((a) => (
                  <tr key={a.pid} className="border-b border-border align-top last:border-b-0">
                    <td className="px-4 py-2 text-fg tabular-nums">{a.pid}</td>
                    <td className="px-4 py-2 text-fg tabular-nums">{a.seconds ?? "?"} s</td>
                    <td className="px-4 py-2">
                      {a.blocked_by.length ? (
                        <span className="inline-flex items-center gap-1 text-danger-text">
                          <TriangleAlert className="size-3.5" aria-hidden="true" />
                          blocked by {a.blocked_by.join(", ")}
                        </span>
                      ) : (
                        <span className="text-fg-muted">{a.wait_event ?? "nothing"}</span>
                      )}
                    </td>
                    <td className="max-w-0 truncate px-4 py-2 text-fg" title={a.query ?? ""}>
                      {a.query}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </>
      )}
      <QueryConsole />
    </PanelFrame>
  );
}

function QueryConsole() {
  const { actions } = useSource();
  const [sql, setSql] = useState("SELECT count(*) FROM products");
  const [result, setResult] = useState<QueryOut | null>(null);
  const query = useAction(actions.query);
  const run = async () => {
    const out = await query.run(sql);
    if (out) setResult(out);
  };
  return (
    <section aria-labelledby="console-title" className="border-t border-border p-4">
      <h3 id="console-title" className="text-label font-semibold text-fg-muted">
        Read-only query console
      </h3>
      <form
        className="mt-2 flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <label htmlFor="sql" className="sr-only">
          SQL
        </label>
        <textarea
          id="sql"
          rows={3}
          value={sql}
          spellCheck={false}
          onChange={(e) => setSql(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              void run();
            }
          }}
          className="rounded-sm border border-border-input bg-sunken px-2.5 py-2 font-mono text-mono text-fg"
        />
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={query.busy || !sql.trim()}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-brand px-3 text-label font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
          >
            <Play className="size-3.5" aria-hidden="true" />
            {query.busy ? "Running…" : "Run"}
          </button>
          <span className="text-caption text-fg-subtle">
            Ctrl+Enter. Read-only role, 5 s timeout, 200 rows.
          </span>
        </div>
      </form>
      <div aria-live="polite">
        {query.error ? <p className="mt-3 text-body text-danger-text">{query.error}</p> : null}
        {result?.error ? <p className="mt-3 font-mono text-mono text-danger-text">{result.error}</p> : null}
        {result && !result.error ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left font-mono text-mono">
              <caption className="sr-only">Query result</caption>
              <thead>
                <tr className="border-b border-border text-caption text-fg-subtle">
                  {(result.columns ?? []).map((c) => (
                    <th key={c} scope="col" className="px-2 py-1 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(result.rows ?? []).map((row, i) => (
                  <tr key={i} className="border-b border-border last:border-b-0">
                    {row.map((cell, j) => (
                      <td key={j} className="px-2 py-1 text-fg">
                        {cell === null ? "NULL" : String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-caption text-fg-subtle">
              {result.rows?.length ?? 0} rows{result.truncated ? " (first 200)" : ""} in {result.ms} ms
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
