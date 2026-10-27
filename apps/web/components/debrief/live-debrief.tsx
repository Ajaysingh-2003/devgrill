import type { DebriefOut, ReplayEntryOut } from "@devgrill/api-client";
import { Hourglass, Lightbulb, Lock, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { ProbeTable } from "@devgrill/ui/components/devgrill/probe-table";
import { VerifyCelebration } from "@devgrill/ui/components/devgrill/verify-celebration";
import { cn } from "@devgrill/ui/lib/utils";
import { ApproachExplorer } from "@/components/approach-explorer";
import { IncidentPageHeader } from "@/components/incident-page-header";
import { Settling } from "./settling";
import { ShareResult } from "./share-result";
import { clock, minutes, toProbeRow } from "./format";

const ENDINGS: Record<string, string> = {
  resolved: "Your fix held up",
  expired: "Time ran out",
  abandoned: "You left this drill",
  failed: "Your practice system stopped working",
};

const MARKS = {
  clue: { label: "Key clue", icon: Search, tone: "bg-info-subtle text-info-text" },
  lost: { label: "Lost time", icon: Hourglass, tone: "bg-warning-subtle text-warning-text" },
  hint: { label: "Hint", icon: Lightbulb, tone: "bg-raised text-fg-muted" },
} as const;

const CITE = /\[e(\d+)\]/g;

/** The coach's note, with its [e<id>] citations as links to the replay lines they name. */
function CoachNote({ text, replay }: { text: string; replay: ReplayEntryOut[] }) {
  const at = new Map(replay.filter((e) => e.event_id != null).map((e) => [e.event_id!, e.at_s]));
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CITE)) {
    const id = Number(m[1]);
    parts.push(text.slice(last, m.index));
    const seconds = at.get(id);
    parts.push(
      seconds == null ? null : (
        <a
          key={m.index}
          href={`#replay-e${id}`}
          className="font-mono text-mono-sm text-brand-text hover:underline"
          aria-label={`See the moment at ${clock(seconds)}`}
        >
          [{clock(seconds)}]
        </a>
      ),
    );
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return <p className="max-w-3xl text-body-lg text-fg">{parts}</p>;
}

const POSTMORTEM_LINK = {
  none: "Write it up",
  draft: "Finish your write-up",
  submitted: "Read your write-up",
} as const;

