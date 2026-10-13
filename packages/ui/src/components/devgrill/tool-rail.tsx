"use client";

import type { LucideIcon } from "lucide-react";
import { useRef, type KeyboardEvent } from "react";
import { cn } from "@devgrill/ui/lib/utils";

export type Tool = {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Number of unseen alerts or events; shown as a badge. */
  badge?: number;
  disabled?: boolean;
};

/**
 * The workspace's vertical tool switcher. ARIA tabs (vertical): arrow keys move,
 * Home/End jump, number keys 1–9 are handled by the workspace hotkeys.
 */
export function ToolRail({
  tools,
  value,
  onValueChange,
  label = "Tools",
  panelId,
}: {
  tools: Tool[];
  value: string;
  onValueChange: (id: string) => void;
  label?: string;
  /** id of the element the selected tool controls (aria-controls). */
  panelId: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const enabled = tools.filter((t) => !t.disabled);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = enabled.findIndex((t) => t.id === value);
    let next: Tool | undefined;
    if (event.key === "ArrowDown") next = enabled[(index + 1) % enabled.length];
    else if (event.key === "ArrowUp") next = enabled[(index - 1 + enabled.length) % enabled.length];
    else if (event.key === "Home") next = enabled[0];
    else if (event.key === "End") next = enabled[enabled.length - 1];
    if (!next) return;
    event.preventDefault();
    onValueChange(next.id);
    refs.current[next.id]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      aria-orientation="vertical"
      onKeyDown={onKeyDown}
      className="flex w-full flex-col gap-0.5 p-1.5"
    >
      {tools.map((tool, i) => {
        const selected = tool.id === value;
        const Icon = tool.icon;
        return (
          <button
            key={tool.id}
            ref={(el) => {
              refs.current[tool.id] = el;
            }}
            role="tab"
            type="button"
            id={`tool-${tool.id}`}
            aria-selected={selected}
            aria-controls={panelId}
            tabIndex={selected ? 0 : -1}
            disabled={tool.disabled}
            onClick={() => onValueChange(tool.id)}
            className={cn(
              "group relative flex h-9 items-center gap-2.5 rounded-sm px-2.5 text-left text-label",
              "outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              "disabled:cursor-not-allowed disabled:opacity-45",
              selected ? "bg-raised font-medium text-fg" : "text-fg-muted hover:bg-raised hover:text-fg",
            )}
          >
            {selected ? (
              <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-brand" />
            ) : null}
            <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
            <span className="flex-1 truncate">{tool.label}</span>
            {tool.badge ? (
              <span className="rounded-full bg-danger-solid px-1.5 text-caption font-semibold text-on-danger tabular-nums">
                {tool.badge}
                <span className="sr-only"> new</span>
              </span>
            ) : (
              <kbd
                aria-hidden="true"
                className="font-mono text-mono-sm text-fg-subtle opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
              >
                {i + 1}
              </kbd>
            )}
          </button>
        );
      })}
    </div>
  );
}
