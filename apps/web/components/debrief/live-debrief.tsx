import type { DebriefOut, ReplayEntryOut } from "@devgrill/api-client";
import { Hourglass, Lightbulb, Lock, Search } from "lucide-react";
import Link from "next/link";
import { ProbeTable } from "@devgrill/ui/components/devgrill/probe-table";
import { VerifyCelebration } from "@devgrill/ui/components/devgrill/verify-celebration";
import { cn } from "@devgrill/ui/lib/utils";
import { ApproachExplorer } from "@/components/approach-explorer";
import { IncidentPageHeader } from "@/components/incident-page-header";
import { Settling } from "./settling";
import { clock, minutes, toProbeRow } from "./format";

const ENDINGS: Record<string, string> = {
  resolved: "Your fix survived the replay",
  expired: "Time ran out",
  abandoned: "You left this incident",
  failed: "The sandbox stopped working",
};

const MARKS = {
  clue: { label: "Key clue", icon: Search, tone: "bg-info-subtle text-info-text" },
  lost: { label: "Lost time", icon: Hourglass, tone: "bg-warning-subtle text-warning-text" },
  hint: { label: "Hint", icon: Lightbulb, tone: "bg-raised text-fg-muted" },
} as const;

const POSTMORTEM_LINK = {
  none: "Write the postmortem",
  draft: "Finish your postmortem",
  submitted: "Read your postmortem",
} as const;

