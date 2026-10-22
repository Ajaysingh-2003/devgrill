"use client";

import { adminReviewCandidate } from "@devgrill/api-client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { browserApi, call, ProblemError } from "@/lib/browser-api";

/** Promote (an author writes it up as a known approach) or dismiss one unrecognised fix. */
export function CandidateActions({ id, describedBy }: { id: string; describedBy: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const decide = async (status: "promoted" | "dismissed") => {
    setBusy(true);
    setError(null);
    try {
      await call(
        adminReviewCandidate({ client: browserApi(), path: { candidate_id: id }, body: { status } }),
      );
      router.refresh();
    } catch (err) {
      setError(err instanceof ProblemError ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="flex items-center gap-2">
      <button
        type="button"
        disabled={busy}
        aria-describedby={describedBy}
        onClick={() => void decide("promoted")}
        className="h-8 rounded-sm border border-border-input px-3 text-label font-medium text-fg hover:bg-raised disabled:opacity-60"
      >
        Promote
      </button>
      <button
        type="button"
        disabled={busy}
        aria-describedby={describedBy}
        onClick={() => void decide("dismissed")}
        className="h-8 rounded-sm px-3 text-label font-medium text-fg-muted hover:bg-raised disabled:opacity-60"
      >
        Dismiss
      </button>
      {error ? (
        <span role="status" className="text-caption text-danger-text">
          {error}
        </span>
      ) : null}
    </span>
  );
}
