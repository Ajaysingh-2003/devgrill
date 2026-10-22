import type {
  CacheOut,
  DbInsightsOut,
  DeployHistoryOut,
  DeployOut,
  FilesOut,
  HintOut,
  MitigationOut,
  QueryOut,
  StatusOut,
  WorkspaceOut,
} from "@devgrill/api-client";
import { useSyncExternalStore } from "react";

/**
 * The incident workspace's data, behind one interface with two implementations:
 * - live: the API (through the same-origin proxy), the SSE event stream and the gateway's
 *   terminal and telemetry WebSockets;
 * - demo: canned data, for the design shell, accessibility and keyboard tests without Docker.
 * Panels only ever see this interface.
 */

export type IncidentState =
  "provisioning" | "active" | "mitigated" | "verifying" | "resolved" | "abandoned" | "expired" | "failed";

export const ENDED: ReadonlySet<IncidentState> = new Set(["resolved", "abandoned", "expired", "failed"]);

export type IncidentEvent = {
  id: number;
  type: string;
  /** ISO timestamp from the server. */
  ts: string;
  payload: Record<string, unknown>;
};

export type Sample = { t: number; values: Record<string, number | null> };

export type LogLevel = "error" | "warn" | "info" | "debug";
export type LogEntry = {
  id: number;
  ts: string;
  service: string;
  level: LogLevel;
  message: string;
  raw: string;
};

export type Connection = "connecting" | "open" | "reconnecting" | "closed";

export type IncidentSnapshot = {
  state: IncidentState;
  activeAt: number | null;
  expiresAt: number | null;
  extendsLeft: number;
  events: IncidentEvent[];
  /** Boot steps seen so far, in order. */
  boot: string[];
  hints: HintOut[];
  endedReason: string | null;
  events_connection: Connection;
  /** When the event stream started reconnecting (ms), null while connected. */
  eventsDownSince: number | null;
  /** The latest verify run, probe by probe (ADR 015); null before the first one. */
  verify: VerifyProgress | null;
  /** A teammate's reply as it is written, and why teammates went quiet (ADR 016). */
  assist: AssistState;
};

export type AssistState = {
  typing: { id: string; persona: string; text: string } | null;
  /** "Teammates are busy" and similar, until the next reply. */
  notice: string | null;
};

export const NO_ASSIST: AssistState = { typing: null, notice: null };

/** Fold one live `assist` event (not stored, not replayed) into the assist state. */
export function reduceAssist(state: AssistState, p: Record<string, unknown>): AssistState {
  const id = String(p.id ?? "");
  switch (p.kind) {
    case "typing":
      return { typing: { id, persona: String(p.persona ?? ""), text: "" }, notice: null };
    case "delta":
      return state.typing?.id === id
        ? { ...state, typing: { ...state.typing, text: state.typing.text + String(p.text ?? "") } }
        : state;
    case "reset":
      return state.typing?.id === id ? { ...state, typing: { ...state.typing, text: "" } } : state;
    case "done":
      return state.typing?.id === id ? { ...state, typing: null } : state;
    case "busy":
      return { typing: null, notice: String(p.text ?? "Your teammates are busy right now.") };
    default:
      return state;
  }
}

export type ProbeStatus = "queued" | "running" | "passed" | "failed" | "skipped";

export type VerifyProgress = {
  runId: string;
  probes: { key: string; title: string; status: ProbeStatus; detail?: string }[];
  done: boolean;
  passed: boolean | null;
  /** Set when verify couldn't finish on our side (the run doesn't count). */
  error: string | null;
};

export type TelemetrySnapshot = {
  samples: Sample[];
  connection: Connection;
  /** When the telemetry socket started reconnecting (ms), null while connected. */
  downSince: number | null;
};

export type LogsSnapshot = { lines: LogEntry[]; dropped: number };

/** What the terminal panel needs from a connection (a WebSocket, or the demo's fake). */
export interface TerminalLink {
  send(data: string | Uint8Array): void;
  close(): void;
  onopen: (() => void) | null;
  onmessage: ((data: string | ArrayBuffer) => void) | null;
  onclose: ((code: number, reason: string) => void) | null;
}

