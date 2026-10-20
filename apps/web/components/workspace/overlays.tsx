"use client";

import { CircleCheck, Clock, Copy, Lightbulb, LoaderCircle, RotateCcw, WifiOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { BootSequence, type BootStep } from "@devgrill/ui/components/devgrill/boot-sequence";
import { ProbeTable, type Probe } from "@devgrill/ui/components/devgrill/probe-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@devgrill/ui/components/ui/dialog";
import { useAction, useIncident, useSource, useTelemetry } from "./context";
import { ENDED, type IncidentSnapshot } from "./model";

// ------------------------------------------------------------------------------- boot

const BOOT: { id: string; label: string; detail?: string }[] = [
  { id: "sandbox", label: "Allocating your sandbox", detail: "an isolated network with no way out" },
  { id: "services", label: "Starting the system", detail: "api, worker, Postgres, the cache, Toxiproxy" },
  { id: "source", label: "Cloning the source", detail: "with its git history" },
  { id: "history", label: "Shipping the latest deploys" },
  { id: "traffic", label: "Starting traffic" },
];

function isResetting({ events, boot, state }: IncidentSnapshot): boolean {
  return (
    state !== "provisioning" &&
    boot.length < BOOT.length &&
    events.some((e) => e.type === "sandbox" && e.payload.action === "reset" && e.payload.status === "started")
  );
}

/** True while the boot or ended overlay covers the workspace (which is then inert). */
export function useOverlayShown(): boolean {
  const incident = useIncident();
  return incident.state === "provisioning" || ENDED.has(incident.state) || isResetting(incident);
}

/** Real progress from the workflow's boot events; never a fake progress bar. */
export function BootOverlay() {
  const incident = useIncident();
  const { state, boot } = incident;
  const resetting = isResetting(incident);
  if (state !== "provisioning" && !resetting) return null;
  const lastSeen = BOOT.reduce((n, step, i) => (boot.includes(step.id) ? i : n), -1);
  const steps: BootStep[] = BOOT.map((step, i) => ({
    ...step,
    state:
      i < lastSeen ? "done" : i === lastSeen ? "active" : i === 0 && lastSeen === -1 ? "active" : "pending",
  }));
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-canvas/95 px-6">
      <div className="w-full max-w-md rounded-md border border-border bg-surface p-6 shadow-lg">
        <BootSequence
          steps={steps}
          title={resetting ? "Resetting the sandbox" : "Getting your incident ready"}
        />
        <p className="text-caption text-fg-muted">
          Usually under 30 seconds. The clock starts when you are paged.
        </p>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------ ended

const ENDINGS: Record<string, { title: string; body: string }> = {
  resolved: { title: "Resolved", body: "Every probe passed. Your debrief is ready." },
  expired: { title: "Time's up", body: "The sandbox reached its time limit and was torn down." },
  abandoned: { title: "You left this incident", body: "The sandbox has been torn down." },
  failed: { title: "The sandbox stopped working", body: "Something on our side went wrong, not your fix." },
};

export function EndedOverlay({ briefingHref }: { briefingHref: string }) {
  const { info } = useSource();
  const { state, endedReason } = useIncident();
  const [copied, setCopied] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const ended = ENDED.has(state);
  // The workspace behind goes inert, so focus moves to what replaced it.
  useEffect(() => {
    if (ended) heading.current?.focus();
  }, [ended]);
  if (!ended) return null;
  const ending = ENDINGS[state] ?? ENDINGS.failed!;
  const body =
    state === "expired" && endedReason === "idle timeout"
      ? "Nobody touched the sandbox for a while, so it was torn down to save resources."
      : ending.body;
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-canvas/95 px-6">
      <section
        aria-labelledby="ended-title"
        className="w-full max-w-md rounded-md border border-border bg-surface p-6 shadow-lg"
      >
        <h2
          id="ended-title"
          ref={heading}
          tabIndex={-1}
          className="text-heading-lg font-semibold text-fg focus:outline-none"
        >
          {ending.title}
        </h2>
        <p className="mt-2 text-body text-fg-muted">{body}</p>
        <div className="mt-5 flex flex-wrap gap-2">
          {state === "resolved" ? (
            <Link
              href={`/incident/${info.attempt.id}/debrief`}
              className="inline-flex h-10 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              Open the debrief
            </Link>
          ) : (
            <Link
              href={briefingHref}
              className="inline-flex h-10 items-center gap-1.5 rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              <RotateCcw className="size-4" aria-hidden="true" />
              Back to the briefing
            </Link>
          )}
          {state === "failed" ? (
            <button
              type="button"
              onClick={async () => {
                const details = `attempt ${info.attempt.id}\nscenario ${info.attempt.scenario_slug}\nreason ${endedReason ?? "unknown"}\nat ${new Date().toISOString()}`;
                try {
                  await navigator.clipboard.writeText(details);
                  setCopied(true);
                } catch {
                  setCopied(false);
                }
              }}
              className="inline-flex h-10 items-center gap-1.5 rounded-sm border border-border-input px-4 text-body font-medium text-fg hover:bg-raised"
            >
              <Copy className="size-4" aria-hidden="true" />
              {copied ? "Details copied" : "Copy details for a report"}
            </button>
          ) : null}
        </div>
      </section>
    </div>
  );
}

// ----------------------------------------------------------------------------- banners

function useNow(everyMs: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(id);
  }, [everyMs]);
  return now;
}