/** T6 Debrief, live: what verify threw at the fix, the score, the investigation, what's next. */
export function LiveDebrief({
  d,
  celebrate: allowed = true,
  guest = false,
}: {
  d: DebriefOut;
  celebrate?: boolean;
  /** Played without an account: offer to keep the result (it moves over on sign-in). */
  guest?: boolean;
}) {
  const resolved = d.attempt.state === "resolved";
  const probes = d.verify?.probes ?? [];
  const passed = probes.filter((p) => p.passed).length;
  const score = d.score;
  const celebrate = allowed && resolved && d.rating && d.mastery && d.rating.delta > 0;
  const briefing = `/drills/${d.track_slug}/${d.attempt.scenario_slug}`;

  return (
    <>
      <IncidentPageHeader
        context={`${d.scenario_title}, results`}
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
                ? `In your best check, ${passed} of ${probes.length} checks passed.`
                : resolved
                  ? "Every check passed."
                  : "You didn't check your fix, so nothing was measured."}{" "}
              {d.rating
                ? `${d.track_title} rating ${Math.round(d.rating.before)} → ${Math.round(d.rating.after)}.`
                : d.settled && !d.rating && d.attempt.state !== "failed"
                  ? "This run doesn't change your rating."
                  : ""}
            </p>
          </header>
        )}
        {guest ? <KeepResult attemptId={d.attempt.id} resolved={resolved} /> : null}
        {resolved ? <ShareResult attemptId={d.attempt.id} title={d.scenario_title} /> : null}
        {!d.settled ? <Settling /> : null}

        <dl className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4">
          {(
            [
              [
                "Working again in",
                score?.mitigation_minutes != null ? minutes(score.mitigation_minutes) : "Not yet",
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
                "Score",
                score ? `${Math.round(score.incident * 100)} / 100` : "…",
                score?.total == null ? "write-up not reviewed yet" : "",
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
              What the check threw at your fix
            </h2>
            <p className="max-w-2xl text-body-lg text-fg-muted">
              Each check tests one behaviour, measured from outside your code. Any fix that holds up in all of
              them passes.
            </p>
            <ProbeTable probes={probes.map(toProbeRow)} caption="The checks your fix faced, and how it did" />
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
                    ["Time to get it working", score.weights.mitigation_time, score.mitigation_time],
                    ["Checks passed", score.weights.resolution, score.resolution],
                    ["Status updates posted", score.weights.communication, score.communication],
                    ["Write-up", score.weights.postmortem, score.postmortem],
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
                Getting it working counts once the check sees the same recovery from outside: none of your
                checks kept the service on target under real traffic.
              </p>
            ) : null}
          </section>
        ) : null}

        {d.coach ? (
          <section aria-labelledby="coach-title" className="flex flex-col gap-3">
            <h2
              id="coach-title"
              className="inline-flex items-center gap-2 text-heading-md font-semibold text-fg"
            >
              <Sparkles className="size-4 text-fg-muted" aria-hidden="true" />
              Coach’s note
            </h2>
            <CoachNote text={d.coach.text} replay={d.replay} />
          </section>
        ) : null}

        <section aria-labelledby="approaches-title" className="flex flex-col gap-3">
          <h2 id="approaches-title" className="text-heading-lg font-semibold tracking-tight text-fg">
            Your fix next to the others
          </h2>
          {d.approaches ? (
            <ApproachExplorer
              label="Ways to fix it"
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
              Other ways to fix it would spoil the drill. Solve it and they open here, with yours marked.
            </p>
          )}
          {d.approach_note?.source === "ai" && d.approach_note.rationale ? (
            <p className="max-w-3xl text-body text-fg-muted">
              {d.approach_key ? "How we read your fix: " : "Your fix is new to us. How we read it: "}
              {d.approach_note.rationale}
            </p>
          ) : null}
        </section>

        <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
          <section aria-labelledby="replay-title" className="flex flex-col gap-3">
            <h2 id="replay-title" className="text-heading-md font-semibold text-fg">
              How it went
            </h2>
            {d.replay.length ? (
              <ol className="flex flex-col rounded-md border border-border bg-surface">
                {d.replay.map((e, i) => (
                  <ReplayRow key={e.event_id ?? `i${i}`} e={e} />
                ))}
              </ol>
            ) : (
              <p className="text-body text-fg-muted">Nothing was recorded for this run.</p>
            )}
          </section>

          <aside aria-labelledby="next-title" className="flex flex-col gap-4">
            <Link
              href={`/incident/${d.attempt.id}/postmortem`}
              className="inline-flex h-10 items-center justify-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              {POSTMORTEM_LINK[d.postmortem]}
            </Link>
            {d.review?.status === "graded" ? (
              <p className="text-label text-fg-muted">
                Write-up review: {d.review.total} of {d.review.max}
                {d.review.blameless === false ? ", not blameless" : ""}
              </p>
            ) : d.review?.status === "pending" ? (
              <p className="text-label text-fg-muted">Your write-up is being reviewed.</p>
            ) : null}
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
                Try this drill again
              </Link>
            ) : null}
          </aside>
        </div>
      </main>
    </>
  );
}

/** For guests: sign in and this run (and any other guest runs) move to the new account. */
function KeepResult({ attemptId, resolved }: { attemptId: string; resolved: boolean }) {
  const next = encodeURIComponent(`/incident/${attemptId}/debrief`);
  return (
    <section
      aria-labelledby="keep-title"
      className="flex max-w-3xl flex-col gap-3 rounded-md border border-border bg-surface p-5 sm:flex-row sm:items-center"
    >
      <div className="flex flex-1 flex-col gap-1">
        <h2 id="keep-title" className="text-body-lg font-semibold text-fg">
          {resolved ? "Keep this win" : "Keep your progress"}
        </h2>
        <p className="text-body text-fg-muted">
          Sign in and this run is saved to your account, along with any others you played here. Then pick your
          next drill.
        </p>
      </div>
      <Link
        href={`/sign-in?next=${next}`}
        className="inline-flex h-10 shrink-0 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
      >
        Sign in with GitHub
      </Link>
    </section>
  );
}

function ReplayRow({ e }: { e: ReplayEntryOut }) {
  const mark = e.mark ? MARKS[e.mark] : null;
  return (
    <li
      id={e.event_id != null ? `replay-e${e.event_id}` : undefined}
      className="grid scroll-mt-6 grid-cols-[3.5rem_1fr] items-start gap-3 border-b border-border px-4 py-2.5 last:border-b-0 target:bg-raised"
    >
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
