"use client";

import { Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { IncidentTimeline, type TimelineEvent } from "@devgrill/ui/components/devgrill/incident-timeline";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@devgrill/ui/components/ui/tabs";
import { cn } from "@devgrill/ui/lib/utils";
import { useAction, useIncident, useSource } from "./context";
import { sinceStart, type IncidentEvent } from "./model";

/** Teammates in the war room: scripted beats, and replies when the player writes (ADR 016). */
const PERSONAS: Record<string, { name: string; role: string }> = {
  priya: { name: "Priya", role: "Product manager" },
  arjun: { name: "Arjun", role: "SRE" },
  meera: { name: "Meera", role: "Backend lead" },
};

const persona = (key: unknown) => {
  const k = String(key ?? "");
  return PERSONAS[k] ?? { name: k.charAt(0).toUpperCase() + k.slice(1), role: "Teammate" };
};

type Message = {
  id: number;
  who: string;
  role: string;
  at: string;
  text: string;
  kind: "alert" | "you" | "teammate";
};

function toMessage(e: IncidentEvent, activeAt: number | null): Message | null {
  const at = sinceStart(new Date(e.ts).getTime(), activeAt);
  switch (e.type) {
    case "alert":
      return {
        id: e.id,
        who: "PagerBot",
        role: "alert",
        at,
        kind: "alert",
        text: `${String(e.payload.severity)}: ${String(e.payload.title)}. Assigned to you.`,
      };
    case "beat": {
      const p = persona(e.payload.persona);
      return { id: e.id, who: p.name, role: p.role, at, kind: "teammate", text: String(e.payload.say) };
    }
    case "reply": {
      const p = persona(e.payload.persona);
      return { id: e.id, who: p.name, role: p.role, at, kind: "teammate", text: String(e.payload.text) };
    }
    case "message":
      return {
        id: e.id,
        who: "You",
        role: "Incident commander",
        at,
        kind: "you",
        text: String(e.payload.text),
      };
    default:
      return null;
  }
}

function toTimeline(e: IncidentEvent, activeAt: number | null): TimelineEvent | null {
  const at = sinceStart(new Date(e.ts).getTime(), activeAt);
  const p = e.payload;
  const id = String(e.id);
  switch (e.type) {
    case "alert":
      return { id, at, kind: "alert", text: `${String(p.severity)} page: ${String(p.title)}` };
    case "beat":
      return { id, at, kind: "beat", actor: persona(p.persona).name, text: String(p.say) };
    case "reply":
      return { id, at, kind: "beat", actor: persona(p.persona).name, text: String(p.text) };
    case "message":
      return { id, at, kind: "action", actor: "You", text: `Status update: ${String(p.text)}` };
    case "nudge":
      return { id, at, kind: "hint", text: `Nudge: ${String(p.text)}` };
    case "action":
      return {
        id,
        at,
        kind: "action",
        actor: p.source === "cli" ? "You (terminal)" : "You",
        text: `Restarted ${String(p.service)}`,
      };
    case "deploy":
      return {
        id,
        at,
        kind: "deploy",
        text: p.ok
          ? `Deployed ${String(p.service)} ${String(p.sha)}`
          : `Deploy of ${String(p.service)} failed health checks`,
      };
    case "rollback":
      return {
        id,
        at,
        kind: "rollback",
        text: p.ok
          ? `Rolled ${String(p.service)} back to ${String(p.sha)}`
          : `Rollback of ${String(p.service)} failed`,
      };
    case "hint":
      return { id, at, kind: "hint", text: `Hint ${String(p.tier)}: ${String(p.text)}` };
    case "verify": {
      const probes = (p.probes as { passed?: boolean }[] | undefined) ?? [];
      const passed = probes.filter((x) => x.passed).length;
      return {
        id,
        at,
        kind: "action",
        actor: "You",
        text: p.error
          ? "Verify couldn't finish (it doesn't count)"
          : `Ran verify: ${p.passed ? "passed" : "not fixed yet"} (${passed} of ${probes.length} checks)`,
      };
    }
    case "mitigation":
      return {
        id,
        at,
        kind: "action",
        actor: "You",
        text: p.correct
          ? "Declared mitigated: confirmed by the metrics"
          : "Declared mitigated, but the SLO still breaches",
      };
    case "state":
      if (p.to === "mitigated")
        return { id, at, kind: "alert", text: "Recovered: the SLO holds again (mitigated)" };
      if (p.to === "active" && p.reason === "the SLO broke again")
        return { id, at, kind: "alert", text: "The SLO broke again" };
      if (p.to === "verifying") return { id, at, kind: "action", actor: "Verifier", text: "Verify started" };
      return null;
    default:
      return null;
  }
}

/** War room (teammates who answer) and the in-world incident timeline. */
export function SidePanel() {
  const { info } = useSource();
  const { events, activeAt } = useIncident();
  const warRoom = info.unlocked_tools.includes("war_room");
  const messages = useMemo(
    () => events.map((e) => toMessage(e, activeAt)).filter((m): m is Message => m !== null),
    [events, activeAt],
  );
  const timeline = useMemo(
    () => events.map((e) => toTimeline(e, activeAt)).filter((t): t is TimelineEvent => t !== null),
    [events, activeAt],
  );

  return (
    <section
      aria-label={warRoom ? "War room and timeline" : "Timeline"}
      className="flex h-full min-h-0 flex-col bg-surface"
    >
      <Tabs defaultValue={warRoom ? "war-room" : "timeline"} className="flex h-full min-h-0 flex-col gap-0">
        <TabsList className="h-10 w-full justify-start rounded-none border-b border-border bg-transparent px-2">
          {warRoom ? <TabsTrigger value="war-room">War room</TabsTrigger> : null}
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>
        {warRoom ? (
          <TabsContent value="war-room" className="flex min-h-0 flex-1 flex-col">
            <WarRoom messages={messages} />
          </TabsContent>
        ) : null}
        <TabsContent value="timeline" className="min-h-0 flex-1 overflow-y-auto">
          {timeline.length ? (
            <IncidentTimeline events={timeline} />
          ) : (
            <p className="p-4 text-body text-fg-muted">The timeline starts with the page.</p>
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}

function WarRoom({ messages }: { messages: Message[] }) {
  const { actions } = useSource();
  const { assist } = useIncident();
  const [draft, setDraft] = useState("");
  const send = useAction(actions.message);
  const list = useRef<HTMLOListElement>(null);
  const typing = assist.typing ? persona(assist.typing.persona) : null;
  useEffect(() => {
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, assist.typing?.text]);
  return (
    <>
      <ol
        ref={list}
        aria-label="War room messages"
        aria-live="polite"
        className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-3"
      >
        {messages.map((m) => (
          <li key={m.id} className="grid grid-cols-[1.75rem_1fr] gap-2.5">
            <span
              aria-hidden="true"
              className={cn(
                "grid size-7 place-items-center rounded-full text-caption font-semibold",
                m.kind === "alert"
                  ? "bg-danger-subtle text-danger-text"
                  : m.kind === "you"
                    ? "bg-brand-subtle text-brand-text"
                    : "bg-raised text-fg-muted",
              )}
            >
              {m.kind === "alert" ? "!" : m.who.slice(0, 1)}
            </span>
            <div className="flex min-w-0 flex-col gap-0.5">
              <p className="text-caption text-fg-subtle">
                <span className="font-semibold text-fg">{m.who}</span>
                {m.kind === "alert" ? "" : `, ${m.role}`} <time className="font-mono">{m.at}</time>
              </p>
              <p className="text-body text-fg">{m.text}</p>
            </div>
          </li>
        ))}
        {typing && assist.typing ? (
          // Streams in without motion. Hidden from screen readers: the finished reply is
          // announced once, when it lands in the list.
          <li aria-hidden="true" className="grid grid-cols-[1.75rem_1fr] gap-2.5">
            <span className="grid size-7 place-items-center rounded-full bg-raised text-caption font-semibold text-fg-muted">
              {typing.name.slice(0, 1)}
            </span>
            <div className="flex min-w-0 flex-col gap-0.5">
              <p className="text-caption text-fg-subtle">
                <span className="font-semibold text-fg">{typing.name}</span>, {typing.role}
              </p>
              <p className="text-body text-fg-muted">{assist.typing.text || "Typing…"}</p>
            </div>
          </li>
        ) : null}
      </ol>
      {assist.notice ? (
        <p role="status" className="border-t border-border px-3 py-2 text-caption text-fg-muted">
          {assist.notice}
        </p>
      ) : null}
      <form
        className="flex items-end gap-2 border-t border-border p-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const text = draft.trim();
          if (!text) return;
          await send.run(text);
          setDraft("");
        }}
      >
        <label htmlFor="status-update" className="sr-only">
          Post a status update to the war room
        </label>
        <textarea
          id="status-update"
          name="update"
          rows={2}
          maxLength={1000}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="Post an update: what you know, what you're doing next…"
          className="min-h-10 flex-1 resize-none rounded-sm border border-border-input bg-surface px-2.5 py-2 text-body text-fg placeholder:text-fg-subtle"
        />
        <button
          type="submit"
          aria-label="Send update"
          disabled={send.busy || !draft.trim()}
          className="grid size-10 place-items-center rounded-sm bg-brand text-on-brand hover:bg-brand-hover disabled:opacity-60"
        >
          <Send className="size-4" aria-hidden="true" />
        </button>
      </form>
      {send.error ? <p className="px-3 pb-2 text-caption text-danger-text">{send.error}</p> : null}
    </>
  );
}
