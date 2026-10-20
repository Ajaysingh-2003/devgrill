"use client";

import { ArrowDown, Pause, Play, ScrollText } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { useHotkey } from "@devgrill/ui/hooks/use-hotkey";
import { cn } from "@devgrill/ui/lib/utils";
import { useLogs } from "../context";
import type { LogEntry, LogLevel } from "../model";

const ROW = 22; // px; fixed height is what makes the list cheap to render
const OVERSCAN = 12;
const RANK: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };
const LEVEL: Record<LogLevel, { label: string; tone: string }> = {
  error: { label: "ERROR", tone: "text-danger-text" },
  warn: { label: "WARN", tone: "text-warning-text" },
  info: { label: "INFO", tone: "text-info-text" },
  debug: { label: "DEBUG", tone: "text-fg-subtle" },
};

/** `service:api level:warn timeout` -> a predicate (level means "at least"). */
function matcher(query: string): (line: LogEntry) => boolean {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const tests = words.map((word) => {
    const [key, value] = word.includes(":") ? (word.split(":", 2) as [string, string]) : ["", word];
    if (key === "service") return (l: LogEntry) => l.service.toLowerCase().includes(value);
    if (key === "level") {
      const min = RANK[value.replace(">=", "") as LogLevel] ?? 0;
      return (l: LogEntry) => RANK[l.level] >= min;
    }
    return (l: LogEntry) => l.message.toLowerCase().includes(word) || l.service.toLowerCase().includes(word);
  });
  return (line) => tests.every((t) => t(line));
}

const time = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour12: false });
};

