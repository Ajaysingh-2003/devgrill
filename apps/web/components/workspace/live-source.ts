import {
  abandonAttempt,
  cacheInsights,
  createWsTicket,
  dbInsights,
  dbQuery,
  declareMitigated,
  deploy,
  extendAttempt,
  listDeploys,
  listFiles,
  nudge,
  postMessage,
  readFile,
  resetAttempt,
  restartService,
  rollback,
  sandboxStatus,
  takeHint,
  touchAttempt,
  verifyAttempt,
  writeFile,
  type HintOut,
  type WorkspaceOut,
} from "@devgrill/api-client";
import { browserApi, call } from "@/lib/browser-api";
import {
  ENDED,
  NO_ASSIST,
  Store,
  appendCapped,
  parseLog,
  reduceAssist,
  type IncidentEvent,
  type IncidentSnapshot,
  type IncidentState,
  type LogsSnapshot,
  type ProbeStatus,
  type TelemetrySnapshot,
  type VerifyProgress,
  type TerminalLink,
  type WorkspaceSource,
} from "./model";

const MAX_SAMPLES = 900; // 30 minutes at one sample every 2 s
const MAX_LOG_LINES = 2000;
const BACKOFF_MS = [1000, 2000, 5000, 10_000];

const ms = (iso: string | null | undefined) => (iso ? new Date(iso).getTime() : null);

/** Fold one server event into the incident snapshot. */
export function reduceEvent(snap: IncidentSnapshot, event: IncidentEvent): IncidentSnapshot {
  if (snap.events.some((e) => e.id === event.id)) return snap;
  const next: IncidentSnapshot = { ...snap, events: [...snap.events, event] };
  const p = event.payload;
  switch (event.type) {
    case "state": {
      const to = String(p.to) as IncidentState;
      next.state = to;
      if (to === "active" && next.activeAt === null) next.activeAt = ms(event.ts);
      if (typeof p.expires_at === "string") next.expiresAt = ms(p.expires_at);
      if (ENDED.has(to) && typeof p.reason === "string") next.endedReason = p.reason;
      break;
    }
    case "extend":
      if (p.granted) {
        next.expiresAt = ms(String(p.expires_at));
        next.extendsLeft = Math.max(0, next.extendsLeft - 1);
      }
      break;
    case "reply":
      // The finished reply replaces the one being written.
      if (next.assist.typing?.id === p.id) next.assist = { ...next.assist, typing: null };
      break;
    case "hint":
      if (!next.hints.some((h) => h.tier === Number(p.tier))) {
        next.hints = [...next.hints, { tier: Number(p.tier), text: String(p.text) }];
      }
      break;
    case "boot":
      if (!next.boot.includes(String(p.step))) next.boot = [...next.boot, String(p.step)];
      break;
    case "sandbox":
      if (p.action === "destroyed" && typeof p.reason === "string" && p.reason) next.endedReason = p.reason;
      if (p.action === "reset" && p.status === "started") next.boot = [];
      break;
    case "verify_progress":
      next.verify = reduceVerifyProgress(next.verify, p);
      break;
    case "verify":
      next.verify = reduceVerifyResult(next.verify, p);
      break;
  }
  return next;
}

type ProbePayload = { key: string; title?: string; passed?: boolean | null; detail?: string };

/** A run starts with every probe queued; each probe then reports running, passed or failed. */
export function reduceVerifyProgress(
  current: VerifyProgress | null,
  p: Record<string, unknown>,
): VerifyProgress | null {
  const runId = String(p.run_id);
  if (p.status === "started") {
    const probes = ((p.probes as ProbePayload[] | undefined) ?? []).map((x) => ({
      key: x.key,
      title: x.title ?? x.key,
      status: "queued" as const,
    }));
    return { runId, probes, done: false, passed: null, error: null };
  }
  if (!current || current.runId !== runId || typeof p.key !== "string") return current;
  return {
    ...current,
    probes: current.probes.map((x) => (x.key === p.key ? { ...x, status: p.status as ProbeStatus } : x)),
  };
}

