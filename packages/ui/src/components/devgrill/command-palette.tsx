"use client";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Command } from "cmdk";
import type { LucideIcon } from "lucide-react";
import { Search } from "lucide-react";
import { formatCombo, useHotkey } from "@devgrill/ui/hooks/use-hotkey";
import { useIsMac } from "@devgrill/ui/hooks/use-platform";
import { cn } from "@devgrill/ui/lib/utils";

export type PaletteCommand = {
  id: string;
  label: string;
  group: string;
  icon?: LucideIcon;
  /** e.g. "mod+shift+v", shown as a hint. */
  shortcut?: string;
  keywords?: string[];
  onSelect: () => void;
};

/**
 * ⌘K / Ctrl+K command palette. Opened from the keyboard it appears instantly (no animation,
 * docs/PLAN.md §7.5); a visible trigger button exists for mouse users.
 */
export function CommandPalette({
  commands,
  open,
  onOpenChange,
  placeholder = "Type a command or search…",
}: {
  commands: PaletteCommand[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  placeholder?: string;
}) {
  const isMac = useIsMac();
  useHotkey("mod+k", (e) => {
    e.preventDefault();
    onOpenChange(!open);
  });

  const groups = [...new Set(commands.map((c) => c.group))];

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-[var(--z-palette)] bg-overlay" />
        <DialogPrimitive.Popup
          className={cn(
            "fixed top-[12vh] left-1/2 z-[var(--z-palette)] w-[min(40rem,calc(100%-2rem))] -translate-x-1/2",
            "overflow-hidden rounded-lg border border-border bg-surface text-fg shadow-overlay outline-none",
          )}
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <Command label="Command palette" loop className="flex flex-col">
            <div className="flex items-center gap-2 border-b border-border px-3">
              <Search className="size-4 text-fg-subtle" aria-hidden="true" />
              <Command.Input
                autoFocus
                placeholder={placeholder}
                className="h-12 flex-1 bg-transparent text-body-lg text-fg outline-none placeholder:text-fg-subtle"
              />
              <kbd className="rounded-xs border border-border px-1.5 font-mono text-mono-sm text-fg-subtle">
                Esc
              </kbd>
            </div>
            <Command.List className="max-h-[min(24rem,60vh)] overflow-y-auto p-1.5">
              <Command.Empty className="px-3 py-8 text-center text-body text-fg-muted">
                No matching command. Try a panel name, “rollback” or “verify”.
              </Command.Empty>
              {groups.map((group) => (
                <Command.Group
                  key={group}
                  heading={group}
                  className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-caption [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-fg-subtle"
                >
                  {commands
                    .filter((c) => c.group === group)
                    .map((c) => {
                      const Icon = c.icon;
                      return (
                        <Command.Item
                          key={c.id}
                          value={`${c.group} ${c.label}`}
                          keywords={c.keywords}
                          onSelect={() => {
                            onOpenChange(false);
                            c.onSelect();
                          }}
                          className="flex h-9 cursor-default items-center gap-2.5 rounded-sm px-2 text-body text-fg data-[selected=true]:bg-raised"
                        >
                          {Icon ? (
                            <Icon className="size-4 text-fg-muted" strokeWidth={1.75} aria-hidden="true" />
                          ) : null}
                          <span className="flex-1 truncate">{c.label}</span>
                          {c.shortcut ? (
                            <span className="flex gap-1" aria-hidden="true">
                              {formatCombo(c.shortcut, isMac).map((k) => (
                                <kbd
                                  key={k}
                                  className="rounded-xs border border-border px-1 font-mono text-mono-sm text-fg-subtle"
                                >
                                  {k}
                                </kbd>
                              ))}
                            </span>
                          ) : null}
                        </Command.Item>
                      );
                    })}
                </Command.Group>
              ))}
            </Command.List>
          </Command>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
