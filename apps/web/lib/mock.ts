/**
 * Phase 1 mock content. Realistic copy so templates are judged on real words; replaced by
 * API data from phase 2 (catalog) and phases 3–6 (incident data).
 */
import type { Approach } from "@devgrill/ui/components/devgrill/approach-list";
import type { BootStep } from "@devgrill/ui/components/devgrill/boot-sequence";
import type { TimelineEvent } from "@devgrill/ui/components/devgrill/incident-timeline";
import type { LogLine } from "@devgrill/ui/components/devgrill/log-view";
import type { Probe } from "@devgrill/ui/components/devgrill/probe-table";
import type { Severity, ServiceKind } from "@devgrill/ui/icons";

export type Track = {
  slug: string;
  name: string;
  service: ServiceKind;
  summary: string;
  topics: string[];
  solved: number;
  total: number;
  rating: number;
};

export const TRACKS: Track[] = [
  {
    slug: "databases",
    name: "Databases",
    service: "db",
    summary: "Most outages end at the database. Tell a slow query from a starved pool.",
    topics: ["Indexes", "Connection pools", "Locks", "Migrations", "Replication"],
    solved: 6,
    total: 14,
    rating: 1412,
  },
  {
    slug: "caching",
    name: "Caching",
    service: "cache",
    summary: "Caches hide problems until the moment they stop working.",
    topics: ["Stampedes", "Invalidation", "Hot keys", "Eviction"],
    solved: 4,
    total: 11,
    rating: 1340,
  },
  {
    slug: "queues",
    name: "Queues and async",
    service: "queue",
    summary: "Nothing is down, yet nothing is happening.",
    topics: ["Poison messages", "Consumer lag", "Idempotency", "Retries"],
    solved: 2,
    total: 9,
    rating: 1268,
  },
  {
    slug: "concurrency",
    name: "Concurrency",
    service: "worker",
    summary: "Bugs that vanish when you add a print statement.",
    topics: ["Race conditions", "Deadlocks", "Double spend"],
    solved: 1,
    total: 7,
    rating: 1190,
  },
  {
    slug: "memory",
    name: "Memory and CPU",
    service: "api",
    summary: "Read the shape of a graph and know what the process is doing.",
    topics: ["Leaks", "Runaway regex", "Thread starvation"],
    solved: 3,
    total: 8,
    rating: 1301,
  },
  {
    slug: "networking",
    name: "Networking",
    service: "lb",
    summary: "One slow dependency decides whether everything else falls over too.",
    topics: ["Timeouts", "Retry storms", "DNS", "Circuit breakers"],
    solved: 0,
    total: 8,
    rating: 1200,
  },
];

export type ScenarioStatus = "solved" | "attempted" | "new";
export type Scenario = {
  slug: string;
  track: string;
  topic: string;
  title: string;
  symptom: string;
  sev: Severity;
  minutes: number;
  solveRate: number;
  status: ScenarioStatus;
};

