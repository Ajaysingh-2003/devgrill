"use client";

import {
  Code2,
  Database,
  DoorOpen,
  Eye,
  EyeOff,
  Filter,
  Gauge,
  GitBranch,
  Laptop,
  LayoutPanelLeft,
  Lightbulb,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  Timer,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CommandPalette, type PaletteCommand } from "@devgrill/ui/components/devgrill/command-palette";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ToolRail, type Tool } from "@devgrill/ui/components/devgrill/tool-rail";
import {
  WORKSPACE_PRESETS,
  WorkspaceLayout,
  requestPreset,
} from "@devgrill/ui/components/devgrill/workspace-layout";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@devgrill/ui/components/ui/dialog";
import { isTypingTarget, useHotkey } from "@devgrill/ui/hooks/use-hotkey";
import { DevGrillMark } from "@devgrill/ui/icons";
import { cn } from "@devgrill/ui/lib/utils";
import { useActivityTouch } from "./activity";
import { SourceProvider, useAction, useIncident, useSource } from "./context";
import { ENDED, type WorkspaceSource } from "./model";
import {
  BootOverlay,
  EndedOverlay,
  ExpiryBanner,
  HintsDialog,
  IdleBanner,
  NetworkBanner,
  VerifyDialog,
  useOverlayShown,
} from "./overlays";
import { CachePanel } from "./panels/cache";
import { CodePanel } from "./panels/code";
import { DatabasePanel } from "./panels/database";
import { DeploysPanel } from "./panels/deploys";
import { LogsPanel } from "./panels/logs";
import { OverviewPanel } from "./panels/overview";
import { TerminalPanel } from "./panels/terminal";
import { SidePanel } from "./side-panel";

const TOOLS: (Tool & { key: string })[] = [
  { id: "overview", key: "overview", label: "Overview", icon: Gauge },
  { id: "logs", key: "logs", label: "Logs", icon: ScrollText },
  { id: "database", key: "database", label: "Database", icon: Database },
  { id: "cache", key: "cache", label: "Cache", icon: Zap },
  { id: "code", key: "code", label: "Code", icon: Code2 },
  { id: "deploys", key: "deploys", label: "Deploys", icon: GitBranch },
];

const PANELS: Record<string, () => React.ReactNode> = {
  overview: OverviewPanel,
  logs: LogsPanel,
  database: DatabasePanel,
  cache: CachePanel,
  code: CodePanel,
  deploys: DeploysPanel,
};

const PHASES = ["Triage", "Investigate", "Mitigate", "Fix", "Verify", "Postmortem"];

export function Workspace({ source, briefingHref }: { source: WorkspaceSource; briefingHref: string }) {
  return (
    <SourceProvider source={source}>
      <Shell briefingHref={briefingHref} />
    </SourceProvider>
  );
}

