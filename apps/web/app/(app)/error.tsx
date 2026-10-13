"use client";

import { TriangleAlert } from "lucide-react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";

/** Errors inside the app shell: the top bar stays, the content explains what to do. */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <EmptyState
      icon={TriangleAlert}
      title="This page didn’t load"
      action={
        <button
          type="button"
          onClick={reset}
          className="inline-flex h-10 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
        >
          Try again
        </button>
      }
    >
      The DevGrill API didn’t answer as expected. Trying again usually works; if it doesn’t, the reference
      below helps us find what happened.
      {error.digest ? (
        <span className="mt-2 block font-mono text-mono-sm text-fg-subtle">Reference {error.digest}</span>
      ) : null}
    </EmptyState>
  );
}
