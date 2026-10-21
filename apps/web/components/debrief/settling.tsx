"use client";

import { LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const EVERY_MS = 2000;
const TRIES = 30;

/**
 * The worker scores an attempt a few seconds after the sandbox is gone. Until then the
 * debrief shows what it has and refreshes itself, quietly, for up to a minute.
 */
export function Settling() {
  const router = useRouter();
  const [tries, setTries] = useState(0);
  useEffect(() => {
    if (tries >= TRIES) return;
    const id = window.setTimeout(() => {
      router.refresh();
      setTries((n) => n + 1);
    }, EVERY_MS);
    return () => window.clearTimeout(id);
  }, [router, tries]);
  return (
    <p role="status" className="flex items-center gap-2 text-body text-fg-muted">
      {tries < TRIES ? (
        <>
          <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          Scoring your incident…
        </>
      ) : (
        "Your score is taking longer than usual. Reload the page in a minute."
      )}
    </p>
  );
}
