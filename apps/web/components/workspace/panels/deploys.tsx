"use client";

import type { DeployOut } from "@devgrill/api-client";
import { CircleCheck, CircleX, GitBranch, RefreshCw, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { StatusPill } from "@devgrill/ui/components/devgrill/status-pill";
import { cn } from "@devgrill/ui/lib/utils";
import { useAction, useIncident, usePoll, useSource } from "../context";

const ago = (unix: number) => {
  const minutes = Math.max(0, Math.round((Date.now() / 1000 - unix) / 60));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 48) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / 1440)} days ago`;
};

export function DeploysPanel() {
  const { actions, info } = useSource();
  const { events } = useIncident();
  const service = info.deployable[0];
  // Refresh whenever a deploy or rollback lands (from here, the editor or the CLI).
  const changes = events.filter((e) => e.type === "deploy" || e.type === "rollback").length;
  const history = usePoll(() => actions.deploys(service), null);
  const { refresh } = history;
  useEffect(() => {
    if (changes > 0) refresh();
  }, [changes, refresh]);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [result, setResult] = useState<DeployOut | null>(null);
  const rollback = useAction(async (sha: string) => {
    setResult(null);
    const out = await actions.rollback(sha, service);
    setResult(out);
    setConfirm(null);
    history.refresh();
  });

  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-deploys"
      title="Deploys"
      meta={service ? `${service}, newest first` : undefined}
    >
      {!service ? null : !history.data ? (
        <EmptyState
          icon={GitBranch}
          title={history.loading ? "Reading the deploy history…" : "No history"}
          compact
        >
          {history.error ?? "Deploys of this service show here."}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-border">
          {history.data.commits.map((c) => {
            const live = c.sha === history.data!.live;
            return (
              <li key={c.sha} className="flex items-center gap-4 px-4 py-3">
                <code className="font-mono text-mono text-brand-text">{c.short}</code>
                <span className="w-24 shrink-0 font-mono text-mono-sm text-fg-subtle">{ago(c.at)}</span>
                <span className="min-w-0 flex-1 text-body text-fg">
                  {c.message} <span className="text-fg-subtle">by {c.author}</span>
                </span>
                {live ? (
                  <StatusPill
                    status="healthy"
                    label={history.data!.live_dirty ? "Live, with uncommitted changes" : "Live"}
                  />
                ) : confirm === c.sha ? (
                  <span className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void rollback.run(c.sha)}
                      disabled={rollback.busy}
                      className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-brand px-2.5 text-label font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
                    >
                      {rollback.busy ? "Rolling back…" : `Deploy ${c.short} now`}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirm(null)}
                      className="h-8 rounded-sm px-2 text-label text-fg-muted hover:bg-raised"
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirm(c.sha)}
                    className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border-input px-2.5 text-label font-medium text-fg hover:bg-raised"
                  >
                    <RotateCcw className="size-3.5" aria-hidden="true" />
                    Roll back to {c.short}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <div aria-live="polite">
        {rollback.error ? <p className="px-4 py-2 text-body text-danger-text">{rollback.error}</p> : null}
        {result ? (
          <p
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-body font-medium",
              result.ok ? "text-success-text" : "text-danger-text",
            )}
          >
            {result.ok ? (
              <CircleCheck className="size-4" aria-hidden="true" />
            ) : (
              <CircleX className="size-4" aria-hidden="true" />
            )}
            {result.message}
          </p>
        ) : null}
      </div>
      <Services />
    </PanelFrame>
  );
}

function Services() {
  const { actions } = useSource();
  const status = usePoll(actions.status, 10_000);
  const [done, setDone] = useState<string | null>(null);
  const restart = useAction(async (service: string) => {
    setDone(await actions.restart(service));
    status.refresh();
  });
  return (
    <section aria-labelledby="services-title" className="border-t border-border p-4">
      <h3 id="services-title" className="text-label font-semibold text-fg-muted">
        Services
      </h3>
      {status.data ? (
        <ul className="mt-2 divide-y divide-border">
          {status.data.services.map((s) => (
            <li key={s.name} className="flex items-center gap-3 py-2">
              <span className="w-40 font-mono text-mono text-fg">{s.name}</span>
              <StatusPill
                status={s.state !== "running" ? "firing" : s.health === "unhealthy" ? "degraded" : "healthy"}
                label={s.state !== "running" ? (s.state ?? "stopped") : (s.health ?? "running")}
              />
              <span className="text-caption text-fg-subtle">
                {s.restarts ? `${s.restarts} restarts` : ""}
                {s.oom_killed ? " (out of memory)" : ""}
              </span>
              <button
                type="button"
                onClick={() => void restart.run(s.name)}
                disabled={restart.busy}
                className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-sm px-2 text-label font-medium text-fg-muted hover:bg-raised hover:text-fg disabled:opacity-60"
              >
                <RefreshCw className="size-3.5" aria-hidden="true" />
                Restart <span className="sr-only">{s.name}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-body text-fg-muted">{status.error ?? "Checking services…"}</p>
      )}
      <p aria-live="polite" className="mt-1 text-caption text-fg-muted">
        {restart.error ?? done ?? ""}
      </p>
    </section>
  );
}
