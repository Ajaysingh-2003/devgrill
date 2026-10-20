"use client";

import { CircleCheck, CircleX, Zap } from "lucide-react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { cn } from "@devgrill/ui/lib/utils";
import { usePoll, useSource } from "../context";
import { formatBytes, formatPct } from "../model";

const POLL_MS = 5000;

export function CachePanel() {
  const { actions } = useSource();
  const poll = usePoll(actions.cache, POLL_MS);
  const data = poll.data;
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-cache"
      title="Cache"
      meta={poll.error ? `Last refresh failed: ${poll.error}` : "Redis-compatible cache, refreshed every 5 s"}
    >
      {!data ? (
        <EmptyState
          icon={Zap}
          title={poll.loading ? "Asking the cache…" : "The cache isn't answering"}
          compact
        >
          {poll.error ?? "Hit rate, memory and the keys the app asks for show here."}
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-px border-b border-border bg-border lg:grid-cols-4">
            {[
              [
                "Hit rate (since start)",
                data.stats.hit_rate === null ? "no reads yet" : formatPct(data.stats.hit_rate),
              ],
              [
                "Memory",
                `${formatBytes(data.stats.used_memory)}${data.stats.maxmemory ? ` / ${formatBytes(data.stats.maxmemory)}` : ""}`,
              ],
              ["Ops / s", data.stats.ops_per_sec.toLocaleString()],
              ["Keys", data.stats.keys.toLocaleString()],
            ].map(([k, v]) => (
              <div key={k} className="bg-surface px-4 py-3">
                <div className="text-caption text-fg-muted">{k}</div>
                <div className="font-mono text-heading-md font-semibold text-fg tabular-nums">{v}</div>
              </div>
            ))}
          </div>
          <div className="grid gap-px bg-border xl:grid-cols-2">
            <section aria-labelledby="keys-asked" className="bg-surface p-4">
              <h3 id="keys-asked" className="text-label font-semibold text-fg-muted">
                Keys the app asked for, last {data.window_s} s
              </h3>
              {data.asked.length === 0 ? (
                <p className="mt-2 text-body text-fg-muted">
                  No reads in that window. Is traffic reaching the app?
                </p>
              ) : (
                <ul className="mt-2 font-mono text-mono">
                  {data.asked.map((k) => (
                    <li key={k.key} className="flex items-center justify-between gap-3 py-0.5">
                      <span className="truncate text-fg">{k.key}</span>
                      <span className="flex shrink-0 items-center gap-3">
                        <span className="text-fg-muted tabular-nums">{k.count}×</span>
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 text-caption",
                            k.exists ? "text-success-text" : "text-warning-text",
                          )}
                        >
                          {k.exists ? (
                            <CircleCheck className="size-3.5" aria-hidden="true" />
                          ) : (
                            <CircleX className="size-3.5" aria-hidden="true" />
                          )}
                          {k.exists ? "stored" : "not in cache"}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="keys-stored" className="bg-surface p-4">
              <h3 id="keys-stored" className="text-label font-semibold text-fg-muted">
                A sample of stored keys
              </h3>
              {data.keys.length === 0 ? (
                <p className="mt-2 text-body text-fg-muted">The cache is empty.</p>
              ) : (
                <ul className="mt-2 font-mono text-mono">
                  {data.keys.map((k) => (
                    <li key={k.key} className="flex justify-between gap-3 py-0.5">
                      <span className="truncate text-fg">{k.key}</span>
                      <span className="shrink-0 text-fg-subtle tabular-nums">
                        {k.ttl < 0 ? "no TTL" : `expires in ${k.ttl} s`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </PanelFrame>
  );
}
