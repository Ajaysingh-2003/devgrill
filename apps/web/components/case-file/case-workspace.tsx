"use client";

import { getCaseEvidence, type CaseEvidenceOut, type CaseFileOut } from "@devgrill/api-client";
import { History, Laptop } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ToolRail } from "@devgrill/ui/components/devgrill/tool-rail";
import { WorkspaceLayout } from "@devgrill/ui/components/devgrill/workspace-layout";
import { isTypingTarget } from "@devgrill/ui/hooks/use-hotkey";
import { DevGrillMark } from "@devgrill/ui/icons";
import { browserApi, call, ProblemError } from "@/lib/browser-api";
import { SourceProvider } from "../workspace/context";
import { PANELS, TOOLS } from "../workspace/panels";
import { createRecordedSource } from "../workspace/recorded-source";
import { CaseSide } from "./case-side";
import { RecordedCommands } from "./recorded-commands";

const PANEL_NAMES = { secondary: "Commands", side: "Your findings" };

/** A case file (ADR 018): the workspace's panels, read-only, with questions instead of a terminal. */
export function CaseWorkspace({ file }: { file: CaseFileOut }) {
  const [evidence, setEvidence] = useState<CaseEvidenceOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    call(getCaseEvidence({ client: browserApi(), path: { slug: file.slug } }))
      .then((data) => current && setEvidence(data as CaseEvidenceOut))
      .catch(
        (err: unknown) =>
          current && setError(err instanceof ProblemError ? err.message : "Couldn't open the recording."),
      );
    return () => {
      current = false;
    };
  }, [file.slug, attempt]);

  if (!evidence) {
    return (
      <main id="main" className="grid min-h-dvh place-items-center p-6 text-center">
        {error ? (
          <div className="flex flex-col items-center gap-3">
            <p role="alert" className="text-body text-danger-text">
              {error}
            </p>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
              className="h-10 rounded-sm border border-border-input px-4 text-body font-medium text-fg hover:bg-raised"
            >
              Try again
            </button>
          </div>
        ) : (
          <p role="status" className="text-body text-fg-muted">
            Opening the recording…
          </p>
        )}
      </main>
    );
  }
  return <Shell file={file} evidence={evidence} />;
}

function Shell({ file, evidence }: { file: CaseFileOut; evidence: CaseEvidenceOut }) {
  const source = useMemo(() => createRecordedSource(file, evidence), [file, evidence]);
  const tools = useMemo(() => TOOLS.map((t) => ({ ...t, disabled: !file.tools.includes(t.key) })), [file]);
  const [tool, setTool] = useState(() => tools.find((t) => !t.disabled)?.id ?? "overview");
  const Active = PANELS[tool]!;

  // Number keys switch tools, as in a live incident.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      const next = tools[Number(event.key) - 1];
      if (next && !next.disabled) setTool(next.id);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [tools]);

  const sev = Number(file.page?.severity.replace("SEV", "") ?? 3) as 1 | 2 | 3 | 4;
  return (
    <SourceProvider source={source}>
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center lg:hidden">
        <Laptop className="size-8 text-fg-muted" aria-hidden="true" />
        <h1 className="text-heading-lg font-semibold text-fg">This case file needs a bigger screen</h1>
        <p className="max-w-sm text-body text-fg-muted">
          The evidence is logs, charts and code side by side. Open it on a laptop, or keep practising here
          with Quick Fire.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <Link
            href="/quickfire"
            className="inline-flex h-10 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand"
          >
            Play Quick Fire
          </Link>
          <Link
            href="/case-files"
            className="inline-flex h-10 items-center rounded-sm px-4 text-body font-medium text-fg hover:bg-raised"
          >
            Back to case files
          </Link>
        </div>
      </div>

      <div className="relative hidden h-dvh min-h-[40rem] flex-col lg:flex">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-surface px-3">
          <Link href="/case-files" aria-label="Back to case files" className="rounded-sm p-1 text-fg">
            <DevGrillMark className="size-5" />
          </Link>
          {file.page ? <SevBadge sev={sev} size="md" /> : null}
          <h1 className="truncate text-body font-semibold text-fg">{file.title}</h1>
          {file.page ? (
            <span className="hidden truncate text-label text-fg-muted xl:inline">{file.page.title}</span>
          ) : null}
          <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 text-label text-fg-muted">
            <History className="size-4" aria-hidden="true" />
            Recorded from a real run. Nothing here can be changed.
          </span>
        </header>
        <div className="flex min-h-0 flex-1">
          <aside aria-label="Tools" className="w-44 shrink-0 border-r border-border bg-surface">
            <ToolRail tools={tools} value={tool} onValueChange={setTool} panelId="tool-panel" />
          </aside>
          <main id="main" className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1">
              <WorkspaceLayout
                primary={<Active />}
                secondary={<RecordedCommands />}
                side={<CaseSide file={file} onPanel={setTool} />}
                storageId="devgrill-case-file-v1"
                panelNames={PANEL_NAMES}
              />
            </div>
          </main>
        </div>
      </div>
    </SourceProvider>
  );
}
