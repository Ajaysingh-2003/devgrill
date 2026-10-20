"use client";

import { Accessibility } from "lucide-react";
import dynamic from "next/dynamic";
import { useState } from "react";
import { PanelFrame } from "@devgrill/ui/components/devgrill/panel-frame";
import { cn } from "@devgrill/ui/lib/utils";
import type { TerminalStatus } from "./terminal-view";

// xterm.js is the heaviest part of the page: it loads with this panel, not with the route.
const TerminalView = dynamic(() => import("./terminal-view"), {
  ssr: false,
  loading: () => <p className="p-3 font-mono text-mono text-fg-muted">Opening a shell…</p>,
});

const STATUS: Record<TerminalStatus, { text: string; tone: string }> = {
  connecting: { text: "Connecting", tone: "text-fg-muted" },
  open: { text: "Connected", tone: "text-success-text" },
  reconnecting: { text: "Reconnecting, your session is kept", tone: "text-warning-text" },
  waiting: { text: "Waiting for the sandbox", tone: "text-fg-muted" },
  ended: { text: "The incident has ended", tone: "text-fg-subtle" },
};

export function TerminalPanel() {
  const [status, setStatus] = useState<TerminalStatus>("connecting");
  const [screenReader, setScreenReader] = useState(false);
  return (
    <PanelFrame
      id="terminal"
      title="Terminal"
      meta={
        <span role="status" className={cn("font-mono", STATUS[status].tone)}>
          oncall@shopkart: {STATUS[status].text}
        </span>
      }
      actions={
        <button
          type="button"
          aria-pressed={screenReader}
          onClick={() => setScreenReader((v) => !v)}
          title="Screen reader mode: output is readable line by line"
          className="inline-flex h-7 items-center gap-1.5 rounded-sm px-2 text-label font-medium whitespace-nowrap text-fg-muted hover:bg-raised hover:text-fg"
        >
          <Accessibility className="size-3.5" aria-hidden="true" />
          Screen reader
        </button>
      }
      bodyClassName="bg-sunken"
    >
      <TerminalView screenReader={screenReader} onStatus={(s) => setStatus(s)} />
    </PanelFrame>
  );
}
