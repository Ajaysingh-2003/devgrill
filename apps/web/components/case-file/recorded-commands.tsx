"use client";

import { TriangleAlert } from "lucide-react";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { useSource } from "../workspace/context";

/** Where a live incident has its terminal: what was asked of the system, and what it said. */
export function RecordedCommands() {
  const { recorded, info } = useSource();
  const commands = recorded?.commands ?? [];
  return (
    <PanelFrame
      id="terminal"
      title="Commands"
      meta={`Run on ${info.host} while the incident was going`}
      bodyClassName="bg-sunken"
    >
      <ul className="flex flex-col gap-4 p-3">
        {commands.map((c) => (
          <li key={c.title}>
            <h3 className="text-label font-semibold text-fg">{c.title}</h3>
            <pre
              tabIndex={0}
              aria-label={`${c.title}: command and output`}
              className="mt-1 overflow-x-auto font-mono text-mono-sm leading-5 whitespace-pre"
            >
              <code className="block whitespace-pre-wrap text-brand-text">$ {c.command}</code>
              <code className="block text-fg">{c.output || "(no output)"}</code>
            </pre>
            {c.ok ? null : (
              <p className="mt-1 inline-flex items-center gap-1.5 text-caption text-warning-text">
                <TriangleAlert className="size-3.5" aria-hidden="true" />
                This command failed.
              </p>
            )}
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
