"use client";

import { useEffect, useRef } from "react";

/**
 * Global keyboard shortcut. `combo` examples: "mod+k", "mod+1", "f", "shift+/", "escape".
 * `mod` is ⌘ on macOS and Ctrl elsewhere. Single-key shortcuts are ignored while the user is
 * typing (inputs, textareas, contenteditable, and anything marked data-hotkeys="off", such
 * as the terminal).
 */
export function useHotkey(
  combo: string,
  handler: (event: KeyboardEvent) => void,
  { enabled = true, allowInInputs = false }: { enabled?: boolean; allowInInputs?: boolean } = {},
) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!enabled) return;
    const parts = combo.toLowerCase().split("+");
    const key = parts.pop()!;
    const wantMod = parts.includes("mod");
    const wantShift = parts.includes("shift");
    const wantAlt = parts.includes("alt");

    function onKeyDown(event: KeyboardEvent) {
      const isMac = navigator.platform.toLowerCase().includes("mac");
      const mod = isMac ? event.metaKey : event.ctrlKey;
      if (mod !== wantMod || event.shiftKey !== wantShift || event.altKey !== wantAlt) return;
      if (event.key.toLowerCase() !== key) return;
      if (!allowInInputs && isTypingTarget(event.target) && !wantMod) return;
      handlerRef.current(event);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [combo, enabled, allowInInputs]);
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.closest("[data-hotkeys='off']")) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/** Human label for a combo on the current platform, e.g. "mod+k" → "⌘K" or "Ctrl K". */
export function formatCombo(combo: string, isMac: boolean): string[] {
  return combo.split("+").map((part) => {
    const p = part.toLowerCase();
    if (p === "mod") return isMac ? "⌘" : "Ctrl";
    if (p === "shift") return isMac ? "⇧" : "Shift";
    if (p === "alt") return isMac ? "⌥" : "Alt";
    if (p === "escape") return "Esc";
    if (p === "enter") return isMac ? "↩" : "Enter";
    return part.length === 1 ? part.toUpperCase() : part;
  });
}
