import type { WorkspaceOut } from "@devgrill/api-client";
import {
  CHARTS,
  CHART_TS,
  CODE_SAMPLE,
  INCIDENT,
  LOGS,
  TERMINAL_LINES,
  WAR_ROOM,
  scenario,
} from "@/lib/mock";
import {
  Store,
  parseLog,
  type IncidentEvent,
  type IncidentSnapshot,
  type LogsSnapshot,
  type TelemetrySnapshot,
  type TerminalLink,
  type WorkspaceSource,
} from "./model";

import { DEMO_ID } from "./ids";

export { DEMO_ID };

const encoder = new TextEncoder();

/** A shell that prints a canned session and echoes what you type. */
function fakeShell(): TerminalLink {
  const link: TerminalLink = {
    send: (data) => {
      const text = typeof data === "string" ? data : new TextDecoder().decode(data);
      if (text.startsWith("{")) return; // resize and ping control messages
      const echoed = text.replace(/\r/g, "\r\n$ ");
      queueMicrotask(() => link.onmessage?.(encoder.encode(echoed).buffer as ArrayBuffer));
    },
    close: () => link.onclose?.(1000, ""),
    onopen: null,
    onmessage: null,
    onclose: null,
  };
  setTimeout(() => {
    link.onopen?.();
    const session = TERMINAL_LINES.map((l) =>
      l.kind === "prompt" ? `$ ${l.text}` : l.text.replace(/\n/g, "\r\n"),
    )
      .join("\r\n")
      .concat("\r\n$ ");
    link.onmessage?.(encoder.encode(session).buffer as ArrayBuffer);
  }, 50);
  return link;
}

/** What the demo's verify reports: the cache fix holds, the price check catches staleness. */
const DEMO_PROBES = [
  { key: "sale-replay", title: "Sale traffic", status: "passed" as const, detail: "all targets met" },
  {
    key: "cache-serves-reads",
    title: "Cache does its job",
    status: "passed" as const,
    detail: "all targets met",
  },
  {
    key: "honest-metrics",
    title: "Metrics tell the truth",
    status: "passed" as const,
    detail: "all targets met",
  },
  { key: "correctness", title: "Still correct", status: "passed" as const, detail: "every check passed" },
  { key: "cold-cache", title: "Cold cache mid-sale", status: "passed" as const, detail: "all targets met" },
  {
    key: "price-freshness",
    title: "Prices stay fresh",
    status: "failed" as const,
    detail: "visible_after_s: not measured (the new price never showed)",
  },
  { key: "budget", title: "Within budget", status: "passed" as const, detail: "within budget" },
];