export interface WorkspaceActions {
  status(): Promise<StatusOut>;
  files(service?: string): Promise<FilesOut>;
  readFile(path: string, service?: string): Promise<string>;
  writeFile(path: string, content: string, service?: string): Promise<void>;
  deploys(service?: string): Promise<DeployHistoryOut>;
  deploy(service?: string): Promise<DeployOut>;
  rollback(ref: string, service?: string): Promise<DeployOut>;
  restart(service: string): Promise<string>;
  db(): Promise<DbInsightsOut>;
  query(sql: string): Promise<QueryOut>;
  cache(): Promise<CacheOut>;
  hint(): Promise<HintOut>;
  /** Guided practice: a nudge toward the next step (AI); free, unlike hints. */
  nudge(): Promise<string>;
  message(text: string): Promise<void>;
  mitigate(): Promise<MitigationOut>;
  verify(): Promise<void>;
  extend(): Promise<void>;
  reset(): Promise<void>;
  abandon(): Promise<void>;
  /** Activity: keeps the idle timeout from ending an incident someone is playing. */
  touch(): Promise<void>;
  openTerminal(cols: number, rows: number): Promise<TerminalLink>;
}

export interface WorkspaceSource {
  kind: "live" | "demo";
  info: WorkspaceOut;
  incident: Store<IncidentSnapshot>;
  telemetry: Store<TelemetrySnapshot>;
  logs: Store<LogsSnapshot>;
  actions: WorkspaceActions;
  /** Start streams (returns a cleanup). */
  start(): () => void;
}

/** A tiny external store: panels subscribe to the slice they draw, nothing else re-renders. */
export class Store<T> {
  private listeners = new Set<() => void>();
  constructor(private value: T) {}

  get = (): T => this.value;

  set(next: T | ((prev: T) => T)): void {
    this.value = typeof next === "function" ? (next as (prev: T) => T)(this.value) : next;
    for (const listener of this.listeners) listener();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
}

export function useStore<T>(store: Store<T>): T {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

/** Keep the newest `max` items (ring buffer semantics, new array for React). */
export function appendCapped<T>(items: T[], more: T[], max: number): T[] {
  const next = items.length + more.length > max ? [...items, ...more].slice(-max) : [...items, ...more];
  return next;
}

// --------------------------------------------------------------------------- log parsing

let nextLogId = 1;

/** ShopKart logs JSON lines ({"level", "msg", ...}); datastores log plain text. */
export function parseLog(ts: string, service: string, raw: string): LogEntry {
  let level: LogLevel = "info";
  let message = raw;
  if (raw.startsWith("{")) {
    try {
      const data = JSON.parse(raw) as Record<string, unknown>;
      const lvl = String(data.level ?? data.levelname ?? "info").toLowerCase();
      level =
        lvl.startsWith("err") || lvl === "critical"
          ? "error"
          : lvl.startsWith("warn")
            ? "warn"
            : lvl === "debug"
              ? "debug"
              : "info";
      const extras = Object.entries(data)
        .filter(([k]) => k.startsWith("x_"))
        .map(([k, v]) => `${k.slice(2)}=${typeof v === "string" ? v : JSON.stringify(v)}`);
      message = [String(data.msg ?? data.message ?? raw), ...extras].join(" ");
    } catch {
      // not JSON after all: keep the raw line
    }
  } else if (/\b(ERROR|FATAL|PANIC)\b/.test(raw)) {
    level = "error";
  } else if (/\bWARN(ING)?\b/.test(raw)) {
    level = "warn";
  }
  return { id: nextLogId++, ts, service, level, message, raw };
}

// ---------------------------------------------------------------------------- formatting

export function formatMs(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)} s` : `${Math.round(value)} ms`;
}

export function formatPct(value: number): string {
  const pct = value * 100;
  return `${pct >= 10 || pct === 0 ? Math.round(pct) : pct.toFixed(1)}%`;
}

export function formatBytes(value: number): string {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value >= 1024 ** 2) return `${Math.round(value / 1024 ** 2)} MB`;
  return `${Math.round(value / 1024)} KB`;
}

/** mm:ss since the page (activeAt), for the timeline and the clock. */
export function sinceStart(at: number, activeAt: number | null): string {
  const seconds = Math.max(0, Math.round((at - (activeAt ?? at)) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