/** T-5 and T-1 minute warnings, with Extend while the plan allows it. */
export function ExpiryBanner() {
  const { actions, info } = useSource();
  const { expiresAt, state, extendsLeft } = useIncident();
  const now = useNow(5000);
  const extend = useAction(actions.extend);
  if (!expiresAt || ENDED.has(state) || state === "provisioning") return null;
  const left = expiresAt - now;
  if (left > 5 * 60_000) return null;
  const minutes = Math.max(0, Math.ceil(left / 60_000));
  return (
    <div
      role="status"
      className="flex items-center gap-3 border-b border-warning-text/30 bg-warning-subtle px-4 py-2 text-body text-warning-text"
    >
      <Clock className="size-4 shrink-0" aria-hidden="true" />
      <span>
        {minutes <= 1 ? "Less than a minute left" : `${minutes} minutes left`} before the sandbox is torn
        down.
      </span>
      {extendsLeft > 0 && info.extend_minutes > 0 ? (
        <button
          type="button"
          onClick={() => void extend.run()}
          disabled={extend.busy}
          className="ml-auto inline-flex h-8 items-center rounded-sm bg-brand px-3 text-label font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
        >
          {extend.busy ? "Extending…" : `Extend by ${info.extend_minutes} min`}
        </button>
      ) : (
        <span className="ml-auto text-caption">No extensions left on your plan.</span>
      )}
      {extend.error ? <span className="text-caption">{extend.error}</span> : null}
    </div>
  );
}

/**
 * A minute before the idle timeout (WCAG 2.2.1): any key, click or scroll keeps the sandbox,
 * and the banner goes away.
 */
export function IdleBanner({ lastTouch }: { lastTouch: number }) {
  const { info } = useSource();
  const { state } = useIncident();
  const now = useNow(5000);
  const idleMs = info.idle_minutes * 60_000;
  if (!idleMs || ENDED.has(state) || state === "provisioning") return null;
  if (now < lastTouch + idleMs - 60_000) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-3 border-b border-warning-text/30 bg-warning-subtle px-4 py-2 text-body text-warning-text"
    >
      <Clock className="size-4 shrink-0" aria-hidden="true" />
      <span>
        Still there? The sandbox shuts down after {info.idle_minutes} minutes without activity. Press any key
        or click anywhere to keep it.
      </span>
    </div>
  );
}