/** The run's verdict: every probe's outcome and detail. */
export function reduceVerifyResult(
  current: VerifyProgress | null,
  p: Record<string, unknown>,
): VerifyProgress {
  const probes = ((p.probes as ProbePayload[] | undefined) ?? []).map((x) => ({
    key: x.key,
    title: x.title ?? x.key,
    status: (x.passed == null ? "skipped" : x.passed ? "passed" : "failed") as ProbeStatus,
    detail: x.detail,
  }));
  return {
    runId: String(p.run_id ?? current?.runId ?? ""),
    probes,
    done: true,
    passed: Boolean(p.passed),
    error: typeof p.error === "string" ? p.error : null,
  };
}

/** A WebSocket as a TerminalLink (binary frames are screen bytes; text frames are control). */
function socketLink(url: string): TerminalLink {
  const ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";
  const link: TerminalLink = {
    send: (data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data as string | ArrayBufferView<ArrayBuffer>);
    },
    close: () => ws.close(),
    onopen: null,
    onmessage: null,
    onclose: null,
  };
  ws.onopen = () => link.onopen?.();
  ws.onmessage = (e) => link.onmessage?.(e.data as string | ArrayBuffer);
  ws.onclose = (e) => link.onclose?.(e.code, e.reason);
  return link;
}

