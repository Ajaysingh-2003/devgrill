"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
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
  waiting: { text: "Waiting for your practice system", tone: "text-fg-muted" },
  ended: { text: "This drill has ended", tone: "text-fg-subtle" },
};

/** The command palette's "screen reader mode" command (only screen readers notice it). */
export const SCREEN_READER_EVENT = "devgrill:terminal-screen-reader";

export function TerminalPanel() {
  const [status, setStatus] = useState<TerminalStatus>("connecting");
  const [screenReader, setScreenReader] = useState(false);
  useEffect(() => {
    const toggle = () => setScreenReader((v) => !v);
    window.addEventListener(SCREEN_READER_EVENT, toggle);
    return () => window.removeEventListener(SCREEN_READER_EVENT, toggle);
  }, []);
  return (
    <PanelFrame
      id="terminal"
      title="Terminal"
      meta={
        <span role="status" className={cn("font-mono", STATUS[status].tone)}>
          oncall@shopkart: {STATUS[status].text}
          {screenReader ? <span className="sr-only">, screen reader mode on</span> : null}
        </span>
      }
      // xterm scrolls its own buffer: the panel body never shows scrollbars of its own.
      bodyClassName="bg-sunken overflow-hidden"
    >
      <TerminalView screenReader={screenReader} onStatus={(s) => setStatus(s)} />
    </PanelFrame>
  );
}