/** Losing the network never blanks the panels: they keep their data and say so. */
export function NetworkBanner() {
  const { eventsDownSince } = useIncident();
  const { downSince } = useTelemetry();
  const [online, setOnline] = useState(true);
  const now = useNow(1000);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  // Only after 3 s of reconnecting: a blip isn't worth a banner.
  const since = [eventsDownSince, downSince].filter((t): t is number => t !== null);
  const stale = since.length > 0 && now - Math.min(...since) > 3000;
  if (online && !stale) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-2 border-b border-border bg-raised px-4 py-2 text-body text-fg"
    >
      <WifiOff className="size-4 shrink-0 text-warning-text" aria-hidden="true" />
      {online
        ? "Reconnecting to your sandbox… it keeps running meanwhile."
        : "You're offline. Your sandbox keeps running; we'll reconnect when you're back."}
    </div>
  );
}

// ------------------------------------------------------------------------------ verify

/** Shows a verify run started by the workspace (results arrive as a `verify` event). */
export function VerifyDialog({
  open,
  onOpenChange,
  startedAt,
  error: verifyError,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  startedAt: number;
  error: string | null;
}) {
  const { info } = useSource();
  const { events, state } = useIncident();
  const result = useMemo(
    () =>
      events.filter((e) => e.type === "verify" && new Date(e.ts).getTime() >= startedAt - 5000).at(-1) ??
      null,
    [events, startedAt],
  );

  const probes: Probe[] = ((result?.payload.probes as Record<string, unknown>[] | undefined) ?? []).map(
    (p) => ({
      key: String(p.key),
      name: String(p.title),
      how: String(p.detail),
      target: "",
      outcome: p.passed ? "pass" : "fail",
    }),
  );
  const passed = result?.payload.passed === true;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {result ? (passed ? "Verify passed" : "Not fixed yet") : "Verifying your fix"}
          </DialogTitle>
          <DialogDescription>
            {result
              ? passed
                ? "Your fix held under the sale replay and every check. The incident is resolved."
                : "Some checks failed. The sandbox is still yours: keep going and verify again."
              : "Replaying the traffic, then attacking the fix (cold cache, chaos, invariants). About two minutes."}
          </DialogDescription>
        </DialogHeader>
        {verifyError ? <p className="text-body text-danger-text">{verifyError}</p> : null}
        {result ? (
          <ProbeTable probes={probes} caption="Verify results" />
        ) : (
          <p className="flex items-center gap-2 text-body text-fg-muted" role="status">
            <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {state === "verifying" ? "Checks running…" : "Starting the verifier…"}
          </p>
        )}
        {passed ? (
          <Link
            href={`/incident/${info.attempt.id}/debrief`}
            className="inline-flex h-10 items-center gap-1.5 self-start rounded-sm bg-brand px-4 text-body font-semibold text-on-brand"
          >
            <CircleCheck className="size-4" aria-hidden="true" />
            Open the debrief
          </Link>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------------------- hints

export function HintsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { actions, info } = useSource();
  const { hints } = useIncident();
  const take = useAction(actions.hint);
  const next = hints.length + 1;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Hints</DialogTitle>
          <DialogDescription>
            Each one is more direct than the last. Hints are part of your score, so take them when they save
            you time.
          </DialogDescription>
        </DialogHeader>
        <ol className="flex flex-col gap-3" aria-live="polite">
          {hints.map((h) => (
            <li key={h.tier} className="rounded-sm border border-border bg-raised p-3">
              <p className="text-caption font-semibold text-brand-text">Hint {h.tier}</p>
              <p className="mt-1 text-body text-fg">{h.text}</p>
            </li>
          ))}
        </ol>
        {next <= info.hints_total ? (
          <button
            type="button"
            onClick={() => void take.run()}
            disabled={take.busy}
            className="inline-flex h-10 items-center gap-1.5 self-start rounded-sm border border-border-input px-4 text-body font-medium text-fg hover:bg-raised disabled:opacity-60"
          >
            <Lightbulb className="size-4" aria-hidden="true" />
            {take.busy ? "Revealing…" : `Reveal hint ${next} of ${info.hints_total}`}
          </button>
        ) : (
          <p className="text-body text-fg-muted">
            {info.hints_total ? "That's every hint for this incident." : "This incident has no hints."}
          </p>
        )}
        {take.error ? <p className="text-body text-danger-text">{take.error}</p> : null}
      </DialogContent>
    </Dialog>
  );
}
