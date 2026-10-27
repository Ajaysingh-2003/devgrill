"use client";

import { startAttempt } from "@devgrill/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ProblemError, browserApi, call } from "@/lib/browser-api";

/** Must be on the API's guest list (SANDBOX_GUEST_SCENARIOS). */
export const TUTORIAL_SCENARIO = "ttl-zero";

type Problem = { message: string; link?: { href: string; label: string } };

/** Starts the tutorial incident, as a guest when nobody is signed in. */
export function TryStart() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function start() {
    setBusy(true);
    setProblem(null);
    const attempt = () =>
      call(
        startAttempt({ client: browserApi(), body: { scenario_slug: TUTORIAL_SCENARIO, mode: "tutorial" } }),
      );
    try {
      let started;
      try {
        started = await attempt();
      } catch (err) {
        if (!(err instanceof ProblemError) || err.status !== 401) throw err;
        const guest = await fetch("/api/guest", { method: "POST" });
        if (!guest.ok) throw err;
        started = await attempt();
      }
      router.push(`/incident/${started.id}`);
    } catch (err) {
      setBusy(false);
      if (!(err instanceof ProblemError)) {
        setProblem({ message: "Couldn't start the incident. Try again." });
      } else if (err.code === "active_attempt_exists") {
        const live = err.instance?.split("/").at(-1);
        setProblem({
          message: "You're already in the middle of one.",
          link: live ? { href: `/incident/${live}`, label: "Go back to it" } : undefined,
        });
      } else {
        setProblem({ message: err.message });
      }
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="inline-flex h-11 w-fit items-center rounded-sm bg-brand px-5 text-body font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
      >
        {busy ? "Starting…" : "Start the incident"}
      </button>
      <p role="status" className="text-body text-fg-muted">
        {problem ? (
          <>
            {problem.message}{" "}
            {problem.link ? (
              <Link href={problem.link.href} className="font-medium text-brand-text hover:underline">
                {problem.link.label}
              </Link>
            ) : null}
          </>
        ) : null}
      </p>
    </div>
  );
}
