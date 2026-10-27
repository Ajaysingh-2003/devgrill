"use client";

import { adminScenarioAction, type AdminScenario } from "@devgrill/api-client";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@devgrill/ui/components/ui/dialog";
import { ProblemError, browserApi, call } from "@/lib/browser-api";

type Action = NonNullable<AdminScenario["actions"]>[number];

const LABEL: Record<Action, string> = {
  submit: "Submit for review",
  send_back: "Send back",
  publish: "Publish",
  retire: "Retire",
  restore: "Restore",
};

/** The lifecycle buttons the caller's role allows for one scenario (the API checks again). */
export function ScenarioActions({ slug, actions }: { slug: string; actions: Action[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const noteId = useId();

  async function run(action: Action, withNote?: string) {
    setBusy(true);
    setError(null);
    try {
      await call(
        adminScenarioAction({
          client: browserApi(),
          path: { slug, action },
          body: { note: withNote ?? null },
        }),
      );
      setNoteOpen(false);
      setNote("");
      router.refresh();
    } catch (err) {
      setError(err instanceof ProblemError ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!actions.length) return <span className="text-caption text-fg-subtle">–</span>;
  return (
    <span className="flex flex-wrap items-center gap-2">
      {actions.map((action) => (
        <button
          key={action}
          type="button"
          disabled={busy}
          aria-label={`${LABEL[action]}: ${slug}`}
          onClick={() => (action === "send_back" ? setNoteOpen(true) : void run(action))}
          className={
            action === "publish"
              ? "h-8 rounded-sm bg-brand px-3 text-label font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
              : "h-8 rounded-sm border border-border-input px-3 text-label font-medium text-fg hover:bg-raised disabled:opacity-60"
          }
        >
          {LABEL[action]}
        </button>
      ))}
      {error ? (
        <span role="status" className="text-caption text-danger-text">
          {error}
        </span>
      ) : null}
      <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
        <DialogContent instant className="max-w-md">
          <DialogHeader>
            <DialogTitle>Send {slug} back to its author?</DialogTitle>
            <DialogDescription>It goes back to draft. Say what needs changing.</DialogDescription>
          </DialogHeader>
          <label htmlFor={noteId} className="text-label font-medium text-fg">
            What needs changing
          </label>
          <textarea
            id={noteId}
            value={note}
            maxLength={500}
            rows={4}
            onChange={(e) => setNote(e.target.value)}
            className="rounded-sm border border-border-input bg-surface p-2 text-body text-fg"
          />
          {error ? <p className="text-body text-danger-text">{error}</p> : null}
          <DialogFooter>
            <button
              type="button"
              onClick={() => setNoteOpen(false)}
              className="h-10 rounded-sm px-4 text-body font-medium text-fg hover:bg-raised"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || !note.trim()}
              onClick={() => void run("send_back", note.trim())}
              className="h-10 rounded-sm bg-brand px-4 text-body font-semibold text-on-brand disabled:opacity-60"
            >
              Send back
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </span>
  );
}