export function LogsPanel() {
  const live = useLogs();
  const [frozen, setFrozen] = useState<LogEntry[] | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [follow, setFollow] = useState(true);
  const [viewport, setViewport] = useState({ top: 0, height: 400 });
  const scroller = useRef<HTMLDivElement>(null);
  const queryRef = useRef<HTMLInputElement>(null);

  const all = frozen ?? live.lines;
  const lines = useMemo(() => (query.trim() ? all.filter(matcher(query)) : all), [all, query]);
  // Where the reader left the bottom: lines beyond it are "new".
  const [anchor, setAnchor] = useState(0);
  const unseen = follow ? 0 : Math.max(0, lines.length - anchor);

  // `/` filters, `.` freezes the stream (spec §8.4): only when not typing elsewhere.
  useHotkey("/", (event) => {
    event.preventDefault();
    queryRef.current?.focus();
  });
  useHotkey(".", () => setFrozen((f) => (f ? null : live.lines)));

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () => setViewport({ top: el.scrollTop, height: el.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Stay at the bottom while following; never move the reader's place otherwise.
  useEffect(() => {
    const el = scroller.current;
    if (el && follow) el.scrollTop = el.scrollHeight;
  }, [lines.length, follow]);

  const first = Math.max(0, Math.floor(viewport.top / ROW) - OVERSCAN);
  const last = Math.min(lines.length, Math.ceil((viewport.top + viewport.height) / ROW) + OVERSCAN);
  const visible = lines.slice(first, last);
  const detail = selected === null ? null : (all.find((l) => l.id === selected) ?? null);

  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-logs"
      title="Logs"
      meta={
        frozen
          ? `Frozen at ${frozen.length} lines. Press . to resume.`
          : `${lines.length} lines${live.dropped ? `, ${live.dropped} dropped while catching up` : ""}`
      }
      actions={
        <button
          type="button"
          aria-pressed={frozen !== null}
          onClick={() => setFrozen((f) => (f ? null : live.lines))}
          className="inline-flex h-7 items-center gap-1.5 rounded-sm border border-border-input px-2 text-label font-medium text-fg hover:bg-raised"
        >
          {frozen ? (
            <Play className="size-3.5" aria-hidden="true" />
          ) : (
            <Pause className="size-3.5" aria-hidden="true" />
          )}
          {frozen ? "Resume" : "Freeze"}
        </button>
      }
      bodyClassName="flex flex-col"
    >
      <div className="border-b border-border px-3 py-2">
        <label htmlFor="log-query" className="sr-only">
          Log query
        </label>
        <input
          id="log-query"
          ref={queryRef}
          name="query"
          autoComplete="off"
          spellCheck={false}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter: timeout   service:api   level:warn…"
          className="h-8 w-full rounded-sm border border-border-input bg-surface px-2.5 font-mono text-mono text-fg placeholder:text-fg-subtle"
        />
      </div>
      {all.length === 0 ? (
        <EmptyState icon={ScrollText} title="No log lines yet" compact>
          Lines appear here as the services write them. The app logs slow and failed requests.
        </EmptyState>
      ) : (
        <div className="relative min-h-0 flex-1">
          <div
            ref={scroller}
            role="log"
            aria-label="Log lines"
            aria-live="off"
            tabIndex={0}
            aria-describedby="log-keys"
            onKeyDown={(e) => {
              // Arrow keys pick a line; its full text shows below.
              if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
              e.preventDefault();
              const index = lines.findIndex((l) => l.id === selected);
              const next =
                e.key === "ArrowDown" ? Math.min(lines.length - 1, index + 1) : Math.max(0, index - 1);
              const target = lines[index === -1 ? lines.length - 1 : next];
              if (!target) return;
              setSelected(target.id);
              const el = e.currentTarget;
              const y = lines.indexOf(target) * ROW;
              if (y < el.scrollTop || y > el.scrollTop + el.clientHeight - ROW)
                el.scrollTop = y - el.clientHeight / 2;
            }}
            onScroll={(e) => {
              const el = e.currentTarget;
              setViewport({ top: el.scrollTop, height: el.clientHeight });
              const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < ROW * 2;
              if (follow && !atBottom) setAnchor(lines.length);
              setFollow(atBottom);
            }}
            className="h-full overflow-auto font-mono text-mono"
            data-hotkeys="off"
          >
            <div style={{ height: lines.length * ROW, position: "relative" }}>
              {visible.map((line, i) => (
                <button
                  key={line.id}
                  type="button"
                  onClick={() => setSelected(line.id === selected ? null : line.id)}
                  aria-pressed={line.id === selected}
                  tabIndex={-1}
                  style={{ position: "absolute", top: (first + i) * ROW, height: ROW, left: 0, right: 0 }}
                  className={cn(
                    "flex items-center gap-3 overflow-hidden px-3 text-left whitespace-nowrap hover:bg-raised",
                    line.id === selected && "bg-brand-subtle",
                  )}
                >
                  <span className="text-fg-subtle tabular-nums">{time(line.ts)}</span>
                  <span className={cn("w-12 shrink-0 font-semibold", LEVEL[line.level].tone)}>
                    {LEVEL[line.level].label}
                  </span>
                  <span className="w-24 shrink-0 truncate text-fg-muted">{line.service}</span>
                  <span className="truncate text-fg">{line.message}</span>
                </button>
              ))}
            </div>
          </div>
          <p id="log-keys" className="sr-only">
            Use the up and down arrow keys to select a line and read it in full.
          </p>
          {unseen > 0 ? (
            <button
              type="button"
              onClick={() => {
                setFollow(true);
                const el = scroller.current;
                if (el) el.scrollTop = el.scrollHeight;
              }}
              className="absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-brand px-3 py-1 text-label font-semibold text-on-brand shadow-md"
            >
              <ArrowDown className="size-3.5" aria-hidden="true" />
              {unseen} new {unseen === 1 ? "line" : "lines"}
            </button>
          ) : null}
        </div>
      )}
      {detail ? (
        <section
          aria-label="Selected log line"
          className="max-h-40 shrink-0 overflow-auto border-t border-border bg-sunken p-3"
        >
          <p className="text-caption text-fg-subtle">
            {detail.service}, {time(detail.ts)}
          </p>
          <pre className="mt-1 font-mono text-mono-sm whitespace-pre-wrap text-fg">{detail.raw}</pre>
        </section>
      ) : null}
    </PanelFrame>
  );
}
