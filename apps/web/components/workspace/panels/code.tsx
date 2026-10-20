"use client";

import type { DeployOut } from "@devgrill/api-client";
import { CircleCheck, CircleX, FileCode2, Rocket, Save } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { cn } from "@devgrill/ui/lib/utils";
import { useAction, usePoll, useSource } from "../context";

const CodeEditor = dynamic(() => import("./code-editor"), {
  ssr: false,
  loading: () => <p className="p-3 font-mono text-mono text-fg-muted">Opening the editor…</p>,
});

type Buffer = { path: string; original: string; current: string };

export function CodePanel() {
  const { actions, info } = useSource();
  const service = info.deployable[0];
  const files = usePoll(() => actions.files(service), null);
  const [buffer, setBuffer] = useState<Buffer | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [result, setResult] = useState<DeployOut | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const bufferRef = useRef(buffer);
  useLayoutEffect(() => {
    bufferRef.current = buffer;
  });
  const save = useAction(async () => {
    const b = bufferRef.current;
    if (!b || b.current === b.original) return;
    await actions.writeFile(b.path, b.current, service);
    setBuffer((prev) => (prev && prev.path === b.path ? { ...prev, original: b.current } : prev));
    setSaved(b.path);
  });
  const deploy = useAction(async () => {
    setResult(null);
    await save.run();
    const out = await actions.deploy(service);
    setResult(out);
    return out;
  });

  const open = useCallback(
    async (path: string) => {
      if (bufferRef.current && bufferRef.current.current !== bufferRef.current.original) await save.run();
      setOpening(path);
      try {
        const content = await actions.readFile(path, service);
        setBuffer({ path, original: content, current: content });
        setSaved(null);
      } finally {
        setOpening(null);
      }
    },
    [actions, service, save],
  );

  if (!service) {
    return (
      <PanelFrame id="tool-panel" tab="tool-code" title="Code">
        <EmptyState icon={FileCode2} title="Nothing to edit here" compact>
          This incident is solved without changing code.
        </EmptyState>
      </PanelFrame>
    );
  }

  const dirty = buffer !== null && buffer.current !== buffer.original;
  return (
    <PanelFrame
      id="tool-panel"
      tab="tool-code"
      title="Code"
      meta={buffer ? `${service}/${buffer.path}${dirty ? " (unsaved)" : ""}` : `${service}: pick a file`}
      actions={
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void save.run()}
            disabled={!dirty || save.busy}
            className="inline-flex h-7 items-center gap-1.5 rounded-sm border border-border-input px-2.5 text-label font-medium text-fg hover:bg-raised disabled:opacity-50"
          >
            <Save className="size-3.5" aria-hidden="true" />
            Save
          </button>
          <button
            type="button"
            onClick={() => void deploy.run()}
            disabled={deploy.busy}
            aria-keyshortcuts="Control+Enter Meta+Enter"
            className="inline-flex h-7 items-center gap-1.5 rounded-sm bg-brand px-2.5 text-label font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
          >
            <Rocket className="size-3.5" aria-hidden="true" />
            {deploy.busy ? "Deploying…" : `Deploy ${service}`}
          </button>
        </div>
      }
      bodyClassName="flex flex-col"
    >
      <div className="flex min-h-0 flex-1">
        <nav
          aria-label="Files"
          className="w-48 shrink-0 overflow-y-auto border-r border-border bg-surface py-2"
        >
          {files.data ? (
            <ul className="font-mono text-mono-sm">
              {files.data.files.map((path) => (
                <li key={path}>
                  <button
                    type="button"
                    aria-current={buffer?.path === path ? "true" : undefined}
                    onClick={() => void open(path)}
                    className={cn(
                      "w-full truncate px-3 py-1 text-left hover:bg-raised",
                      buffer?.path === path ? "bg-brand-subtle text-brand-text" : "text-fg",
                    )}
                  >
                    {path}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-3 text-caption text-fg-muted">{files.error ?? "Listing files…"}</p>
          )}
        </nav>
        <div className="min-w-0 flex-1">
          {buffer ? (
            <CodeEditor
              key={buffer.path}
              path={buffer.path}
              value={buffer.original}
              onChange={(value) => setBuffer((b) => (b ? { ...b, current: value } : b))}
              onSave={() => void save.run()}
              onDeploy={() => void deploy.run()}
            />
          ) : (
            <EmptyState icon={FileCode2} title={opening ? `Opening ${opening}…` : "Open a file"} compact>
              The source of {service}, as a git repo. Your edits deploy with the Deploy button or Ctrl+Enter;
              the terminal has the same repo at /workspace/{service}.
            </EmptyState>
          )}
        </div>
      </div>
      <div aria-live="polite" className="shrink-0">
        {save.error || deploy.error ? (
          <p className="border-t border-border px-3 py-2 text-body text-danger-text">
            {save.error ?? deploy.error}
          </p>
        ) : null}
        {saved && !dirty && !result ? (
          <p className="border-t border-border px-3 py-2 text-caption text-fg-muted">
            Saved {saved}. Not deployed yet.
          </p>
        ) : null}
        {result ? (
          <div className="border-t border-border px-3 py-2">
            <p
              className={cn(
                "inline-flex items-center gap-1.5 text-body font-medium",
                result.ok ? "text-success-text" : "text-danger-text",
              )}
            >
              {result.ok ? (
                <CircleCheck className="size-4" aria-hidden="true" />
              ) : (
                <CircleX className="size-4" aria-hidden="true" />
              )}
              {result.message}
            </p>
            {!result.ok && result.log ? (
              <pre className="mt-1 max-h-32 overflow-auto font-mono text-mono-sm whitespace-pre-wrap text-fg-muted">
                {result.log}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>
    </PanelFrame>
  );
}