/** T6 Debrief, live: what verify threw at the fix, the score, the investigation, what's next. */
export function LiveDebrief({ d }: { d: DebriefOut }) {
  const resolved = d.attempt.state === "resolved";
  const probes = d.verify?.probes ?? [];
  const passed = probes.filter((p) => p.passed).length;
  const score = d.score;
  const celebrate = resolved && d.rating && d.mastery && d.rating.delta > 0;
  const briefing = `/drills/${d.track_slug}/${d.attempt.scenario_slug}`;

  return (
    <>
      <IncidentPageHeader
        context={`${d.scenario_title}, debrief`}
        back={{ href: briefing, label: "Back to the briefing" }}
      />
      <main id="main" className="mx-auto flex max-w-[72rem] flex-col gap-12 px-4 py-10 sm:px-6">
        {celebrate && d.rating && d.mastery ? (
          <VerifyCelebration
            title={ENDINGS.resolved!}
            delta={Math.round(d.rating.delta)}
            rating={Math.round(d.rating.after)}
            track={d.track_title}
            masteryBefore={d.mastery.before}
            masteryAfter={d.mastery.after}
          />
        ) : (
          <header className="flex max-w-3xl flex-col gap-3">
            <h1 className="font-serif text-display-xl text-fg">
              {ENDINGS[d.attempt.state] ?? ENDINGS.failed}
            </h1>
            <p className="text-body-lg text-fg-muted">
              {d.verify
                ? `Your best verify run passed ${passed} of ${probes.length} checks.`
                : resolved
                  ? "Every check passed."
                  : "You didn't run verify, so nothing was checked."}{" "}
              {d.rating
                ? `${d.track_title} rating ${Math.round(d.rating.before)} → ${Math.round(d.rating.after)}.`
                : d.settled && !d.rating && d.attempt.state !== "failed"
                  ? "This attempt doesn't change your rating."
                  : ""}
            </p>
          </header>
        )}
        {!d.settled ? <Settling /> : null}

        <dl className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4">
          {(
            [
              [
                "Mitigated in",
                score?.mitigation_minutes != null ? minutes(score.mitigation_minutes) : "Not mitigated",
                score ? `par is ${score.par_minutes} minutes` : "",
              ],
              [
                "Checks passed",
                d.verify ? `${passed} of ${probes.length}` : "None run",
                d.verify?.status ?? "",
              ],
              [
                "Hints used",
                String(score?.hints_used ?? 0),
                score?.hints_penalty ? `−${Math.round(score.hints_penalty * 100)} points` : "full credit",
              ],
              [
                "Incident score",
                score ? `${Math.round(score.incident * 100)} / 100` : "…",
                score?.total == null ? "postmortem not reviewed yet" : "",
              ],
            ] as const
          ).map(([k, v, note]) => (
            <div key={k} className="flex flex-col gap-0.5 bg-surface px-4 py-3">
              <dt className="text-label text-fg-muted">{k}</dt>
              <dd className="font-mono text-stat font-semibold text-fg tabular-nums">{v}</dd>
              <dd className="text-caption text-fg-subtle">{note}</dd>
            </div>
          ))}
        </dl>

        {probes.length ? (
          <section aria-labelledby="probes-title" className="flex flex-col gap-3">
            <h2 id="probes-title" className="text-heading-lg font-semibold tracking-tight text-fg">
              What verify threw at your fix
            </h2>
            <p className="max-w-2xl text-body-lg text-fg-muted">
              Each probe checks a behaviour, measured from outside your code. Any fix that holds all of them
              passes.
            </p>
            <ProbeTable probes={probes.map(toProbeRow)} caption="Verify probes and results" />
          </section>
        ) : null}

        {score ? (
          <section aria-labelledby="score-title" className="flex flex-col gap-3">
            <h2 id="score-title" className="text-heading-md font-semibold text-fg">
              How the score adds up
            </h2>
            <table className="w-full max-w-2xl border-collapse text-body">
              <caption className="sr-only">Score components, their weights and your credit</caption>
              <thead>
                <tr className="border-b border-border text-left text-label text-fg-muted">
                  <th scope="col" className="py-2 font-medium">
                    Part
                  </th>
                  <th scope="col" className="py-2 text-right font-medium">
                    Weight
                  </th>
                  <th scope="col" className="py-2 text-right font-medium">
                    Your credit
                  </th>
                </tr>
              </thead>
              <tbody className="font-mono text-mono tabular-nums">
                {(
                  [
                    ["Time to mitigate", score.weights.mitigation_time, score.mitigation_time],
                    ["Verify checks passed", score.weights.resolution, score.resolution],
                    ["Status updates posted", score.weights.communication, score.communication],
                    ["Postmortem", score.weights.postmortem, score.postmortem],
                  ] as const
                ).map(([part, weight, credit]) => (
                  <tr key={part} className="border-b border-border">
                    <th scope="row" className="py-2 text-left font-sans font-normal text-fg">
                      {part}
                    </th>
                    <td className="py-2 text-right text-fg-muted">{Math.round((weight ?? 0) * 100)}%</td>
                    <td className="py-2 text-right text-fg">
                      {credit == null ? "pending" : `${Math.round(credit * 100)}%`}
                    </td>
                  </tr>
                ))}
                {score.hints_penalty ? (
                  <tr className="border-b border-border">
                    <th scope="row" className="py-2 text-left font-sans font-normal text-fg">
                      Hints
                    </th>
                    <td className="py-2 text-right text-fg-muted" />
                    <td className="py-2 text-right text-fg">−{Math.round(score.hints_penalty * 100)}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
            {score.mitigation_minutes != null && score.mitigation_time === 0 ? (
              <p className="max-w-2xl text-body text-fg-muted">
                Mitigation counts once verify has measured the same recovery from outside: none of your runs
                held the SLO under the replay.
              </p>
            ) : null}
          </section>
        ) : null}

        <section aria-labelledby="approaches-title" className="flex flex-col gap-3">
          <h2 id="approaches-title" className="text-heading-lg font-semibold tracking-tight text-fg">
            Your fix next to the others
          </h2>
          {d.approaches ? (
            <ApproachExplorer
              label="Known approaches"
              approaches={d.approaches.map((a) => ({
                id: a.key,
                name: a.name,
                share: a.share,
                outcome: a.outcome,
                yours: a.yours,
                idea: a.idea_md,
                code: a.patch,
                pros: a.pros,
                cons: a.cons,
              }))}
            />
          ) : (
            <p className="flex max-w-2xl items-start gap-2 rounded-md border border-border bg-surface p-4 text-body text-fg-muted">
              <Lock className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              The known approaches are spoilers. Resolve this incident and they open here, with yours marked.
            </p>
          )}
        </section>

        <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
          <section aria-labelledby="replay-title" className="flex flex-col gap-3">
            <h2 id="replay-title" className="text-heading-md font-semibold text-fg">
              How your investigation went
            </h2>
            {d.replay.length ? (
              <ol className="flex flex-col rounded-md border border-border bg-surface">
                {d.replay.map((e, i) => (
                  <ReplayRow key={i} e={e} />
                ))}
              </ol>
            ) : (
              <p className="text-body text-fg-muted">Nothing was recorded for this attempt.</p>
            )}
          </section>

          <aside aria-labelledby="next-title" className="flex flex-col gap-4">
            <Link
              href={`/incident/${d.attempt.id}/postmortem`}
              className="inline-flex h-10 items-center justify-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              {POSTMORTEM_LINK[d.postmortem]}
            </Link>
            <h2 id="next-title" className="text-body font-semibold text-fg">
              Next in {d.track_title}
            </h2>
            {d.next.length ? (
              <ul className="flex flex-col gap-2">
                {d.next.map((s) => (
                  <li key={s.slug}>
                    <Link
                      href={`/drills/${s.track_slug}/${s.slug}`}
                      className="flex flex-col rounded-sm border border-border px-3 py-2 hover:bg-raised"
                    >
                      <span className="text-body text-fg">{s.title}</span>
                      <span className="text-caption text-fg-subtle">
                        {s.difficulty.toUpperCase()}, about {s.est_minutes} minutes
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-body text-fg-muted">You’ve solved everything here. Try another track.</p>
            )}
            {!resolved ? (
              <Link href={briefing} className="text-body font-medium text-brand-text hover:underline">
                Try this incident again
              </Link>
            ) : null}
          </aside>
        </div>
      </main>
    </>
  );
}

function ReplayRow({ e }: { e: ReplayEntryOut }) {
  const mark = e.mark ? MARKS[e.mark] : null;
  return (
    <li className="grid grid-cols-[3.5rem_1fr] items-start gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
      <time className="pt-0.5 font-mono text-mono-sm text-fg-subtle">{clock(e.at_s)}</time>
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-body wrap-anywhere text-fg">{e.text}</span>
        {mark ? (
          <span className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-caption font-medium",
                mark.tone,
              )}
            >
              <mark.icon className="size-3" aria-hidden="true" />
              {mark.label}
            </span>
            {e.note ? <span className="text-caption text-fg-muted">{e.note}</span> : null}
          </span>
        ) : null}
      </div>
    </li>
  );
}
