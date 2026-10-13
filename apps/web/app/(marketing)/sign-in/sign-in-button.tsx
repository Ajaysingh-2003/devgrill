"use client";

import { useState } from "react";
import { signInWithGitHub } from "@/lib/auth-client";

/** Starts the GitHub OAuth redirect. `next` is where to land afterwards (same-site path). */
export function SignInButton({ next }: { next: string }) {
  const [pending, setPending] = useState(false);
  return (
    <button
      type="button"
      disabled={pending}
      aria-busy={pending}
      onClick={async () => {
        setPending(true);
        try {
          const { error } = await signInWithGitHub(next);
          if (error) setPending(false); // the redirect never happened; let them retry
        } catch {
          setPending(false); // network failure: same
        }
      }}
      className="flex h-11 items-center justify-center gap-2.5 rounded-sm bg-fg text-body font-semibold text-fg-inverse hover:opacity-90 disabled:opacity-70"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true" className="size-4 fill-current">
        <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.23 1.87.87 2.33.67.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
      </svg>
      {pending ? "Opening GitHub…" : "Continue with GitHub"}
    </button>
  );
}
