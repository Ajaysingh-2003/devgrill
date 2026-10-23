"use client";

import { savePostmortem, submitPostmortem, type PostmortemOut } from "@devgrill/api-client";
import { CircleCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { browserApi, call, ProblemError } from "@/lib/browser-api";
import { PostmortemReview } from "./review";

type Section = "summary" | "impact" | "cause" | "actions";

const SECTIONS: { id: Section; title: string; hint: string }[] = [
  { id: "summary", title: "Summary", hint: "Two or three sentences a director could read." },
  { id: "impact", title: "Impact", hint: "Who was affected, for how long, how badly." },
  { id: "cause", title: "Root cause", hint: "The change, the mechanism, and why it hurt now." },
  {
    id: "actions",
    title: "Action items",
    hint: "What stops this kind of problem happening again, with owners.",
  },
];
const SAVE_AFTER_MS = 1500;
const MAX_CHARS = 4000;

type Status = { kind: "idle" | "saving" | "saved" | "error"; at?: Date; message?: string };

/**
 * The postmortem editor (PLAN phase 5): four sections, saved as a draft while you type,
 * then submitted once (the incident's timeline is added from your session), then reviewed by
 * the AI against the scenario's rubric (ADR 016).
 */
export function PostmortemEditor({ attemptId, initial }: { attemptId: string; initial: PostmortemOut }) {
  const [sections, setSections] = useState<Record<Section, string>>(() => ({
    summary: initial.sections.summary ?? "",
    impact: initial.sections.impact ?? "",
    cause: initial.sections.cause ?? "",
    actions: initial.sections.actions ?? "",
  }));
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [submittedAt, setSubmittedAt] = useState(initial.submitted_at ?? null);
  const [submitting, setSubmitting] = useState(false);
  const [review, setReview] = useState(initial.review ?? null);
  const dirty = useRef(false);
  const readOnly = submittedAt !== null;

  // Save the draft a moment after typing stops.
  useEffect(() => {
    if (!dirty.current || readOnly) return;
    const id = window.setTimeout(async () => {
      setStatus({ kind: "saving" });
      try {
        await call(
          savePostmortem({ client: browserApi(), path: { attempt_id: attemptId }, body: { sections } }),
        );
        dirty.current = false;
        setStatus({ kind: "saved", at: new Date() });
      } catch (err) {
        setStatus({ kind: "error", message: err instanceof ProblemError ? err.message : "Couldn't save." });
      }
    }, SAVE_AFTER_MS);
    return () => window.clearTimeout(id);
  }, [sections, readOnly, attemptId]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      const out = await call(
        submitPostmortem({ client: browserApi(), path: { attempt_id: attemptId }, body: { sections } }),
      );
      dirty.current = false;
      setSubmittedAt(out.submitted_at ?? new Date().toISOString());
      setReview(out.review ?? null);
      setStatus({ kind: "saved", at: new Date() });
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof ProblemError ? err.message : "Couldn't submit. Try again.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex max-w-[44rem] flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-serif text-display-lg text-fg">Write-up: {initial.scenario_title}</h1>
        <p className="text-body-lg text-fg-muted">
          Blameless and specific. Describe what changed, not who changed it.
        </p>
      </header>
      {SECTIONS.map((s) => (
        <div key={s.id} className="flex flex-col gap-1.5">
          <label htmlFor={`pm-${s.id}`} className="text-heading-md font-semibold text-fg">
            {s.title}
          </label>
          <p id={`pm-${s.id}-hint`} className="text-label text-fg-muted">
            {s.hint}
          </p>
          <textarea
            id={`pm-${s.id}`}
            name={s.id}
            aria-describedby={`pm-${s.id}-hint`}
            rows={4}
            maxLength={MAX_CHARS}
            readOnly={readOnly}
            value={sections[s.id]}
            onChange={(e) => {
              dirty.current = true;
              setSections((prev) => ({ ...prev, [s.id]: e.target.value }));
            }}
            className="rounded-sm border border-border-input bg-surface px-3 py-2.5 text-body-lg text-fg placeholder:text-fg-subtle read-only:bg-raised"
          />
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        {readOnly ? (
          <>
            <p className="inline-flex items-center gap-1.5 text-body font-medium text-success-text">
              <CircleCheck className="size-4" aria-hidden="true" />
              Submitted.
            </p>
            <Link
              href={`/incident/${attemptId}/debrief`}
              className="text-body font-medium text-brand-text hover:underline"
            >
              Back to your results
            </Link>
          </>
        ) : (
          <button
            type="submit"
            disabled={submitting || !Object.values(sections).some((v) => v.trim())}
            className="h-10 rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
          >
            {submitting ? "Submitting…" : "Submit for review"}
          </button>
        )}
        <span role="status" className="text-label text-fg-subtle">
          {readOnly
            ? status.kind === "error"
              ? status.message
              : ""
            : status.kind === "saving"
              ? "Saving…"
              : status.kind === "saved" && status.at
                ? `Draft saved at ${status.at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : status.kind === "error"
                  ? status.message
                  : ""}
        </span>
      </div>
      {readOnly ? <PostmortemReview attemptId={attemptId} initial={review} /> : null}
    </form>
  );
}
