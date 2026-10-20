"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { startAttempt } from "@devgrill/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { cn } from "@devgrill/ui/lib/utils";
import { ProblemError, browserApi, call } from "@/lib/browser-api";

const MODES = [
  {
    id: "guided",
    name: "Guided",
    desc: "Three tiered hints. The clock is hidden (you can show it) and your rating changes less.",
  },
  {
    id: "oncall",
    name: "Real on-call",
    desc: "No hints, the clock counts and teammates get impatient. Fully rated.",
  },
] as const;

type Refusal = { message: string; link?: { href: string; label: string } };

function retryText(seconds: number | null): string {
  if (!seconds) return "";
  if (seconds < 120) return " Try again in a minute.";
  const hours = Math.round(seconds / 3600);
  return hours >= 1
    ? ` It resets in about ${hours} ${hours === 1 ? "hour" : "hours"}.`
    : ` Try again in ${Math.ceil(seconds / 60)} minutes.`;
}

export function ModePicker({ scenarioSlug }: { scenarioSlug: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<"guided" | "oncall">("guided");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const here = `/sign-in?next=${encodeURIComponent(typeof window === "undefined" ? "/drills" : window.location.pathname)}`;

  async function start() {
    setBusy(true);
    setRefusal(null);
    const attempt = () =>
      call(startAttempt({ client: browserApi(), body: { scenario_slug: scenarioSlug, mode } }));
    try {
      let started;
      try {
        started = await attempt();
      } catch (err) {
        // Not signed in: incidents open to guests start with a guest session.
        if (!(err instanceof ProblemError) || err.status !== 401) throw err;
        const guest = await fetch("/api/guest", { method: "POST" });
        if (!guest.ok) throw err;
        started = await attempt();
      }
      router.push(`/incident/${started.id}`);
    } catch (err) {
      setBusy(false);
      if (!(err instanceof ProblemError)) {
        setRefusal({ message: "Couldn't start the incident. Try again." });
        return;
      }
      switch (err.code) {
        case "sign_up_required":
        case "unauthenticated":
          setRefusal({ message: err.message, link: { href: here, label: "Sign in with GitHub" } });
          break;
        case "upgrade_required":
          setRefusal({ message: err.message, link: { href: "/drills", label: "See the free incidents" } });
          break;
        case "active_attempt_exists": {
          const live = err.instance?.split("/").at(-1);
          setRefusal({
            message: "You already have an incident running. Finish or leave it first.",
            link: live ? { href: `/incident/${live}`, label: "Go back to it" } : undefined,
          });
          break;
        }
        case "quota_exceeded":
        case "capacity":
        case "budget_paused":
          setRefusal({ message: `${err.message}${retryText(err.retryAfter)}` });
          break;
        default:
          setRefusal({ message: err.message });
      }
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4">
      <h2 id="mode-label" className="text-body font-semibold text-fg">
        How do you want to play?
      </h2>
      <RadioGroup
        aria-labelledby="mode-label"
        value={mode}
        onValueChange={(v) => setMode(v as "guided" | "oncall")}
        className="flex flex-col gap-2"
      >
        {MODES.map((m) => (
          <Radio.Root
            key={m.id}
            value={m.id}
            className={cn(
              "flex flex-col gap-1 rounded-sm border px-3 py-2.5 text-left outline-none",
              "border-border hover:bg-raised data-[checked]:border-brand data-[checked]:bg-brand-subtle",
              "focus-visible:ring-2 focus-visible:ring-focus-ring",
            )}
          >
            <span className="text-body font-semibold text-fg">{m.name}</span>
            <span className="text-label text-fg-muted">{m.desc}</span>
          </Radio.Root>
        ))}
      </RadioGroup>
      <button
        type="button"
        onClick={() => void start()}
        disabled={busy}
        className="inline-flex h-10 items-center justify-center rounded-sm bg-brand text-body font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-70"
      >
        {busy ? "Starting your sandbox…" : "Start the incident"}
      </button>
      <div aria-live="polite">
        {refusal ? (
          <p className="text-body text-fg">
            {refusal.message}{" "}
            {refusal.link ? (
              <Link
                href={refusal.link.href}
                className="font-medium text-brand-text underline underline-offset-2"
              >
                {refusal.link.label}
              </Link>
            ) : null}
          </p>
        ) : null}
      </div>
      <p className="text-caption text-fg-subtle">
        Your sandbox starts in about 30 seconds and is torn down when you finish, leave, or stop using it.
      </p>
    </div>
  );
}
