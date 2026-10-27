"use client";

import { useState } from "react";
import { Check, Share2 } from "lucide-react";

/**
 * Share a solved drill: the link opens a spoiler-free card (severity, time, hints; never the
 * cause or the fix, never who played). Uses the system share sheet where there is one.
 */
export function ShareResult({ attemptId, title }: { attemptId: string; title: string }) {
  const [copied, setCopied] = useState(false);

  async function share() {
    const url = `${window.location.origin}/share/${attemptId}`;
    if (navigator.share) {
      try {
        await navigator.share({ title: `I fixed “${title}” on DevGrill`, url });
        return;
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
      }
    }
    await navigator.clipboard.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2500);
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={share}
        className="inline-flex h-9 items-center gap-2 rounded-sm border border-border-strong px-3 text-label font-medium text-fg hover:bg-raised"
      >
        {copied ? (
          <Check className="size-4 text-success-text" aria-hidden="true" />
        ) : (
          <Share2 className="size-4" aria-hidden="true" />
        )}
        Share your result
      </button>
      <span aria-live="polite" className="text-label text-fg-muted">
        {copied ? "Link copied. It shows your time and hints, never the fix." : ""}
      </span>
    </div>
  );
}