export const SCENARIOS: Scenario[] = [
  {
    slug: "big-sale-meltdown",
    track: "caching",
    topic: "Stampedes",
    title: "The Big Sale Meltdown",
    symptom: "Product pages die the minute a sale starts",
    sev: 2,
    minutes: 25,
    solveRate: 41,
    status: "new",
  },
  {
    slug: "redis-restart-herd",
    track: "caching",
    topic: "Stampedes",
    title: "Redis restart herd",
    symptom: "A routine cache restart takes the site down",
    sev: 2,
    minutes: 25,
    solveRate: 38,
    status: "attempted",
  },
  {
    slug: "stale-prices",
    track: "caching",
    topic: "Invalidation",
    title: "Stale prices",
    symptom: "Customers are charged yesterday’s price",
    sev: 4,
    minutes: 15,
    solveRate: 68,
    status: "solved",
  },
  {
    slug: "ttl-zero",
    track: "caching",
    topic: "Invalidation",
    title: "TTL zero",
    symptom: "The cache works locally and does nothing in production",
    sev: 4,
    minutes: 10,
    solveRate: 82,
    status: "solved",
  },
  {
    slug: "one-celebrity-one-key",
    track: "caching",
    topic: "Hot keys",
    title: "One celebrity, one key",
    symptom: "A single viral profile melts one cache shard",
    sev: 1,
    minutes: 35,
    solveRate: 17,
    status: "new",
  },
  {
    slug: "evicted-at-the-worst-time",
    track: "caching",
    topic: "Eviction",
    title: "Evicted at the worst time",
    symptom: "Sessions vanish and everyone is logged out",
    sev: 3,
    minutes: 20,
    solveRate: 44,
    status: "solved",
  },
  {
    slug: "pool-party",
    track: "databases",
    topic: "Connection pools",
    title: "Pool party",
    symptom: "Requests hang while database CPU sits at 20%",
    sev: 3,
    minutes: 15,
    solveRate: 71,
    status: "solved",
  },
  {
    slug: "the-3am-table-lock",
    track: "databases",
    topic: "Migrations",
    title: "The 3 a.m. table lock",
    symptom: "Checkout freezes right after a deploy",
    sev: 2,
    minutes: 25,
    solveRate: 48,
    status: "attempted",
  },
  {
    slug: "ghost-reads",
    track: "databases",
    topic: "Replication",
    title: "Ghost reads",
    symptom: "Orders vanish, then reappear a minute later",
    sev: 1,
    minutes: 40,
    solveRate: 22,
    status: "new",
  },
  {
    slug: "emails-sent-twice",
    track: "queues",
    topic: "Idempotency",
    title: "Emails sent twice",
    symptom: "Every receipt arrives twice",
    sev: 3,
    minutes: 25,
    solveRate: 39,
    status: "solved",
  },
  {
    slug: "retry-storm",
    track: "queues",
    topic: "Retries",
    title: "Retry storm",
    symptom: "A two-minute blip becomes an hour-long outage",
    sev: 1,
    minutes: 35,
    solveRate: 21,
    status: "new",
  },
  {
    slug: "restarts-every-six-hours",
    track: "memory",
    topic: "Leaks",
    title: "Restarts every six hours",
    symptom: "Pods are OOM-killed on a schedule",
    sev: 3,
    minutes: 25,
    solveRate: 46,
    status: "solved",
  },
];

export const scenario = (slug: string) => SCENARIOS.find((s) => s.slug === slug);
export const track = (slug: string) => TRACKS.find((t) => t.slug === slug);

export const DAILY = {
  scenario: "the-3am-table-lock",
  players: 2418,
  medianMinutes: 13,
  closesIn: "9h 41m",
};

/* ------------------------------------------------------------------ incident */

export const INCIDENT = {
  id: "demo",
  scenario: "big-sale-meltdown",
  /** Severity of the page itself (the scenario's difficulty is separate). */
  sev: 1 as Severity,
  page: "product-api p99 latency above 3 s, error rate 18%",
  startedAt: "20:00",
};

// 19:30 today in the viewer's time zone, so the axis reads like the story (charts render client-side).
const T0 = (() => {
  const d = new Date();
  d.setHours(19, 30, 0, 0);
  return Math.floor(d.getTime() / 1000);
})();
export const CHART_TS = Array.from({ length: 31 }, (_, i) => T0 + i * 120);
const shape = (base: number, spike: number, from = 15, noise = 0.04) =>
  CHART_TS.map((_, i) => {
    const wobble = 1 + Math.sin(i * 1.7) * noise;
    return Math.round((i < from ? base : spike) * wobble * 10) / 10;
  });

export const CHARTS = {
  latency: shape(118, 4200, 15, 0.06),
  errors: shape(0.2, 18, 15, 0.08),
  dbCpu: shape(34, 97, 15, 0.03),
  cacheHit: shape(95, 3, 14, 0.02),
  deployAt: T0 + 14 * 120,
  saleAt: T0 + 15 * 120,
};

