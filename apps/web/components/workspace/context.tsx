"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ProblemError } from "@/lib/browser-api";
import {
  useStore,
  type IncidentSnapshot,
  type LogsSnapshot,
  type TelemetrySnapshot,
  type WorkspaceSource,
} from "./model";

const SourceContext = createContext<WorkspaceSource | null>(null);

export function SourceProvider({ source, children }: { source: WorkspaceSource; children: ReactNode }) {
  useEffect(() => source.start(), [source]);
  return <SourceContext.Provider value={source}>{children}</SourceContext.Provider>;
}

export function useSource(): WorkspaceSource {
  const source = useContext(SourceContext);
  if (!source) throw new Error("useSource outside a SourceProvider");
  return source;
}

export const useIncident = (): IncidentSnapshot => useStore(useSource().incident);
export const useTelemetry = (): TelemetrySnapshot => useStore(useSource().telemetry);
export const useLogs = (): LogsSnapshot => useStore(useSource().logs);

export type Poll<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
};

/**
 * Call `fetcher` now and every `everyMs` while the panel is mounted and the tab visible.
 * Keeps the last good data on errors (panels never blank during a hiccup).
 */
export function usePoll<T>(fetcher: () => Promise<T>, everyMs: number | null): Poll<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  useLayoutEffect(() => {
    fetcherRef.current = fetcher;
  });
  const inflight = useRef(false);

  const refresh = useCallback(() => {
    if (inflight.current) return;
    inflight.current = true;
    fetcherRef
      .current()
      .then((value) => {
        setData(value);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof ProblemError ? err.message : "Couldn't load this."))
      .finally(() => {
        inflight.current = false;
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    refresh();
    if (everyMs === null) return;
    const id = setInterval(() => {
      if (!document.hidden) refresh();
    }, everyMs);
    return () => clearInterval(id);
  }, [everyMs, refresh]);

  return { data, error, loading, refresh };
}

/** Run an action, tracking busy and error state for the button that started it. */
export function useAction<A extends unknown[], R>(action: (...args: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (...args: A): Promise<R | undefined> => {
      setBusy(true);
      setError(null);
      try {
        return await action(...args);
      } catch (err) {
        setError(err instanceof ProblemError ? err.message : "That didn't work. Try again.");
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [action],
  );
  return { run, busy, error, clearError: () => setError(null) };
}