function Shell({ briefingHref }: { briefingHref: string }) {
  const { info, actions } = useSource();
  const incident = useIncident();
  const router = useRouter();
  const unlocked = new Set<string>(info.unlocked_tools);
  const tools = TOOLS.map((t) => ({ ...t, disabled: !unlocked.has(t.key) }));
  const [tool, setTool] = useState(tools.find((t) => !t.disabled)?.id ?? "overview");
  const [preset, setPreset] = useState(WORKSPACE_PRESETS[0]!.id);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [hintsOpen, setHintsOpen] = useState(false);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [confirm, setConfirm] = useState<"reset" | "leave" | null>(null);
  const [claim, setClaim] = useState("");
  // Guided mode hides the clock by default (no pressure); on-call shows it (PLAN §8.4).
  const [showClock, setShowClock] = useState(info.attempt.mode !== "guided");
  const Active = PANELS[tool]!;
  const ended = ENDED.has(incident.state);
  const sev = Number(info.page?.severity.replace("SEV", "") ?? 3) as 1 | 2 | 3 | 4;

  // The page is the only assertive announcement in the workspace (inserted after mount:
  // text already in a server-rendered alert is often not announced).
  const [paged, setPaged] = useState("");
  useEffect(() => {
    if (!info.page || incident.state === "provisioning") return;
    const id = window.setTimeout(() => setPaged(`Paged: ${info.page!.title}`), 400);
    return () => window.clearTimeout(id);
  }, [info.page, incident.state]);

  // Number keys switch tools (not while typing in the terminal, editor or inputs).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      const next = tools[Number(event.key) - 1];
      if (next && !next.disabled) setTool(next.id);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [tools]);

  const mitigate = useAction(actions.mitigate);
  const declareMitigated = async () => {
    const out = await mitigate.run();
    if (out) {
      setClaim(
        out.correct
          ? "Declared mitigated, and the metrics agree."
          : "Declared mitigated, but the SLO still breaches. Keep going: the claim is on your timeline.",
      );
    }
  };
  const reset = useAction(actions.reset);
  const verify = useAction(actions.verify);
  // The run on screen before this request: the dialog waits for the next one.
  const [previousRun, setPreviousRun] = useState<string | null>(null);
  const openVerify = () => {
    setPreviousRun(incident.state === "verifying" ? null : (incident.verify?.runId ?? null));
    setVerifyOpen(true);
    void verify.run();
  };
  const leave = useAction(actions.abandon);

  // Triage while it boots; investigating once paged; mitigating once you act on the system.
  const phase = useMemo(() => {
    if (incident.state === "resolved") return 5;
    if (incident.state === "verifying") return 4;
    if (incident.state === "mitigated") return 3;
    if (incident.state === "provisioning") return 0;
    return incident.events.some((e) => e.type === "deploy" || e.type === "rollback" || e.type === "action")
      ? 2
      : 1;
  }, [incident]);

  const incidentCommands: PaletteCommand[] = [
    {
      id: "hint",
      group: "Incident",
      label: "Request a hint",
      icon: Lightbulb,
      shortcut: "h",
      onSelect: () => setHintsOpen(true),
    },
    {
      id: "mitigated",
      group: "Incident",
      label: "Declare mitigated",
      icon: ShieldCheck,
      shortcut: "m",
      onSelect: () => void declareMitigated(),
    },
    {
      id: "verify",
      group: "Incident",
      label: "Run verify",
      icon: ShieldCheck,
      shortcut: "mod+shift+v",
      onSelect: () => openVerify(),
    },
    {
      id: "filter-logs",
      group: "Incident",
      label: "Filter logs by…",
      icon: Filter,
      onSelect: () => {
        setTool("logs");
        window.setTimeout(() => document.getElementById("log-query")?.focus(), 50);
      },
    },
    {
      id: "rollback",
      group: "Incident",
      label: "Roll back…",
      icon: RotateCcw,
      onSelect: () => setTool("deploys"),
    },
    ...(incident.extendsLeft > 0 && info.extend_minutes > 0
      ? [
          {
            id: "extend",
            group: "Incident",
            label: `Extend by ${info.extend_minutes} minutes`,
            icon: Timer,
            onSelect: () => void actions.extend(),
          },
        ]
      : []),
    {
      id: "reset",
      group: "Incident",
      label: "Reset the sandbox",
      icon: RotateCcw,
      onSelect: () => setConfirm("reset"),
    },
    {
      id: "leave",
      group: "Incident",
      label: "Leave the incident",
      icon: DoorOpen,
      onSelect: () => setConfirm("leave"),
    },
  ];
  const runCommand = (id: string) => {
    if (ended || incident.state === "provisioning") return;
    incidentCommands.find((c) => c.id === id)?.onSelect();
  };
  useHotkey("h", () => runCommand("hint"));
  useHotkey("m", () => runCommand("mitigated"));
  useHotkey("mod+shift+v", (event) => {
    event.preventDefault();
    runCommand("verify");
  });

  const commands: PaletteCommand[] = [
    ...tools
      .filter((t) => !t.disabled)
      .map((t) => ({
        id: `tool-${t.id}`,
        group: "Panels",
        label: `Open ${t.label}`,
        icon: t.icon,
        shortcut: String(tools.indexOf(t) + 1),
        onSelect: () => setTool(t.id),
      })),
    ...WORKSPACE_PRESETS.map((p, i) => ({
      id: `preset-${p.id}`,
      group: "Layout",
      label: `${p.label} layout`,
      icon: LayoutPanelLeft,
      shortcut: `mod+${i + 1}`,
      onSelect: () => requestPreset(p.id),
    })),
    ...(ended ? [] : incidentCommands),
  ];

  const busy = incident.state === "provisioning" || ended;
  const covered = useOverlayShown();
  const lastTouch = useActivityTouch(actions.touch, !busy);
  return (
    <>
      {/* Below 1024 px the workspace is not shrunk: offer the right alternatives instead. */}
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center lg:hidden">
        <Laptop className="size-8 text-fg-muted" aria-hidden="true" />
        <h1 className="text-heading-lg font-semibold text-fg">This incident needs a bigger screen</h1>
        <p className="max-w-sm text-body text-fg-muted">
          The workspace has a terminal, logs and live charts side by side. Open it on a laptop, or keep
          practising here with Quick Fire.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <Link
            href="/quickfire"
            className="inline-flex h-10 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand"
          >
            Play Quick Fire
          </Link>
          <Link
            href="/drills"
            className="inline-flex h-10 items-center rounded-sm px-4 text-body font-medium text-fg hover:bg-raised"
          >
            Back to drills
          </Link>
        </div>
      </div>

      <div className="relative hidden h-dvh min-h-[40rem] flex-col lg:flex">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-surface px-3">
          <Link
            href="/drills"
            aria-label="Back to drills (the incident keeps running)"
            className="rounded-sm p-1 text-fg"
          >
            <DevGrillMark className="size-5" />
          </Link>
          {info.page ? <SevBadge sev={sev} size="md" /> : null}
          <h1 className="truncate text-body font-semibold text-fg">{info.scenario_title}</h1>
          {info.page ? (
            <span className="hidden truncate text-label text-fg-muted xl:inline">{info.page.title}</span>
          ) : null}
          {showClock ? <ElapsedClock activeAt={incident.activeAt} stopped={ended} /> : null}
          {info.attempt.mode === "guided" ? (
            <button
              type="button"
              onClick={() => setShowClock((v) => !v)}
              aria-pressed={!showClock}
              aria-label={showClock ? "Hide the clock" : "Show the clock"}
              className="rounded-sm p-1 text-fg-subtle hover:bg-raised hover:text-fg"
            >
              {showClock ? (
                <EyeOff className="size-4" aria-hidden="true" />
              ) : (
                <Eye className="size-4" aria-hidden="true" />
              )}
            </button>
          ) : null}
          <p className="ml-2 text-caption text-fg-muted 2xl:hidden">
            Step {phase + 1} of {PHASES.length}:{" "}
            <span className="font-semibold text-brand-text">{PHASES[phase]}</span>
          </p>

          <ol aria-label="Incident phases" className="ml-auto hidden items-center gap-1 2xl:flex">
            {PHASES.map((p, i) => (
              <li
                key={p}
                aria-current={i === phase ? "step" : undefined}
                className={cn(
                  "rounded-full px-2 py-0.5 text-caption",
                  i < phase && "text-success-text",
                  i === phase && "bg-brand-subtle font-semibold text-brand-text",
                  i > phase && "text-fg-subtle",
                )}
              >
                {p}
                {i < phase ? <span className="sr-only"> (done)</span> : null}
              </li>
            ))}
          </ol>

          <div
            role="group"
            aria-label="Layout"
            className="ml-auto flex rounded-sm border border-border p-0.5 2xl:ml-3"
          >
            {WORKSPACE_PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                aria-pressed={preset === p.id}
                onClick={() => requestPreset(p.id)}
                className={cn(
                  "rounded-xs px-2 py-1 text-caption font-medium",
                  preset === p.id ? "bg-raised text-fg" : "text-fg-subtle hover:text-fg",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          {info.hints_total > 0 ? (
            <button
              type="button"
              onClick={() => setHintsOpen(true)}
              disabled={busy}
              aria-keyshortcuts="h"
              className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border-input px-2.5 text-label font-medium text-fg hover:bg-raised disabled:opacity-50"
            >
              <Lightbulb className="size-3.5" aria-hidden="true" />
              Hint
              {incident.hints.length ? (
                <span className="text-fg-subtle tabular-nums">
                  {incident.hints.length}/{info.hints_total}
                </span>
              ) : null}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void declareMitigated()}
            disabled={busy || mitigate.busy}
            aria-keyshortcuts="m"
            className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border-input px-2.5 text-label font-medium text-fg hover:bg-raised disabled:opacity-50"
          >
            <ShieldCheck className="size-3.5" aria-hidden="true" />
            Mitigated
          </button>
          <button
            type="button"
            onClick={openVerify}
            disabled={busy || incident.state === "verifying"}
            aria-keyshortcuts="Control+Shift+V Meta+Shift+V"
            className="inline-flex h-8 items-center rounded-sm bg-brand px-3 text-label font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
          >
            {incident.state === "verifying" ? "Verifying…" : "Verify"}
          </button>
        </header>
        <NetworkBanner />
        <ExpiryBanner />
        <IdleBanner lastTouch={lastTouch} />
        <p className="sr-only" role="status">
          {claim || mitigate.error || ""}
        </p>

        <div className="relative flex min-h-0 flex-1">
          {/* A tablist, not navigation: it switches the panel in place. */}
          <aside
            inert={covered}
            aria-label="Incident tools"
            className="w-44 shrink-0 border-r border-border bg-surface"
          >
            <ToolRail tools={tools} value={tool} onValueChange={setTool} panelId="tool-panel" />
          </aside>
          <main id="main" inert={covered} className="min-w-0 flex-1">
            <WorkspaceLayout
              primary={<Active />}
              secondary={unlocked.has("terminal") ? <TerminalPanel /> : <LockedTerminal />}
              side={<SidePanel />}
              onPresetChange={(p) => setPreset(p.id)}
            />
          </main>
          <BootOverlay />
          <EndedOverlay briefingHref={briefingHref} />
        </div>
      </div>

      {/* Genuine pages are the only assertive announcements in the workspace. */}
      <p role="alert" className="sr-only">
        {paged}
      </p>
      <CommandPalette commands={commands} open={paletteOpen} onOpenChange={setPaletteOpen} />
      <HintsDialog open={hintsOpen} onOpenChange={setHintsOpen} />
      <VerifyDialog
        open={verifyOpen}
        onOpenChange={setVerifyOpen}
        previousRun={previousRun}
        error={verify.error}
      />
      <Dialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent instant className="max-w-md">
          <DialogHeader>
            <DialogTitle>{confirm === "reset" ? "Reset the sandbox?" : "Leave this incident?"}</DialogTitle>
            <DialogDescription>
              {confirm === "reset"
                ? "The system goes back to its initial broken state: your deploys and data changes are lost. The clock keeps running."
                : "The sandbox is torn down and the attempt ends. You can start the incident again from its briefing."}
            </DialogDescription>
          </DialogHeader>
          {reset.error || leave.error ? (
            <p className="text-body text-danger-text">{reset.error ?? leave.error}</p>
          ) : null}
          <DialogFooter>
            <button
              type="button"
              onClick={() => setConfirm(null)}
              className="h-10 rounded-sm px-4 text-body font-medium text-fg hover:bg-raised"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={reset.busy || leave.busy}
              onClick={async () => {
                if (confirm === "reset") {
                  await reset.run();
                  setConfirm(null);
                } else {
                  await leave.run();
                  setConfirm(null);
                  router.push(briefingHref);
                }
              }}
              className="h-10 rounded-sm bg-danger-solid px-4 text-body font-semibold text-on-danger disabled:opacity-60"
            >
              {confirm === "reset" ? "Reset" : "Leave"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function LockedTerminal() {
  return (
    <PanelFrame id="terminal" title="Terminal" bodyClassName="bg-sunken">
      <EmptyState icon={ScrollText} title="The terminal unlocks in a later tutorial" compact>
        For this one, the panels on the left are enough.
      </EmptyState>
    </PanelFrame>
  );
}

function ElapsedClock({ activeAt, stopped }: { activeAt: number | null; stopped: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (stopped) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [stopped]);
  const seconds = activeAt ? Math.max(0, Math.floor((now - activeAt) / 1000)) : 0;
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return (
    <span className="ml-1 rounded-xs bg-raised px-1.5 py-0.5 font-mono text-mono font-semibold text-fg tabular-nums">
      <span className="sr-only">Elapsed time </span>
      <span role="timer" aria-live="off">
        {mm}:{ss}
      </span>
    </span>
  );
}
