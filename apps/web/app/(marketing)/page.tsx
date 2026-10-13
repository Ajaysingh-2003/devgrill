import Link from "next/link";
import { ProbeTable } from "@devgrill/ui/components/devgrill/probe-table";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { StatusPill } from "@devgrill/ui/components/devgrill/status-pill";
import { ServiceIcon } from "@devgrill/ui/icons";
import { Sparkline } from "@/components/sparkline";
import { CHARTS, PROBES, TRACKS } from "@/lib/mock";

const LOOP = [
  { name: "Get paged", text: "A pager alert, a worried product manager and a clock." },
  { name: "Investigate", text: "A real stack: logs, metrics, a terminal, the database and the cache." },
  { name: "Mitigate", text: "Stop the bleeding first. Roll back, flip a flag, shed load." },
  { name: "Fix the cause", text: "Change the actual code and deploy it to your sandbox." },
  { name: "Survive verify", text: "We replay the traffic and attack the weak spots of your fix." },
  { name: "Write it up", text: "A blameless postmortem, reviewed against a rubric." },
];

export default function LandingPage() {
  return (
    <>
      <section className="mx-auto grid max-w-[75rem] gap-12 px-4 pt-16 pb-20 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:pt-24">
        <div className="flex flex-col gap-6">
          <h1 className="font-display text-[clamp(2.5rem,6vw,4.25rem)] leading-[1.02] font-extrabold tracking-[-0.035em] text-fg">
            Your first Sev1 shouldn’t be your first Sev1.
          </h1>
          <p className="max-w-xl text-body-lg text-fg-muted">
            DevGrill drops you into live, broken systems. Find out why production is on fire, stop it, fix the
            real cause and prove it with a traffic replay, before it happens at 2 a.m. for real.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/drills"
              className="inline-flex h-11 items-center rounded-sm bg-brand px-5 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              Take a 5-minute incident
            </Link>
            <Link
              href="/drills"
              className="inline-flex h-11 items-center rounded-sm px-4 text-body font-medium text-fg hover:bg-raised"
            >
              Browse the drills
            </Link>
          </div>
        </div>

        {/* The memorable thing: a frozen frame of a real incident. */}
        <figure
          aria-label="An incident in progress"
          className="overflow-hidden rounded-lg border border-border bg-surface shadow-float"
        >
          <div className="flex items-center gap-3 border-b border-border bg-danger-subtle px-4 py-3">
            <SevBadge sev={1} />
            <p className="flex-1 truncate text-label font-semibold text-danger-text">
              product-api p99 latency is 4.2 s and 18% of requests fail
            </p>
            <time className="font-mono text-mono-sm text-danger-text">20:03</time>
          </div>
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <span className="text-label text-fg-muted">p99 latency</span>
              <span className="font-mono text-stat font-semibold text-fg">4.2 s</span>
              <Sparkline
                values={CHARTS.latency}
                threshold={500}
                marker={14}
                label="p99 latency jumps from 118 ms to 4.2 s after the 19:58 deploy"
                className="h-20 w-full"
                color="var(--chart-7)"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-label text-fg-muted">Cache hit rate</span>
              <span className="font-mono text-stat font-semibold text-fg">3%</span>
              <Sparkline
                values={CHARTS.cacheHit}
                marker={14}
                label="Cache hit rate falls from 95% to 3% at the same moment"
                className="h-20 w-full"
              />
            </div>
          </div>
          <div className="flex flex-col gap-2 border-t border-border px-4 py-3">
            <p className="text-body text-fg">
              <span className="font-semibold">Arjun, SRE:</span>{" "}
              <span className="text-fg-muted">
                I restarted Postgres and it came straight back. What changed at 19:58?
              </span>
            </p>
            <div className="flex items-center gap-2">
              <StatusPill status="investigating" />
              <span className="text-label text-fg-subtle">
                Hint: compare the keys the app asks for with the keys in Redis.
              </span>
            </div>
          </div>
        </figure>
      </section>

      <section aria-labelledby="loop-title" className="border-y border-border bg-surface">
        <div className="mx-auto max-w-[75rem] px-4 py-16 sm:px-6">
          <h2 id="loop-title" className="max-w-2xl text-heading-lg font-semibold tracking-tight text-fg">
            Every drill is the whole on-call loop, not a puzzle
          </h2>
          <ol className="mt-8 grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {LOOP.map((step, i) => (
              <li key={step.name} className="flex flex-col gap-2 bg-surface p-5">
                <span className="font-mono text-mono-sm text-brand-text">Step {i + 1}</span>
                <span className="text-body-lg font-semibold text-fg">{step.name}</span>
                <span className="text-body text-fg-muted">{step.text}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section
        aria-labelledby="verify-title"
        className="mx-auto grid max-w-[75rem] gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[22rem_1fr]"
      >
        <div className="flex flex-col gap-3">
          <h2 id="verify-title" className="text-heading-lg font-semibold tracking-tight text-fg">
            Graded on what the system does
          </h2>
          <p className="text-body-lg text-fg-muted">
            There is no answer key to match. Any fix that keeps the service inside its targets while we replay
            the sale and pull the rug out passes. Then you see how 10,000 other engineers fixed the same
            outage.
          </p>
        </div>
        <ProbeTable probes={PROBES.slice(0, 4)} caption="Verify probes for The Big Sale Meltdown" />
      </section>

      <section aria-labelledby="tracks-title" className="mx-auto max-w-[75rem] px-4 pb-20 sm:px-6">
        <h2 id="tracks-title" className="text-heading-md font-semibold text-fg">
          Six systems to break, more on the way
        </h2>
        <ul className="mt-4 flex flex-wrap gap-2">
          {TRACKS.map((t) => (
            <li
              key={t.slug}
              className="flex items-center gap-2 rounded-sm border border-border bg-surface px-3 py-2 text-body text-fg"
            >
              <ServiceIcon kind={t.service} className="text-fg-muted" />
              {t.name}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