export const BOOT_STEPS: BootStep[] = [
  { id: "alloc", label: "Setting up your practice system", state: "done" },
  { id: "pull", label: "Starting ShopKart", detail: "api, worker, postgres and redis", state: "done" },
  { id: "seed", label: "Seeding 18,402 products", state: "done" },
  { id: "fault", label: "Shipping the 19:58 deploy", state: "active" },
  { id: "load", label: "Starting sale traffic", state: "pending" },
];

export const TIMELINE: TimelineEvent[] = [
  { id: "e1", at: "00:00", kind: "alert", text: "SEV1 page: product-api p99 latency 4.2 s, error rate 18%" },
  {
    id: "e2",
    at: "00:20",
    kind: "beat",
    actor: "Priya (product)",
    text: "Sale went live at 8 and product pages are dying. What's happening?",
  },
  {
    id: "e3",
    at: "02:10",
    kind: "beat",
    actor: "Arjun (SRE)",
    text: "I restarted Postgres. It dipped for 20 seconds and came straight back. What changed?",
  },
  {
    id: "e4",
    at: "04:02",
    kind: "action",
    text: "Ran pg_stat_statements: products query called 184,302 times",
  },
  { id: "e5", at: "05:40", kind: "action", text: "Compared cache keys with missed keys: v2: prefix" },
];

export const LOGS: LogLine[] = [
  {
    id: "l1",
    ts: "19:58:02",
    level: "info",
    service: "deployer",
    message: "deploy a91f3c2 started (product-api)",
  },
  {
    id: "l2",
    ts: "19:58:40",
    level: "info",
    service: "deployer",
    message: "deploy a91f3c2 complete, 4/4 pods healthy",
  },
  { id: "l3", ts: "20:00:00", level: "info", service: "load-gen", message: "sale profile engaged (10x)" },
  {
    id: "l4",
    ts: "20:00:01",
    level: "warn",
    service: "product-api",
    message: "cache MISS key=v2:product:1042",
  },
  {
    id: "l5",
    ts: "20:00:01",
    level: "warn",
    service: "product-api",
    message: "cache MISS key=v2:product:1042",
  },
  {
    id: "l6",
    ts: "20:00:02",
    level: "error",
    service: "product-api",
    message: "db pool exhausted (100/100) waiting=812",
  },
  {
    id: "l7",
    ts: "20:00:03",
    level: "error",
    service: "product-api",
    message: "upstream timeout GET /products/1042 after 3000ms, returning 502",
  },
  {
    id: "l8",
    ts: "20:00:03",
    level: "warn",
    service: "product-api",
    message: "cache MISS key=v2:product:1043",
  },
  { id: "l9", ts: "20:00:04", level: "debug", service: "worker", message: "orders queue depth=12" },
  {
    id: "l10",
    ts: "20:00:05",
    level: "error",
    service: "product-api",
    message: "upstream timeout GET /products/2210 after 3000ms, returning 502",
  },
];

export const TERMINAL_LINES = [
  { kind: "prompt", text: "redis-cli INFO stats | grep keyspace" },
  { kind: "out", text: "keyspace_hits:1204\nkeyspace_misses:391022" },
  { kind: "prompt", text: "redis-cli --scan --pattern 'product:*' | head -3" },
  { kind: "out", text: "product:1042\nproduct:1043\nproduct:2210" },
  { kind: "prompt", text: "git log --oneline -3" },
  {
    kind: "out",
    text: "a91f3c2 (19:58) refactor: add version prefix to cache keys\n7bd21e0 (17:30) update product images\n3c0e9aa (yesterday) bump redis client to 5.0.1",
  },
] as const;

