"use client";

import { TriangleAlert } from "lucide-react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";

/** T11: unexpected error boundary. Says what happened and how to recover, without apologising. */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main id="main" className="grid min-h-dvh place-items-center px-4">
      <EmptyState
        icon={TriangleAlert}
        title="This page failed to load"
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
        Something on our side broke while loading it. Trying again usually works.
        {error.digest ? (
          <span className="mt-2 block font-mono text-mono-sm text-fg-subtle">Reference {error.digest}</span>
        ) : null}
      </EmptyState>
    </main>
  );
}
