import { getPostmortem } from "@devgrill/api-client";
import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";
import { IncidentTimeline } from "@devgrill/ui/components/devgrill/incident-timeline";
import { IncidentPageHeader } from "@/components/incident-page-header";
import { PostmortemEditor } from "@/components/postmortem/editor";
import { DEMO_ID } from "@/components/workspace/ids";
import { api, unwrap } from "@/lib/api";
import { TIMELINE } from "@/lib/mock";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const metadata: Metadata = { title: "Write-up" };

export function generateStaticParams() {
  return [{ attemptId: "demo" }];
}

const SECTIONS = [
  {
    id: "summary",
    title: "Summary",
    hint: "Two or three sentences a director could read.",
    value: "Product pages failed for 8 minutes at the start of the sale.",
  },
  {
    id: "impact",
    title: "Impact",
    hint: "Who was affected, for how long, how badly.",
    value: "18% of product requests returned 502 between 20:00 and 20:08.",
  },
  { id: "cause", title: "Root cause", hint: "The change, the mechanism, and why it hurt now.", value: "" },
  {
    id: "actions",
    title: "Action items",
    hint: "What stops this kind of problem happening again, with owners.",
    value: "",
  },
];

async function Live({ attemptId }: { attemptId: string }) {
  if (!UUID.test(attemptId)) notFound();
  const result = await getPostmortem({ client: await api(), path: { attempt_id: attemptId } });
  // The write-up opens when the drill ends.
  if (result.response?.status === 409) redirect(`/incident/${attemptId}`);
  const doc = await unwrap(Promise.resolve(result));
  return (
    <>
      <IncidentPageHeader
        context={`Write-up, ${doc.scenario_title}`}
        back={{ href: `/incident/${attemptId}/debrief`, label: "Back to your results" }}
      />
      <main
        id="main"
        className="mx-auto grid max-w-[72rem] gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_20rem]"
      >
        <PostmortemEditor attemptId={attemptId} initial={doc} />
        <aside aria-labelledby="pm-timeline" className="flex flex-col gap-2 lg:sticky lg:top-6 lg:self-start">
          <h2 id="pm-timeline" className="text-body font-semibold text-fg">
            Timeline, from your session
          </h2>
          <p className="text-caption text-fg-muted">Added to your write-up when you submit it.</p>
          <ol className="flex flex-col rounded-md border border-border bg-surface">
            {doc.timeline.map((line, i) => {
              const [at, ...text] = line.split(" ");
              return (
                <li
                  key={i}
                  className="grid grid-cols-[3rem_1fr] gap-2 border-b border-border px-3 py-2 last:border-b-0"
                >
                  <span className="font-mono text-mono-sm text-fg-subtle">{at}</span>
                  <span className="text-label wrap-anywhere text-fg">{text.join(" ")}</span>
                </li>
              );
            })}
          </ol>
        </aside>
      </main>
    </>
  );
}

async function Editor({ params }: { params: PageProps<"/incident/[attemptId]/postmortem">["params"] }) {
  const { attemptId } = await params;
  if (attemptId !== DEMO_ID) return <Live attemptId={attemptId} />;
  return (
    <>
      <IncidentPageHeader
        context="Write-up, The Big Sale Meltdown"
        back={{ href: `/incident/${attemptId}/debrief`, label: "Back to your results" }}
      />
      <main
        id="main"
        className="mx-auto grid max-w-[72rem] gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_20rem]"
      >
        <form className="flex max-w-[44rem] flex-col gap-8">
          <header className="flex flex-col gap-2">
            <h1 className="font-serif text-display-lg text-fg">
              Write-up: product pages failed at sale start
            </h1>
            <p className="text-body-lg text-fg-muted">
              Blameless and specific. Describe what changed, not who changed it.
            </p>
          </header>
          {SECTIONS.map((s) => (
            <div key={s.id} className="flex flex-col gap-1.5">
              <label htmlFor={`pm-${s.id}`} className="text-heading-md font-semibold text-fg">
                {s.title}
              </label>
              <p id={`pm-${s.id}-hint`} className="text-label text-fg-muted">
                {s.hint}
              </p>
              <textarea
                id={`pm-${s.id}`}
                name={s.id}
                aria-describedby={`pm-${s.id}-hint`}
                rows={4}
                defaultValue={s.value}
                className="rounded-sm border border-border-input bg-surface px-3 py-2.5 text-body-lg text-fg placeholder:text-fg-subtle"
              />
            </div>
          ))}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              className="h-10 rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
            >
              Submit for review
            </button>
            <span className="text-label text-fg-subtle">Draft saved 20 seconds ago</span>
          </div>
        </form>
        <aside aria-labelledby="pm-timeline" className="flex flex-col gap-2 lg:sticky lg:top-6 lg:self-start">
          <h2 id="pm-timeline" className="text-body font-semibold text-fg">
            Timeline, from your session
          </h2>
          <div className="rounded-md border border-border bg-surface">
            <IncidentTimeline events={TIMELINE} label="Timeline (read only)" />
          </div>
        </aside>
      </main>
    </>
  );
}

/** T7 Postmortem editor (Field Manual). */
export default function PostmortemPage({ params }: PageProps<"/incident/[attemptId]/postmortem">) {
  return (
    <Suspense fallback={<p className="p-6 text-body text-fg-muted">Loading the editor…</p>}>
      <Editor params={params} />
    </Suspense>
  );
}