export function createLiveSource(info: WorkspaceOut): WorkspaceSource {
  const id = info.attempt.id;
  const path = { attempt_id: id };
  const client = () => browserApi();

  const incident = new Store<IncidentSnapshot>({
    state: info.attempt.state as IncidentState,
    activeAt: ms(info.attempt.active_at),
    expiresAt: ms(info.attempt.expires_at),
    extendsLeft: info.extends_left,
    events: [],
    boot: [],
    hints: info.hints,
    endedReason: null,
    events_connection: "connecting",
    eventsDownSince: null,
    verify: null,
    assist: NO_ASSIST,
  });
  const telemetry = new Store<TelemetrySnapshot>({ samples: [], connection: "connecting", downSince: null });
  const logs = new Store<LogsSnapshot>({ lines: [], dropped: 0 });

  const actions: WorkspaceSource["actions"] = {
    status: () => call(sandboxStatus({ client: client(), path })),
    files: (service) => call(listFiles({ client: client(), path, query: { service } })),
    readFile: async (p, service) =>
      (await call(readFile({ client: client(), path, query: { path: p, service } }))).content,
    writeFile: async (p, content, service) => {
      await call(writeFile({ client: client(), path, query: { path: p, service }, body: { content } }));
    },
    deploys: (service) => call(listDeploys({ client: client(), path, query: { service } })),
    deploy: (service) => call(deploy({ client: client(), path, body: { service } })),
    rollback: (ref, service) => call(rollback({ client: client(), path, body: { ref, service } })),
    restart: async (service) =>
      (await call(restartService({ client: client(), path, body: { service } }))).message,
    db: () => call(dbInsights({ client: client(), path })),
    query: (sql) => call(dbQuery({ client: client(), path, body: { sql } })),
    cache: () => call(cacheInsights({ client: client(), path })),
    hint: async () => {
      const hint: HintOut = await call(takeHint({ client: client(), path }));
      incident.set((s) =>
        s.hints.some((h) => h.tier === hint.tier) ? s : { ...s, hints: [...s.hints, hint] },
      );
      return hint;
    },
    message: async (text) => {
      await call(postMessage({ client: client(), path, body: { text } }));
    },
    nudge: async () => (await call(nudge({ client: client(), path }))).text,
    mitigate: () => call(declareMitigated({ client: client(), path })),
    verify: async () => {
      await call(verifyAttempt({ client: client(), path }));
    },
    extend: async () => {
      await call(extendAttempt({ client: client(), path }));
    },
    reset: async () => {
      await call(resetAttempt({ client: client(), path }));
    },
    abandon: async () => {
      await call(abandonAttempt({ client: client(), path }));
    },
    touch: async () => {
      await call(touchAttempt({ client: client(), path }));
    },
    openTerminal: async (cols, rows) => {
      const ticket = await call(createWsTicket({ client: client(), path, body: { kind: "terminal" } }));
      return socketLink(`${ticket.url}&cols=${cols}&rows=${rows}`);
    },
  };

  function start(): () => void {
    let stopped = false;
    let events: EventSource | null = null;
    let socket: WebSocket | null = null;
    let telemetryTry = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    // ---- events (SSE): resumable; closed for good once the sandbox is torn down.
    events = new EventSource(`/api/v1/attempts/${id}/events`);
    events.onopen = () => incident.set((s) => ({ ...s, events_connection: "open", eventsDownSince: null }));
    events.onmessage = (message) => {
      const data = JSON.parse(message.data as string) as Omit<IncidentEvent, "id">;
      const event: IncidentEvent = { id: Number(message.lastEventId), ...data };
      incident.set((s) => reduceEvent(s, event));
      if (event.type === "sandbox" && event.payload.action === "destroyed") {
        events?.close();
        incident.set((s) => ({ ...s, events_connection: "closed" }));
      }
    };
    // A teammate writing a reply: live only, never replayed on reconnect.
    events.addEventListener("assist", (message) => {
      const payload = JSON.parse((message as MessageEvent<string>).data) as Record<string, unknown>;
      incident.set((s) => ({ ...s, assist: reduceAssist(s.assist, payload) }));
    });
    events.onerror = () => {
      if (events?.readyState === EventSource.CLOSED)
        incident.set((s) => ({ ...s, events_connection: "closed" }));
      else
        incident.set((s) => ({
          ...s,
          events_connection: "reconnecting",
          eventsDownSince: s.eventsDownSince ?? Date.now(),
        }));
    };

    // ---- telemetry (WebSocket): once the sandbox is up; reconnects with backoff.
    async function connectTelemetry() {
      if (stopped || socket) return;
      const state = incident.get().state;
      if (state === "provisioning" || ENDED.has(state)) return;
      try {
        const ticket = await call(createWsTicket({ client: client(), path, body: { kind: "telemetry" } }));
        if (stopped) return;
        socket = new WebSocket(ticket.url);
      } catch {
        scheduleTelemetry();
        return;
      }
      socket.onopen = () => {
        telemetryTry = 0;
        telemetry.set((t) => ({ ...t, connection: "open", downSince: null }));
      };
      socket.onmessage = (message) => {
        const frame = JSON.parse(message.data as string) as Record<string, unknown>;
        switch (frame.type) {
          case "history":
            telemetry.set((t) => ({
              ...t,
              samples: (frame.samples as TelemetrySnapshot["samples"]).slice(-MAX_SAMPLES),
            }));
            break;
          case "sample":
            telemetry.set((t) => ({
              ...t,
              samples: appendCapped(
                t.samples,
                [{ t: Number(frame.t), values: frame.values as Record<string, number | null> }],
                MAX_SAMPLES,
              ),
            }));
            break;
          case "logs": {
            const lines = (frame.lines as { ts: string; service: string; line: string }[]).map((l) =>
              parseLog(l.ts, l.service, l.line),
            );
            logs.set((s) => ({
              lines: appendCapped(s.lines, lines, MAX_LOG_LINES),
              dropped: s.dropped + Number(frame.dropped ?? 0),
            }));
            break;
          }
        }
      };
      socket.onclose = (event) => {
        socket = null;
        if (stopped || event.code === 4410 || ENDED.has(incident.get().state)) {
          telemetry.set((t) => ({ ...t, connection: "closed" }));
          return;
        }
        telemetry.set((t) => ({ ...t, connection: "reconnecting", downSince: t.downSince ?? Date.now() }));
        scheduleTelemetry();
      };
    }
    function scheduleTelemetry() {
      clearTimeout(retryTimer);
      const delay = BACKOFF_MS[Math.min(telemetryTry, BACKOFF_MS.length - 1)]!;
      telemetryTry += 1;
      retryTimer = setTimeout(() => void connectTelemetry(), delay);
    }

    let lastState = incident.get().state;
    const unsubscribe = incident.subscribe(() => {
      const state = incident.get().state;
      if (state !== lastState) {
        lastState = state;
        if (ENDED.has(state)) socket?.close();
        else void connectTelemetry();
      }
    });
    void connectTelemetry();

    return () => {
      stopped = true;
      unsubscribe();
      clearTimeout(retryTimer);
      events?.close();
      socket?.close();
    };
  }

  return { kind: "live", info, incident, telemetry, logs, actions, start };
}
