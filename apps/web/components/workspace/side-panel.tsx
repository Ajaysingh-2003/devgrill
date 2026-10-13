"use client";

import { Send } from "lucide-react";
import { IncidentTimeline } from "@devgrill/ui/components/devgrill/incident-timeline";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@devgrill/ui/components/ui/tabs";
import { cn } from "@devgrill/ui/lib/utils";
import { TIMELINE, WAR_ROOM } from "@/lib/mock";

/** War room (AI teammates from phase 6) and the in-world incident timeline. */
export function SidePanel() {
  return (
    <section aria-label="War room and timeline" className="flex h-full min-h-0 flex-col bg-surface">
      <Tabs defaultValue="war-room" className="flex h-full min-h-0 flex-col gap-0">
        <TabsList className="h-10 w-full justify-start rounded-none border-b border-border bg-transparent px-2">
          <TabsTrigger value="war-room">War room</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>
        <TabsContent value="war-room" className="flex min-h-0 flex-1 flex-col">
          <ol
            aria-label="War room messages"
            className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-3"
          >
            {WAR_ROOM.map((m) => {
              const you = m.who === "You";
              const bot = m.role === "alert";
              return (
                <li key={m.id} className="grid grid-cols-[1.75rem_1fr] gap-2.5">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "grid size-7 place-items-center rounded-full text-caption font-semibold",
                      bot
                        ? "bg-danger-subtle text-danger-text"
                        : you
                          ? "bg-brand-subtle text-brand-text"
                          : "bg-raised text-fg-muted",
                    )}
                  >
                    {bot ? "!" : m.who.slice(0, 1)}
                  </span>
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <p className="text-caption text-fg-subtle">
                      <span className="font-semibold text-fg">{m.who}</span>
                      {bot ? "" : `, ${m.role}`} <time className="font-mono">{m.at}</time>
                    </p>
                    <p className="text-body text-fg">{m.text}</p>
                  </div>
                </li>
              );
            })}
          </ol>
          <form
            className="flex items-end gap-2 border-t border-border p-2"
            onSubmit={(e) => e.preventDefault()}
          >
            <label htmlFor="status-update" className="sr-only">
              Post a status update to the war room
            </label>
            <textarea
              id="status-update"
              name="update"
              rows={2}
              placeholder="Post an update: what you know, what you're doing next…"
              className="min-h-10 flex-1 resize-none rounded-sm border border-border-input bg-surface px-2.5 py-2 text-body text-fg placeholder:text-fg-subtle"
            />
            <button
              type="submit"
              aria-label="Send update"
              className="grid size-10 place-items-center rounded-sm bg-brand text-on-brand hover:bg-brand-hover"
            >
              <Send className="size-4" aria-hidden="true" />
            </button>
          </form>
        </TabsContent>
        <TabsContent value="timeline" className="min-h-0 flex-1 overflow-y-auto">
          <IncidentTimeline events={TIMELINE} />
        </TabsContent>
      </Tabs>
    </section>
  );
}
