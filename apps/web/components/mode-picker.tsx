"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { canPlay, startAttempt, type PlayCheckOut } from "@devgrill/api-client";
import { Clock, Lock, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@devgrill/ui/lib/utils";
import { ProblemError, browserApi, call } from "@/lib/browser-api";

const MODES = [
  {
    id: "guided",
    name: "With hints",
    desc: "Up to three hints when you're stuck. The clock is hidden (you can show it), and your rating moves less.",
  },
  {
    id: "oncall",
    name: "No hints",
    desc: "Like a real on-call shift: the clock runs and teammates get impatient. Counts fully for your rating.",
  },
] as const;

type Refusal = { message: string; link?: { href: string; label: string } };

/** "on Mon, 27 Oct at 05:30 (in 3 days)": when a limit lifts, in the player's own time. */
function unlocksAt(iso: string, now = new Date()): string {
  const at = new Date(iso);
  const when = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(at);
  const hours = (at.getTime() - now.getTime()) / 3_600_000;
  const rel = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const relative =
    hours < 1
      ? rel.format(Math.max(1, Math.round(hours * 60)), "minute")
      : hours < 36
        ? rel.format(Math.round(hours), "hour")
        : rel.format(Math.round(hours / 24), "day");
  return `${when} (${relative})`;
}

/** What to offer instead of starting, for each reason the check can give. */
function blockedBy(check: PlayCheckOut, signIn: string): { icon: typeof Lock; next?: Refusal["link"] } {
  switch (check.reason) {
    case "sign_up_required":
      return { icon: Lock, next: { href: signIn, label: "Sign in with GitHub" } };
    case "upgrade_required":
      return { icon: Sparkles, next: { href: "/drills", label: "See the free drills" } };
    case "active_attempt_exists":
      return {
        icon: Clock,
        next: check.live_attempt_id
          ? { href: `/incident/${check.live_attempt_id}`, label: "Go back to it" }
          : undefined,
      };
    case "not_playable":
      return { icon: Clock };
    default:
      // Out of plays or time, or everyone's busy: something else to do meanwhile.
      return { icon: Clock, next: { href: "/quickfire", label: "Play Quick Fire meanwhile" } };
  }
}

function retryText(seconds: number | null): string {
  if (!seconds) return "";
  if (seconds < 120) return " Try again in a minute.";
  const hours = Math.round(seconds / 3600);
  return hours >= 1
    ? ` It resets in about ${hours} ${hours === 1 ? "hour" : "hours"}.`
    : ` Try again in ${Math.ceil(seconds / 60)} minutes.`;
}

export function ModePicker({ scenarioSlug, solved = false }: { scenarioSlug: string; solved?: boolean }) {
  const router = useRouter();
  const [mode, setMode] = useState<"guided" | "oncall">("guided");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  // Whether this player can start this one now, asked before they click (the same rules as
  // starting). Null while unknown: the button stays usable, and starting checks again anyway.
  const [check, setCheck] = useState<PlayCheckOut | null>(null);
  useEffect(() => {
    let current = true;
    const ask = () =>
      void canPlay({ client: browserApi(), path: { slug: scenarioSlug } }).then(
        ({ data }) => current && data && setCheck(data),
      );
    ask();
    // Back from a run (or another tab): the answer may have changed.
    window.addEventListener("pageshow", ask);
    return () => {
      current = false;
      window.removeEventListener("pageshow", ask);
    };
  }, [scenarioSlug]);
  // "Starting" lasts until we navigate into the drill. Coming back (the router keeps this
  // page alive in the background, and the browser's back/forward cache restores it) must show
  // the button ready again, not still starting.
  useEffect(() => {
    const ready = (e: PageTransitionEvent) => e.persisted && setBusy(false);
    window.addEventListener("pageshow", ready);
    return () => {
      window.removeEventListener("pageshow", ready);
      setBusy(false);
    };
  }, []);
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
        setRefusal({ message: "Couldn't start the drill. Try again." });
        return;
      }
      switch (err.code) {
        case "sign_up_required":
        case "unauthenticated":
          setRefusal({ message: err.message, link: { href: here, label: "Sign in with GitHub" } });
          break;
        case "upgrade_required":
          setRefusal({ message: err.message, link: { href: "/drills", label: "See the free drills" } });
          break;
        case "active_attempt_exists": {
          const live = err.instance?.split("/").at(-1);
          setRefusal({
            message: "You're already in the middle of one. Finish it or leave it first.",
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

  // Can't start it now: just the reason and what to do instead (no mode choice to make).
  if (check && !check.allowed) {
    return (
      <div className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4">
        <h2 id="mode-label" className="text-body font-semibold text-fg">
          {check.reason === "not_playable" ? "Coming soon" : "You can't start this one right now"}
        </h2>
        <Blocked check={check} signIn={here} />
      </div>
    );
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
        {busy ? "Starting your practice system…" : solved ? "Play it again" : "Start the drill"}
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
        Your practice system starts in about 30 seconds and shuts down when you finish, leave, or stop using
        it.
      </p>
    </div>
  );
}

/** Why this player can't start this one now, when that lifts, and what to do instead. */
function Blocked({ check, signIn }: { check: PlayCheckOut; signIn: string }) {
  const { icon: Icon, next } = blockedBy(check, signIn);
  return (
    <div role="status" className="flex flex-col gap-3">
      <p className="flex items-start gap-2 text-body text-fg">
        <Icon className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
        <span>
          {check.message}
          {check.resets_at ? (
            <span className="mt-1 block text-label text-fg-muted">
              You can play again {unlocksAt(check.resets_at)}.
            </span>
          ) : null}
        </span>
      </p>
      {next ? (
        <Link
          href={next.href}
          className={cn(
            "inline-flex h-10 items-center justify-center rounded-sm text-body font-semibold",
            check.reason === "sign_up_required" || check.reason === "active_attempt_exists"
              ? "bg-brand text-on-brand hover:bg-brand-hover"
              : "border border-border-input text-fg hover:bg-raised",
          )}
        >
          {next.label}
        </Link>
      ) : null}
    </div>
  );
}
