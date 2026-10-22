"use client";

import { getPostmortem, reviewPostmortem, type PostmortemReviewOut } from "@devgrill/api-client";
import { CircleAlert, CircleCheck, LoaderCircle, Quote, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { browserApi, call, ProblemError } from "@/lib/browser-api";

const POLL_MS = 5000;

/**
 * The AI review of a submitted postmortem (ADR 016): each rubric criterion with the quotes
 * that back its score, the blamelessness check and the feedback. Polls while it's pending.
 */
export function PostmortemReview({
  attemptId,
  initial,
}: {
  attemptId: string;
  initial: PostmortemReviewOut | null;
}) {
  const [review, setReview] = useState(initial);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = review?.status === "pending";

  useEffect(() => {
    if (!pending) return;
    const id = window.setInterval(async () => {
      try {
        const doc = await call(getPostmortem({ client: browserApi(), path: { attempt_id: attemptId } }));
        if (doc.review && doc.review.status !== "pending") setReview(doc.review);
      } catch {
        // Keep polling: the next try may work.
      }
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [pending, attemptId]);

  if (!review) return null;

  const askAgain = async () => {
    setAsking(true);
    setError(null);
    try {
      setReview(await call(reviewPostmortem({ client: browserApi(), path: { attempt_id: attemptId } })));
    } catch (err) {
      setError(err instanceof ProblemError ? err.message : "Couldn't ask again. Try in a minute.");
    } finally {
      setAsking(false);
    }
  };

  return (
    <section aria-labelledby="pm-review" className="flex flex-col gap-4 border-t border-border pt-8">
      <h2 id="pm-review" className="text-heading-lg font-semibold tracking-tight text-fg">
        Review
      </h2>
      {review.status === "pending" ? (
        <p role="status" className="inline-flex items-center gap-2 text-body text-fg-muted">
          <LoaderCircle className="size-4" aria-hidden="true" />
          Reviewing against the scenario’s rubric. This usually takes under a minute.
        </p>
      ) : null}
      {review.status === "failed" || review.status === "unavailable" ? (
        <div className="flex flex-col items-start gap-3">
          <p role="status" className="inline-flex items-start gap-2 text-body text-fg-muted">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {review.detail ?? "Not reviewed."}
          </p>
          {review.status === "failed" ? (
            <button
              type="button"
              onClick={() => void askAgain()}
              disabled={asking}
              className="h-10 rounded-sm border border-border-input px-4 text-body font-medium text-fg hover:bg-raised disabled:opacity-60"
            >
              {asking ? "Asking…" : "Ask for the review again"}
            </button>
          ) : null}
          {error ? <p className="text-body text-danger-text">{error}</p> : null}
        </div>
      ) : null}
      {review.status === "graded" ? <Graded review={review} /> : null}
    </section>
  );
}

function Graded({ review }: { review: PostmortemReviewOut }) {
  return (
    <div className="flex flex-col gap-6">
      {/* A status, so a review that lands while you wait is announced. */}
      <p role="status" className="text-body-lg text-fg">
        <span className="font-mono font-semibold tabular-nums">
          {review.total} of {review.max}
        </span>{" "}
        on the rubric.
      </p>
      {review.blameless === false ? (
        <div className="flex flex-col gap-2 rounded-md border border-warning-text/30 bg-warning-subtle p-4">
          <p className="inline-flex items-center gap-2 text-body font-semibold text-warning-text">
            <TriangleAlert className="size-4" aria-hidden="true" />
            Not blameless: 20% off
          </p>
          <p className="text-body text-fg">
            These sentences point at people. Describe what the system allowed instead.
          </p>
          <ul className="flex flex-col gap-1">
            {review.blame?.map((q) => (
              <li key={q} className="text-body text-fg-muted">
                “{q}”
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="inline-flex items-center gap-2 text-body text-success-text">
          <CircleCheck className="size-4" aria-hidden="true" />
          Blameless
        </p>
      )}
      <ol className="flex flex-col gap-4">
        {review.criteria?.map((c) => (
          <li key={c.key} className="flex flex-col gap-2 rounded-md border border-border bg-surface p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-body font-semibold text-fg">{c.description}</h3>
              <span className="font-mono text-mono font-semibold text-fg tabular-nums">
                {c.score} / {c.max}
              </span>
            </div>
            <p className="text-body text-fg-muted">{c.reason}</p>
            {c.evidence.length ? (
              <ul className="flex flex-col gap-1.5">
                {c.evidence.map((q) => (
                  <li key={q} className="flex items-start gap-2 text-label text-fg-muted">
                    <Quote className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                    <span>
                      <span className="sr-only">From your postmortem: </span>
                      {q}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
            {c.unsupported ? (
              <p className="inline-flex items-start gap-2 text-label text-warning-text">
                <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                No sentence in your postmortem backed this up, so the credit was halved.
              </p>
            ) : null}
          </li>
        ))}
      </ol>
      {review.feedback ? (
        <div className="flex flex-col gap-1.5">
          <h3 className="text-body font-semibold text-fg">Feedback</h3>
          <p className="max-w-2xl text-body text-fg">{review.feedback}</p>
        </div>
      ) : null}
    </div>
  );
}
