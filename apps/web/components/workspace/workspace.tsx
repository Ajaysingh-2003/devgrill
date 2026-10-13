"use client";

import {
  Code2,
  Database,
  GitBranch,
  Gauge,
  LayoutPanelLeft,
  Lightbulb,
  ScrollText,
  ShieldCheck,
  Zap,
  Laptop,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CommandPalette, type PaletteCommand } from "@devgrill/ui/components/devgrill/command-palette";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ToolRail, type Tool } from "@devgrill/ui/components/devgrill/tool-rail";
import {
  WORKSPACE_PRESETS,
  WorkspaceLayout,
  requestPreset,
} from "@devgrill/ui/components/devgrill/workspace-layout";
import { isTypingTarget, useHotkey } from "@devgrill/ui/hooks/use-hotkey";
import { DevGrillMark } from "@devgrill/ui/icons";
import { cn } from "@devgrill/ui/lib/utils";
import { INCIDENT, scenario } from "@/lib/mock";
import { SidePanel } from "./side-panel";
import {
  CachePanel,
  CodePanel,
  DatabasePanel,
  DeploysPanel,
  LogsPanel,
  OverviewPanel,
  TerminalPanel,
} from "./tool-panels";

const TOOLS: Tool[] = [
  { id: "overview", label: "Overview", icon: Gauge, badge: 2 },
  { id: "logs", label: "Logs", icon: ScrollText },
  { id: "database", label: "Database", icon: Database },
  { id: "cache", label: "Cache", icon: Zap },
  { id: "code", label: "Code", icon: Code2 },
  { id: "deploys", label: "Deploys", icon: GitBranch },
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
const CURRENT_PHASE = 1;

export function Workspace({ attemptId }: { attemptId: string }) {
  const s = scenario(INCIDENT.scenario)!;
  const [tool, setTool] = useState("overview");
  const [preset, setPreset] = useState(WORKSPACE_PRESETS[0]!.id);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const Active = PANELS[tool]!;

  // The alert region starts empty and the page text is inserted after mount: text that is
  // already in a server-rendered alert is often not announced.
  const [paged, setPaged] = useState("");
  useEffect(() => {
    const id = window.setTimeout(() => setPaged(`Paged: ${INCIDENT.page}`), 400);
    return () => window.clearTimeout(id);
  }, []);

  // Number keys 1–6 switch tools (not while typing in the terminal, editor or inputs).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      const next = TOOLS[Number(event.key) - 1];
      if (next) setTool(next.id);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Incident actions: listed in the palette and bound to the shortcuts it shows.
  const incidentCommands: PaletteCommand[] = [
    {
      id: "hint",
      group: "Incident",
      label: "Request a hint",
      icon: Lightbulb,
      shortcut: "h",
      onSelect: () => toast("Hints arrive in phase 4"),
    },
    {
      id: "mitigated",
      group: "Incident",
      label: "Declare mitigated",
      icon: ShieldCheck,
      shortcut: "m",
      onSelect: () => toast("Mitigation is checked against real recovery from phase 4"),
    },
    {
      id: "verify",
      group: "Incident",
      label: "Run verify",
      icon: ShieldCheck,
      shortcut: "mod+shift+v",
      onSelect: () => toast("Verify runs from phase 5"),
    },
  ];
  const runCommand = (id: string) => incidentCommands.find((c) => c.id === id)?.onSelect();
  useHotkey("h", () => runCommand("hint"));
  useHotkey("m", () => runCommand("mitigated"));
  useHotkey("mod+shift+v", (event) => {
    event.preventDefault();
    runCommand("verify");
  });

  const commands: PaletteCommand[] = [
    ...TOOLS.map((t, i) => ({
      id: `tool-${t.id}`,
      group: "Panels",
      label: `Open ${t.label}`,
      icon: t.icon,
      shortcut: String(i + 1),
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
    ...incidentCommands,
  ];

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

      <div className="hidden h-dvh min-h-[40rem] flex-col lg:flex">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-surface px-3">
          <Link
            href="/drills"
            aria-label="Leave the incident and go to drills"
            className="rounded-sm p-1 text-fg"
          >
            <DevGrillMark className="size-5" />
          </Link>
          <SevBadge sev={INCIDENT.sev} size="md" />
          <h1 className="truncate text-body font-semibold text-fg">{s.title}</h1>
          <span className="hidden truncate text-label text-fg-muted xl:inline">{INCIDENT.page}</span>
          <ElapsedClock startSeconds={492} />
          <p className="ml-2 text-caption text-fg-muted 2xl:hidden">
            Step {CURRENT_PHASE + 1} of {PHASES.length}:{" "}
            <span className="font-semibold text-brand-text">{PHASES[CURRENT_PHASE]}</span>
          </p>

          <ol aria-label="Incident phases" className="ml-auto hidden items-center gap-1 2xl:flex">
            {PHASES.map((p, i) => (
              <li
                key={p}
                aria-current={i === CURRENT_PHASE ? "step" : undefined}
                className={cn(
                  "rounded-full px-2 py-0.5 text-caption",
                  i < CURRENT_PHASE && "text-success-text",
                  i === CURRENT_PHASE && "bg-brand-subtle font-semibold text-brand-text",
                  i > CURRENT_PHASE && "text-fg-subtle",
                )}
              >
                {p}
                {i < CURRENT_PHASE ? <span className="sr-only"> (done)</span> : null}
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
          <button
            type="button"
            onClick={() => toast("Hints arrive in phase 4")}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border-input px-2.5 text-label font-medium text-fg hover:bg-raised"
          >
            <Lightbulb className="size-3.5" aria-hidden="true" />
            Hint
          </button>
          <Link
            href={`/incident/${attemptId}/debrief`}
            className="inline-flex h-8 items-center rounded-sm bg-brand px-3 text-label font-semibold text-on-brand hover:bg-brand-hover"
          >
            Verify
          </Link>
        </header>

        <div className="flex min-h-0 flex-1">
          {/* A tablist, not navigation: it switches the panel in place. */}
          <aside aria-label="Incident tools" className="w-44 shrink-0 border-r border-border bg-surface">
            <ToolRail tools={TOOLS} value={tool} onValueChange={setTool} panelId="tool-panel" />
          </aside>
          <main id="main" className="min-w-0 flex-1">
            <WorkspaceLayout
              primary={<Active />}
              secondary={<TerminalPanel />}
              side={<SidePanel />}
              onPresetChange={(p) => setPreset(p.id)}
            />
          </main>
        </div>
      </div>

      {/* Genuine pages are the only assertive announcements in the workspace. */}
      <p role="alert" className="sr-only">
        {paged}
      </p>
      <CommandPalette commands={commands} open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  );
}

function ElapsedClock({ startSeconds }: { startSeconds: number }) {
  const [seconds, setSeconds] = useState(startSeconds);
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
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