export const WAR_ROOM = [
  {
    id: "w1",
    who: "PagerBot",
    role: "alert",
    at: "00:00",
    text: "SEV1: product-api p99 is 4.2 s and 18% of requests fail. Assigned to you.",
  },
  {
    id: "w2",
    who: "Priya",
    role: "Product manager",
    at: "00:20",
    text: "Sale went live at 8 and product pages are dying. Customers are posting screenshots.",
  },
  {
    id: "w3",
    who: "Arjun",
    role: "SRE",
    at: "02:10",
    text: "Restarted Postgres. It dipped and came straight back. Something is sending it way too many queries. What changed?",
  },
  {
    id: "w4",
    who: "You",
    role: "Incident commander",
    at: "06:02",
    text: "Likely the 19:58 deploy: cache keys changed, so every read misses. Rolling back.",
  },
] as const;

export const CODE_SAMPLE = `from app.cache import cache
from app.db import db

CACHE_VERSION = "v2"   # added in a91f3c2

def key(pid):
    return f"{CACHE_VERSION}:product:{pid}"

def get_product(pid):
    data = cache.get(key(pid))
    if data is None:
        # every miss goes straight to Postgres
        data = db.fetch_product(pid)
        cache.set(key(pid), data, ttl=300)
    return data`;

/* ------------------------------------------------------------------ debrief */

export const PROBES: Probe[] = [
  {
    key: "replay",
    name: "Sale replay at 10x",
    how: "Replays the 20:00 traffic shape for 3 minutes",
    observed: "p99 180 ms",
    target: "< 500 ms",
    outcome: "pass",
  },
  {
    key: "hot-key",
    name: "Hot key expires mid-load",
    how: "Deletes product:1042 while 4,000 req/s hit it",
    observed: "1 query/s",
    target: "< 50/s",
    outcome: "pass",
  },
  {
    key: "cold",
    name: "Cold cache",
    how: "Flushes Redis at peak and measures recovery",
    observed: "9 s",
    target: "< 30 s",
    outcome: "pass",
  },
  {
    key: "fresh",
    name: "Price change freshness",
    how: "Updates a price and polls until the API shows it",
    observed: "2 s",
    target: "< 5 s",
    outcome: "pass",
  },
  {
    key: "tests",
    name: "Hidden correctness tests",
    how: "API contract and edge cases",
    observed: "24/24",
    target: "all pass",
    outcome: "pass",
  },
  {
    key: "budget",
    name: "Resource budget",
    how: "No bigger database, Redis under 1 GB",
    observed: "within budget",
    target: "no scale-up",
    outcome: "pass",
  },
];

export const APPROACHES: (Approach & {
  idea: string;
  code: string;
  p99: string;
  dbAtExpiry: string;
  staleness: string;
  pro: string;
  con: string;
})[] = [
  {
    id: "coalesce",
    name: "Request coalescing",
    share: 38,
    outcome: "full",
    yours: true,
    idea: "When many requests miss the same key at once, one goes to the database and the rest wait for its answer.",
    code: "with lock_for(pid):\n    data = cache.get(key(pid))\n    if data is None:\n        data = db.fetch_product(pid)\n        cache.set(key(pid), data, ttl=300)",
    p99: "180 ms",
    dbAtExpiry: "1/s",
    staleness: "2 s",
    pro: "Simple, no stale data, no extra infrastructure.",
    con: "Coalesces per process only: 40 pods can still mean 40 loaders.",
  },
  {
    id: "lock",
    name: "Distributed lock on miss",
    share: 24,
    outcome: "full",
    idea: "The first request to miss takes a short lock in Redis and rebuilds the value; others wait briefly.",
    code: 'if cache.set(f"lock:{k}", 1, nx=True, ex=5):\n    rebuild(k)',
    p99: "240 ms",
    dbAtExpiry: "1/s",
    staleness: "2 s",
    pro: "Exactly one loader across the whole cluster.",
    con: "Extra round trip; lock expiry needs care.",
  },
  {
    id: "swr",
    name: "Stale-while-revalidate",
    share: 21,
    outcome: "full",
    idea: "Serve the old value past its soft expiry while one background job refreshes it.",
    code: "value, soft_exp = cache.get_with_meta(k)\nif value and now() > soft_exp:\n    refresh_in_background(pid)",
    p99: "120 ms",
    dbAtExpiry: "0.5/s",
    staleness: "4 s",
    pro: "Fastest for users; hot keys never fully expire.",
    con: "Briefly stale data; wrong for stock counts at zero.",
  },
  {
    id: "jitter",
    name: "TTL jitter only",
    share: 9,
    outcome: "partial",
    idea: "Randomise expiry times so keys do not all expire together.",
    code: "cache.set(k, data, ttl=300 + randint(0, 60))",
    p99: "310 ms",
    dbAtExpiry: "3,900/s",
    staleness: "2 s",
    pro: "Spreads mass expiry. One line.",
    con: "Does nothing for a single hot key. Fails the hot-key check.",
  },
  {
    id: "scale",
    name: "Scale up Postgres",
    share: 2,
    outcome: "fails",
    idea: "Move to a bigger database so it absorbs the extra queries.",
    code: "# infrastructure change, no code",
    p99: "1.9 s",
    dbAtExpiry: "12,000/s",
    staleness: "2 s",
    pro: "Buys a little headroom quickly.",
    con: "Treats the symptom and breaks the resource budget.",
  },
];

