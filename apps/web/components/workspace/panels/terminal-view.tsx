"use client";

import { FitAddon } from "@xterm/addon-fit";
import { Terminal, type ITheme } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { useEffect, useLayoutEffect, useRef } from "react";
import { ProblemError } from "@/lib/browser-api";
import { useSource } from "../context";
import { ENDED, type TerminalLink } from "../model";

export type TerminalStatus = "connecting" | "open" | "reconnecting" | "waiting" | "ended";

const BACKOFF_MS = [500, 1000, 2000, 5000, 10_000];
const PING_EVERY_MS = 25_000;
/** The shell redraws its screen on every resize: tell it once the size has settled. */
const RESIZE_SETTLE_MS = 150;

const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

function theme(): ITheme {
  return {
    background: cssVar("sunken"),
    foreground: cssVar("text"),
    cursor: cssVar("text"),
    cursorAccent: cssVar("sunken"),
    selectionBackground: cssVar("brand-subtle"),
  };
}

/**
 * The shell, in xterm.js. Keystrokes go out as binary frames, resizes as JSON. On a lost
 * connection it reconnects with backoff and tmux puts you back where you were.
 * Loaded only when the terminal panel is shown (xterm is the heaviest part of the page).
 */
export default function TerminalView({
  screenReader,
  onStatus,
}: {
  screenReader: boolean;
  onStatus: (status: TerminalStatus, detail?: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const source = useSource();
  const statusRef = useRef(onStatus);
  useLayoutEffect(() => {
    statusRef.current = onStatus;
  });

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const code = cssVar("font-code");
    const term = new Terminal({
      fontFamily: code ? `${code}, ui-monospace, monospace` : "ui-monospace, monospace",
      fontSize: 13,
      lineHeight: 1.2,
      // Nothing animates on streaming panels (CLAUDE.md, motion): a steady cursor.
      cursorBlink: false,
      scrollback: 5000,
      screenReaderMode: false,
      theme: theme(),
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(el);
    fit.fit();
    termRef.current = term;

    const encoder = new TextEncoder();
    let link: TerminalLink | null = null;
    let disposed = false;
    let tries = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const dataSub = term.onData((data) => link?.send(encoder.encode(data)));
    let resizeTimer: ReturnType<typeof setTimeout> | undefined;
    const resizeSub = term.onResize(({ cols, rows }) => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(
        () => link?.send(JSON.stringify({ type: "resize", cols, rows })),
        RESIZE_SETTLE_MS,
      );
    });

    function schedule(delay?: number) {
      clearTimeout(retry);
      const wait = delay ?? BACKOFF_MS[Math.min(tries, BACKOFF_MS.length - 1)]!;
      tries += 1;
      retry = setTimeout(() => void connect(), wait);
    }

    async function connect() {
      if (disposed) return;
      const state = source.incident.get().state;
      if (ENDED.has(state)) {
        statusRef.current("ended");
        return;
      }
      if (state === "provisioning") {
        statusRef.current("waiting"); // connects when the sandbox is up (subscription below)
        return;
      }
      statusRef.current(tries === 0 ? "connecting" : "reconnecting");
      try {
        link = await source.actions.openTerminal(term.cols, term.rows);
      } catch (err) {
        statusRef.current(
          err instanceof ProblemError && err.code === "attempt_ended" ? "ended" : "reconnecting",
        );
        if (!(err instanceof ProblemError && err.code === "attempt_ended")) schedule();
        return;
      }
      if (disposed) {
        link.close();
        return;
      }
      link.onopen = () => {
        tries = 0;
        statusRef.current("open");
      };
      link.onmessage = (data) => {
        // Text frames are control replies (pong); screen bytes are binary.
        if (typeof data !== "string") term.write(new Uint8Array(data));
      };
      link.onclose = (code, reason) => {
        link = null;
        if (disposed) return;
        if (code === 4410 || ENDED.has(source.incident.get().state)) {
          statusRef.current("ended");
        } else if (code === 4409) {
          statusRef.current("waiting", reason);
          schedule(3000);
        } else {
          statusRef.current("reconnecting");
          schedule();
        }
      };
    }

    const ping = setInterval(
      () => link?.send(JSON.stringify({ type: "ping", t: Date.now() })),
      PING_EVERY_MS,
    );
    // Refit at most once a frame, and only when the grid really changes size. Refitting on
    // every observation let a scrollbar appearing and disappearing feed back into the size,
    // which made the screen and the scrollbars flicker while the layout settled.
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const dims = fit.proposeDimensions();
        // Hidden (a collapsed panel) proposes nothing, or a degenerate grid: keep the old one.
        if (!dims || !Number.isFinite(dims.cols) || dims.cols < 2 || dims.rows < 2) return;
        if (dims.cols !== term.cols || dims.rows !== term.rows) term.resize(dims.cols, dims.rows);
      });
    });
    observer.observe(el);
    const themeObserver = new MutationObserver(() => {
      term.options.theme = theme();
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    void connect();

    // Connect once the sandbox is up; after a reset the shell restarts: reconnect promptly.
    let lastState = source.incident.get().state;
    const unsubscribe = source.incident.subscribe(() => {
      const state = source.incident.get().state;
      if (state === lastState) return;
      lastState = state;
      if (!link && !disposed && !ENDED.has(state) && state !== "provisioning") {
        tries = 0;
        schedule(300);
      }
    });

    return () => {
      disposed = true;
      unsubscribe();
      clearTimeout(retry);
      clearTimeout(resizeTimer);
      cancelAnimationFrame(frame);
      clearInterval(ping);
      observer.disconnect();
      themeObserver.disconnect();
      dataSub.dispose();
      resizeSub.dispose();
      link?.close();
      term.dispose();
      termRef.current = null;
    };
  }, [source]);

  useEffect(() => {
    const term = termRef.current;
    if (term) term.options.screenReaderMode = screenReader;
  }, [screenReader]);

  return <div ref={host} className="h-full min-h-0 w-full overflow-hidden p-2" data-hotkeys="off" />;
}
