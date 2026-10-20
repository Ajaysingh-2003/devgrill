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

export type WorkspacePreset = {
  id: string;
  label: string;
  /** Percentages for primary / secondary / side; must add up to 100. */
  layout: Record<PanelSlot, number>;
};

export const WORKSPACE_PRESETS: WorkspacePreset[] = [
  { id: "triage", label: "Triage", layout: { primary: 46, secondary: 30, side: 24 } },
  { id: "debug", label: "Debug", layout: { primary: 34, secondary: 44, side: 22 } },
  { id: "comms", label: "Comms", layout: { primary: 38, secondary: 22, side: 40 } },
  { id: "postmortem", label: "Postmortem", layout: { primary: 60, secondary: 0, side: 40 } },
];

const SLOTS: PanelSlot[] = ["primary", "secondary", "side"];

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
 * The incident workspace's resizable area: three panels with keyboard-accessible splitters
 * (WAI-ARIA window splitter), layout presets (⌘/Ctrl+1–4), focus mode (F to maximise the
 * panel holding focus, Esc to restore) and a layout remembered per device.
 */
export function WorkspaceLayout({
  primary,
  secondary,
  side,
  storageId = "devgrill-workspace",
  onPresetChange,
}: {
  primary: ReactNode;
  secondary: ReactNode;
  side: ReactNode;
  storageId?: string;
  onPresetChange?: (preset: WorkspacePreset) => void;
}) {
  const groupRef = useGroupRef();
  const [focused, setFocused] = useState<PanelSlot | null>(null);
  const beforeFocus = useRef<Layout | null>(null);
  const panelRefs = useRef<Record<PanelSlot, HTMLElement | null>>({
    primary: null,
    secondary: null,
    side: null,
  });
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({
    id: storageId,
    panelIds: SLOTS,
    storage: safeStorage,
  });

  // A collapsed panel is 0px wide but still in the DOM: make it inert so Tab can't land on
  // controls nobody can see (focus mode and the Postmortem preset both collapse panels).
  function syncInert(layout: Layout) {
    for (const slot of SLOTS) {
      panelRefs.current[slot]?.toggleAttribute("inert", (layout[slot] ?? 0) === 0);
    }
  }
  function handleLayoutChanged(layout: Layout, meta: LayoutChangedMeta) {
    syncInert(layout);
    onLayoutChanged(layout, meta);
  }
  useEffect(() => {
    const layout = groupRef.current?.getLayout();
    if (layout) syncInert(layout);
    // Mount only: later changes arrive through onLayoutChanged.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyPreset(preset: WorkspacePreset) {
    setFocused(null);
    groupRef.current?.setLayout(preset.layout);
    onPresetChange?.(preset);
  }

  // ⌘/Ctrl + 1–4 switch presets (one listener for all four).
  const applyPresetRef = useRef(applyPreset);
  applyPresetRef.current = applyPreset;
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const isMac = navigator.platform.toLowerCase().includes("mac");
      if (!(isMac ? event.metaKey : event.ctrlKey) || event.shiftKey || event.altKey) return;
      const preset = WORKSPACE_PRESETS[Number(event.key) - 1];
      if (!preset) return;
      event.preventDefault();
      applyPresetRef.current(preset);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useHotkey("f", () => {
    const slot = SLOTS.find((s) => panelRefs.current[s]?.contains(document.activeElement));
    if (!slot || !groupRef.current) return;
    beforeFocus.current = groupRef.current.getLayout();
    groupRef.current.setLayout(Object.fromEntries(SLOTS.map((s) => [s, s === slot ? 100 : 0])));
    setFocused(slot);
  });

  useHotkey("escape", () => {
    if (!focused || !beforeFocus.current) return;
    groupRef.current?.setLayout(beforeFocus.current);
    setFocused(null);
  });

  // Announce focus mode for screen readers.
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    setAnnouncement(focused ? `${focused} panel maximised. Press Escape to restore.` : "");
  }, [focused]);

  const separator = cn(
    "relative w-px bg-border transition-colors duration-[var(--duration-fast)] outline-none",
    "data-[separator]:hover:bg-brand",
    // The 1px line alone is too faint as a focus indicator: show the full 8px hit area.
    "after:absolute after:inset-y-0 after:-left-1 after:w-2 after:rounded-full after:content-['']",
    "focus-visible:bg-brand focus-visible:after:bg-focus-ring/40",
  );

  return (
    <>
      <Group
        groupRef={groupRef}
        orientation="horizontal"
        defaultLayout={defaultLayout ?? WORKSPACE_PRESETS[0]!.layout}
        onLayoutChanged={handleLayoutChanged}
        resizeTargetMinimumSize={{ coarse: 32, fine: 8 }}
        className="h-full min-h-0"
      >
        <Panel
          id="primary"
          minSize="20%"
          collapsible
          collapsedSize="0%"
          elementRef={(el) => {
            panelRefs.current.primary = el;
          }}
        >
          {primary}
        </Panel>
        <Separator className={separator} aria-label="Resize primary and secondary panels" />
        <Panel
          id="secondary"
          minSize="16%"
          collapsible
          collapsedSize="0%"
          elementRef={(el) => {
            panelRefs.current.secondary = el;
          }}
        >
          {secondary}
        </Panel>
        <Separator className={separator} aria-label="Resize secondary panel and war room" />
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
      <PresetSwitcherSlot applyPreset={applyPreset} />
    </>
  );
}

// The preset switcher is rendered by the workspace's incident bar; expose apply via context-free event.
function PresetSwitcherSlot({ applyPreset }: { applyPreset: (p: WorkspacePreset) => void }) {
  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      const preset = WORKSPACE_PRESETS.find((p) => p.id === id);
      if (preset) applyPreset(preset);
    };
    window.addEventListener("devgrill:preset", handler);
    return () => window.removeEventListener("devgrill:preset", handler);
  }, [applyPreset]);
  return null;
}

/** Ask the mounted WorkspaceLayout to switch preset (used by toolbar buttons and the palette). */
export function requestPreset(id: string) {
  window.dispatchEvent(new CustomEvent("devgrill:preset", { detail: id }));
}