export const RUBRIC = [
  {
    item: "Root cause",
    score: "3 / 3",
    note: "Named both the key-format deploy and the missing stampede protection.",
  },
  { item: "Impact", score: "2 / 2", note: "Duration, error rate and affected pages were all stated." },
  {
    item: "Action items",
    score: "2 / 3",
    note: "Coalescing and cache warm-up are good. Missing: a deploy freeze before big sales.",
  },
  {
    item: "Blameless and clear",
    score: "1.5 / 2",
    note: "One line names the engineer who shipped the deploy. Describe the change, not the person.",
  },
];

export const REPLAY = [
  { at: "00:00", text: "Paged; opened Overview", mark: null },
  { at: "01:12", text: "Cache hit rate at 3% was already on screen", mark: "clue" },
  { at: "02:30", text: "Spent 3 minutes on Postgres connection settings", mark: "lost" },
  { at: "05:40", text: "Compared stored keys with missed keys", mark: "clue" },
  { at: "06:55", text: "Found deploy a91f3c2 in git log", mark: "clue" },
  { at: "08:12", text: "Rolled back; service recovered", mark: null },
  { at: "17:40", text: "Shipped coalescing; all six checks passed", mark: null },
] as const;

/* ------------------------------------------------------------------ profile, admin, quick fire */

export const PROFILE = {
  handle: "ajay",
  name: "Ajay Singh",
  joined: "October 2026",
  streakDays: 12,
  resolved: 23,
  ratings: TRACKS.map((t, i) => ({
    track: t.name,
    rating: t.rating,
    history: [1200, 1220 + i * 7, 1250 - i * 4, 1268 + i * 6, t.rating - 20, t.rating],
  })),
  // 12 weeks × 7 days of activity counts (0–3).
  activity: Array.from({ length: 84 }, (_, i) => [0, 1, 0, 2, 0, 1, 3, 0, 1, 1, 0, 2][i % 12]!),
};

export const ADMIN_ROWS = [
  {
    slug: "big-sale-meltdown",
    status: "published",
    version: 3,
    validation: "pass",
    solveRate: 41,
    median: "23 min",
    flag: null,
  },
  {
    slug: "one-celebrity-one-key",
    status: "published",
    version: 1,
    validation: "pass",
    solveRate: 17,
    median: "38 min",
    flag: "Solve rate under 20%",
  },
  {
    slug: "ghost-reads",
    status: "review",
    version: 2,
    validation: "pass",
    solveRate: 0,
    median: "—",
    flag: null,
  },
  {
    slug: "retry-storm",
    status: "draft",
    version: 1,
    validation: "fail",
    solveRate: 0,
    median: "—",
    flag: "Fix does not pass the hot-key check",
  },
  {
    slug: "pool-party",
    status: "published",
    version: 4,
    validation: "pass",
    solveRate: 71,
    median: "12 min",
    flag: null,
  },
] as const;
