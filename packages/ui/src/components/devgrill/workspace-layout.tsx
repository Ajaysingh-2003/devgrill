"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Group,
  Panel,
  Separator,
  useDefaultLayout,
  useGroupRef,
  type Layout,
  type LayoutChangedMeta,
} from "react-resizable-panels";
import { useHotkey } from "@devgrill/ui/hooks/use-hotkey";
import { cn } from "@devgrill/ui/lib/utils";

export type PanelSlot = "primary" | "secondary" | "side";

/**
 * Percentages. `main` / `side` split the width (the work area and the war room); `primary` /
 * `secondary` split the work area's height (the tool on top, the terminal below).
 */
const DEFAULT_LAYOUT = { main: 76, side: 24, primary: 62, secondary: 38 };

const SLOTS: PanelSlot[] = ["primary", "secondary", "side"];
/** How focus mode names each panel to screen readers. */
const PANEL_NAMES: Record<PanelSlot, string> = {
  primary: "Tool panel",
  secondary: "Terminal",
  side: "Team chat",
};
const COLUMNS = ["main", "side"];
const ROWS = ["primary", "secondary"];

/** localStorage that is safe during SSR and in private browsing (falls back to no persistence). */
const safeStorage = {
  getItem(key: string): string | null {
    if (typeof window === "undefined") return null;
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string): void {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Storage unavailable: the layout still works, it just isn't remembered.
    }
  },
};

/**
 * The incident workspace's resizable area, laid out like an IDE: the active tool on top, the
 * terminal across the bottom, the war room down the right. Keyboard-accessible splitters
 * (WAI-ARIA window splitter), focus mode (F to maximise the panel holding focus, Esc to
 * restore) and a layout remembered per device.
 */
export function WorkspaceLayout({
  primary,
  secondary,
  side,
  storageId = "devgrill-workspace-v2",
}: {
  primary: ReactNode;
  secondary: ReactNode;
  side: ReactNode;
  storageId?: string;
}) {
  const columnsRef = useGroupRef();
  const rowsRef = useGroupRef();
  const [focused, setFocused] = useState<PanelSlot | null>(null);
  const beforeFocus = useRef<{ columns: Layout; rows: Layout } | null>(null);
  const panelRefs = useRef<Record<PanelSlot, HTMLElement | null>>({
    primary: null,
    secondary: null,
    side: null,
  });
  const columns = useDefaultLayout({ id: `${storageId}-columns`, panelIds: COLUMNS, storage: safeStorage });
  const rows = useDefaultLayout({ id: `${storageId}-rows`, panelIds: ROWS, storage: safeStorage });

  // A collapsed panel is 0px but still in the DOM: make it inert so Tab can't land on controls
  // nobody can see (focus mode collapses the other panels).
  function syncInert() {
    const c = columnsRef.current?.getLayout() ?? {};
    const r = rowsRef.current?.getLayout() ?? {};
    const main = c.main ?? 1;
    const size: Record<PanelSlot, number> = {
      primary: main && (r.primary ?? 1),
      secondary: main && (r.secondary ?? 1),
      side: c.side ?? 1,
    };
    for (const slot of SLOTS) panelRefs.current[slot]?.toggleAttribute("inert", size[slot] === 0);
  }
  useEffect(() => {
    syncInert();
    // Mount only: later changes arrive through onLayoutChanged.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setLayouts(c: Layout, r: Layout) {
    columnsRef.current?.setLayout(c);
    rowsRef.current?.setLayout(r);
  }

  useHotkey("f", () => {
    const slot = SLOTS.find((s) => panelRefs.current[s]?.contains(document.activeElement));
    const c = columnsRef.current?.getLayout();
    const r = rowsRef.current?.getLayout();
    if (!slot || !c || !r) return;
    beforeFocus.current = { columns: c, rows: r };
    if (slot === "side") setLayouts({ main: 0, side: 100 }, r);
    else
      setLayouts(
        { main: 100, side: 0 },
        slot === "primary" ? { primary: 100, secondary: 0 } : { primary: 0, secondary: 100 },
      );
    setFocused(slot);
  });

  useHotkey("escape", () => {
    if (!focused || !beforeFocus.current) return;
    setLayouts(beforeFocus.current.columns, beforeFocus.current.rows);
    setFocused(null);
  });

  // Announce focus mode for screen readers.
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    setAnnouncement(focused ? `${PANEL_NAMES[focused]} maximised. Press Escape to restore.` : "");
  }, [focused]);

  const separator = (direction: "columns" | "rows") =>
    cn(
      "relative bg-border transition-colors duration-[var(--duration-fast)] outline-none",
      "data-[separator]:hover:bg-brand",
      "focus-visible:bg-brand focus-visible:after:bg-focus-ring/40",
      // The 1px line alone is too faint as a focus indicator: show the full 8px hit area.
      direction === "columns"
        ? "w-px after:absolute after:inset-y-0 after:-left-1 after:w-2 after:rounded-full after:content-['']"
        : "h-px after:absolute after:inset-x-0 after:-top-1 after:h-2 after:rounded-full after:content-['']",
    );

  return (
    <>
      <Group
        groupRef={columnsRef}
        orientation="horizontal"
        defaultLayout={columns.defaultLayout ?? { main: DEFAULT_LAYOUT.main, side: DEFAULT_LAYOUT.side }}
        onLayoutChanged={(layout: Layout, meta: LayoutChangedMeta) => {
          syncInert();
          columns.onLayoutChanged(layout, meta);
        }}
        resizeTargetMinimumSize={{ coarse: 32, fine: 8 }}
        className="h-full min-h-0"
      >
        <Panel id="main" minSize="40%" collapsible collapsedSize="0%">
          <Group
            groupRef={rowsRef}
            orientation="vertical"
            defaultLayout={
              rows.defaultLayout ?? { primary: DEFAULT_LAYOUT.primary, secondary: DEFAULT_LAYOUT.secondary }
            }
            onLayoutChanged={(layout: Layout, meta: LayoutChangedMeta) => {
              syncInert();
              rows.onLayoutChanged(layout, meta);
            }}
            resizeTargetMinimumSize={{ coarse: 32, fine: 8 }}
            className="h-full min-h-0"
          >
            <Panel
              id="primary"
              minSize="25%"
              collapsible
              collapsedSize="0%"
              elementRef={(el) => {
                panelRefs.current.primary = el;
              }}
            >
              {primary}
            </Panel>
            <Separator className={separator("rows")} aria-label="Resize the tool panel and the terminal" />
            <Panel
              id="secondary"
              minSize="15%"
              collapsible
              collapsedSize="0%"
              elementRef={(el) => {
                panelRefs.current.secondary = el;
              }}
            >
              {secondary}
            </Panel>
          </Group>
        </Panel>
        <Separator className={separator("columns")} aria-label="Resize the work area and the team chat" />
        <Panel
          id="side"
          minSize="18%"
          collapsible
          collapsedSize="0%"
          elementRef={(el) => {
            panelRefs.current.side = el;
          }}
        >
          {side}
        </Panel>
      </Group>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </>
  );
}