export function createDemoSource(): WorkspaceSource {
  const s = scenario(INCIDENT.scenario)!;
  const now = Date.now();
  const activeAt = now - 492_000;
  const info: WorkspaceOut = {
    attempt: {
      id: DEMO_ID,
      scenario_slug: s.slug,
      mode: "oncall",
      state: "active",
      started_at: new Date(activeAt - 30_000).toISOString(),
      active_at: new Date(activeAt).toISOString(),
      ended_at: null,
      expires_at: new Date(activeAt + 45 * 60_000).toISOString(),
    },
    scenario_title: s.title,
    track_slug: s.track,
    difficulty: "sev2",
    page: { severity: "SEV1", title: INCIDENT.page },
    unlocked_tools: ["overview", "logs", "terminal", "database", "cache", "code", "deploys", "war_room"],
    metrics: ["p99_latency_ms", "error_rate", "cache_hit_rate", "db_qps_product"],
    slo: { p99_latency_ms: { lt: 500 }, error_rate: { lt: 0.01 } },
    deployable: ["api"],
    hints_total: 3,
    hints: [],
    extend_minutes: 15,
    extends_left: 2,
    idle_minutes: 10,
    gateway_url: "",
  };

  const at = (mmss: string) => {
    const [m, sec] = mmss.split(":").map(Number);
    return new Date(activeAt + ((m ?? 0) * 60 + (sec ?? 0)) * 1000).toISOString();
  };
  const events: IncidentEvent[] = [
    { id: 1, type: "alert", ts: at("00:00"), payload: { severity: "SEV1", title: INCIDENT.page } },
    ...WAR_ROOM.filter((m) => m.role !== "alert").map((m, i) => ({
      id: 2 + i,
      type: m.who === "You" ? "message" : "beat",
      ts: at(m.at),
      payload:
        m.who === "You" ? { author: "you", text: m.text } : { persona: m.who.toLowerCase(), say: m.text },
    })),
    {
      id: 10,
      type: "action",
      ts: at("04:02"),
      payload: { verb: "restart", service: "postgres-db", source: "cli" },
    },
  ];
  const incident = new Store<IncidentSnapshot>({
    state: "active",
    activeAt,
    expiresAt: activeAt + 45 * 60_000,
    extendsLeft: 2,
    events,
    boot: [],
    hints: [],
    endedReason: null,
    events_connection: "open",
    eventsDownSince: null,
    verify: null,
  });

  const samples = CHART_TS.map((t, i) => ({
    t,
    values: {
      p99_latency_ms: CHARTS.latency[i] ?? null,
      error_rate: (CHARTS.errors[i] ?? 0) / 100,
      cache_hit_rate: (CHARTS.cacheHit[i] ?? 0) / 100,
      db_qps_product: Math.round(1200 * (1 - (CHARTS.cacheHit[i] ?? 0) / 100) + 20),
    },
  }));
  const telemetry = new Store<TelemetrySnapshot>({ samples, connection: "open", downSince: null });
  const logs = new Store<LogsSnapshot>({
    lines: LOGS.map((l) => parseLog(l.ts, l.service, l.message)).map((l, i) => ({
      ...l,
      level: LOGS[i]!.level,
    })),
    dropped: 0,
  });

  const files = { "app/cache.py": CODE_SAMPLE, "config/app.env": "CACHE_TTL_SECONDS=300\n" };
  const ok = async () => undefined;
  const actions: WorkspaceSource["actions"] = {
    status: async () => ({
      services: ["api", "postgres-db", "redis-db", "worker"].map((name) => ({
        name,
        state: "running",
        health: "healthy",
        restarts: name === "postgres-db" ? 1 : 0,
        oom_killed: false,
        started_at: null,
      })),
    }),
    files: async () => ({ service: "api", files: Object.keys(files) }),
    readFile: async (path) => files[path as keyof typeof files] ?? "",
    writeFile: ok,
    deploys: async () => ({
      service: "api",
      live: "a91f3c2",
      live_dirty: false,
      commits: [
        {
          sha: "a91f3c2",
          short: "a91f3c2",
          author: "rahul",
          at: activeAt / 1000 - 120,
          message: "refactor: add version prefix to cache keys",
        },
        {
          sha: "7bd21e0",
          short: "7bd21e0",
          author: "meera",
          at: activeAt / 1000 - 9000,
          message: "update product images",
        },
      ],
    }),
    deploy: async () => ({ ok: true, sha: "a91f3c2", message: "api a91f3c2 is live (demo)", log: "" }),
    rollback: async (ref) => ({ ok: true, sha: ref, message: `api ${ref} is live (demo)`, log: "" }),
    restart: async (service) => `${service} restarted (demo)`,
    db: async () => ({
      max_connections: 100,
      connections: [
        { state: "active", n: 96 },
        { state: "idle in transaction", n: 4 },
      ],
      top: [
        {
          query: "SELECT p.id, p.sku, p.name, ... FROM products p WHERE p.id = $1",
          calls: 184_302,
          mean_ms: 212.4,
          total_ms: 39_146_000,
          rows: 184_302,
        },
        {
          query: "SELECT id, sku, name, price_cents FROM products WHERE name ILIKE $1",
          calls: 2114,
          mean_ms: 14.2,
          total_ms: 30_018,
          rows: 21_140,
        },
      ],
      active: [],
    }),
    query: async () => ({ columns: ["count"], rows: [[18402]], truncated: false, ms: 3.1 }),
    cache: async () => ({
      stats: {
        hits: 1204,
        misses: 391_022,
        hit_rate: 0.003,
        ops_per_sec: 6120,
        used_memory: 92_000_000,
        maxmemory: 268_435_456,
        evicted_keys: 0,
        keys: 18_390,
        clients: 9,
      },
      keys: [
        { key: "product:1042", ttl: 211 },
        { key: "product:1043", ttl: 188 },
        { key: "product:2210", ttl: 240 },
      ],
      asked: [
        { key: "v2:product:1042", count: 12_384, exists: false },
        { key: "v2:product:1043", count: 9911, exists: false },
        { key: "v2:product:2210", count: 4402, exists: false },
      ],
      window_s: 1.5,
    }),
    hint: async () => {
      const tier = incident.get().hints.length + 1;
      const hint = {
        tier,
        text:
          [
            "Look at what the cache is doing for product reads.",
            "Compare the key the app reads with the key it writes.",
            "set() still writes key(); write with versioned_key() too, then deploy.",
          ][tier - 1] ?? "",
      };
      incident.set((s) => ({ ...s, hints: [...s.hints, hint] }));
      return hint;
    },
    message: async (text) => {
      incident.set((s) => ({
        ...s,
        events: [
          ...s.events,
          {
            id: s.events.length + 100,
            type: "message",
            ts: new Date().toISOString(),
            payload: { author: "you", text },
          },
        ],
      }));
    },
    mitigate: async () => ({ declared: true, real_state: "active", correct: false }),
    verify: async () => {
      // A canned run: every probe queued, then running, then the verdict.
      const probes = DEMO_PROBES.map((p) => ({ key: p.key, title: p.title, status: "queued" as const }));
      const runId = `demo-${Date.now()}`;
      incident.set((s) => ({ ...s, verify: { runId, probes, done: false, passed: null, error: null } }));
      window.setTimeout(() => {
        incident.set((s) => ({
          ...s,
          verify: s.verify && {
            ...s.verify,
            probes: s.verify.probes.map((p, i) => ({ ...p, status: i === 0 ? "running" : "queued" })),
          },
        }));
      }, 400);
      window.setTimeout(() => {
        incident.set((s) => ({
          ...s,
          verify: {
            runId,
            probes: DEMO_PROBES.map((p) => ({
              key: p.key,
              title: p.title,
              status: p.status,
              detail: p.detail,
            })),
            done: true,
            passed: false,
            error: null,
          },
        }));
      }, 1600);
    },
    extend: ok,
    reset: ok,
    abandon: ok,
    touch: ok,
    openTerminal: async () => fakeShell(),
  };

  return { kind: "demo", info, incident, telemetry, logs, actions, start: () => () => undefined };
}
