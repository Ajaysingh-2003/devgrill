import type {
  CaseEvidenceOut,
  CaseFileOut,
  DeployChangesOut,
  DeployHistoryOut,
  WorkspaceOut,
} from "@devgrill/api-client";
import {
  NO_ASSIST,
  Store,
  parseLog,
  type IncidentEvent,
  type IncidentSnapshot,
  type LogsSnapshot,
  type TelemetrySnapshot,
  type WorkspaceSource,
} from "./model";

/** Nothing in a recording can be changed: the panels hide what would call these. */
const readOnly = async (): Promise<never> => {
  throw new Error("This is a recording: nothing can be changed.");
};

/**
 * A case file's recording behind the workspace's interface (ADR 018), so the panels draw it
 * exactly as they draw a live incident. Times are moved so the incident ended just now: charts
 * and "5 min ago" then read naturally, and how old the recording is doesn't matter.
 */
export function createRecordedSource(
  file: CaseFileOut,
  evidence: CaseEvidenceOut,
  now: number = Date.now(),
): WorkspaceSource {
  const lastBeat = Math.max(0, ...file.beats.map((b) => b.at_s));
  const activeAt = now - Math.max(evidence.duration_s, lastBeat) * 1000;
  const shift = activeAt / 1000 - evidence.recorded_at;
  const moved = (at: number) => at + shift;
  const iso = (t: number) => new Date(activeAt + t * 1000).toISOString();

  const info: WorkspaceOut = {
    attempt: {
      id: file.slug,
      scenario_slug: file.slug,
      mode: "guided",
      state: "active",
      started_at: new Date(activeAt).toISOString(),
      active_at: new Date(activeAt).toISOString(),
      ended_at: null,
      expires_at: null,
    },
    scenario_title: file.title,
    track_slug: file.track_slug,
    difficulty: file.difficulty,
    page: file.page,
    unlocked_tools: file.tools as WorkspaceOut["unlocked_tools"],
    metrics: file.metrics,
    slo: file.slo,
    deployable: file.deployable,
    host: file.host,
    hints_total: 0,
    hints: [],
    extend_minutes: 0,
    extends_left: 0,
    idle_minutes: 0,
    gateway_url: "",
  };

  const events: IncidentEvent[] = [
    ...(file.page
      ? [
          {
            id: 1,
            type: "alert",
            ts: iso(evidence.breached_after_s),
            payload: { severity: file.page.severity, title: file.page.title },
          },
        ]
      : []),
    ...file.beats.map((b, i) => ({
      id: 2 + i,
      type: "beat",
      ts: iso(b.at_s),
      payload: { persona: b.persona, say: b.say },
    })),
  ];

  const history = (service?: string): DeployHistoryOut => {
    const found = evidence.deploys[service ?? file.deployable[0] ?? ""];
    if (!found) throw new Error("No deploy history in this recording.");
    return { ...found, commits: found.commits.map((c) => ({ ...c, at: moved(c.at) })) };
  };
  const changes = (sha: string): DeployChangesOut => {
    const found = evidence.changes[sha];
    if (!found) throw new Error("These changes aren't in this recording.");
    return { ...found, at: moved(found.at) };
  };
  const files = (service?: string) => evidence.files[service ?? file.deployable[0] ?? ""] ?? {};

  return {
    kind: "recording",
    info,
    recorded: { dbRates: evidence.db_rates, commands: evidence.commands },
    incident: new Store<IncidentSnapshot>({
      state: "active",
      activeAt,
      expiresAt: null,
      extendsLeft: 0,
      events,
      boot: [],
      hints: [],
      endedReason: null,
      events_connection: "open",
      eventsDownSince: null,
      verify: null,
      assist: NO_ASSIST,
    }),
    telemetry: new Store<TelemetrySnapshot>({
      samples: evidence.samples.map((s) => ({ t: moved(evidence.recorded_at + s.t), values: s.values })),
      connection: "open",
      downSince: null,
    }),
    logs: new Store<LogsSnapshot>({
      lines: evidence.logs.map((l) => parseLog(iso(l.t), l.service, l.line)),
      dropped: 0,
    }),
    actions: {
      status: async () => ({ services: evidence.status }),
      files: async (service) => ({ service: service ?? "", files: Object.keys(files(service)) }),
      readFile: async (path, service) => files(service)[path] ?? "",
      writeFile: readOnly,
      deploys: async (service) => history(service),
      changes: async (sha) => changes(sha),
      deploy: readOnly,
      rollback: readOnly,
      restart: readOnly,
      db: async () => {
        if (!evidence.db) throw new Error("No database in this recording.");
        return evidence.db;
      },
      query: readOnly,
      cache: async () => {
        if (!evidence.cache) throw new Error("No cache in this recording.");
        return evidence.cache;
      },
      hint: readOnly,
      nudge: readOnly,
      message: readOnly,
      mitigate: readOnly,
      verify: readOnly,
      extend: readOnly,
      reset: readOnly,
      abandon: readOnly,
      touch: async () => undefined,
      openTerminal: readOnly,
    },
    start: () => () => undefined,
  };
}
