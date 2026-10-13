import type { Metadata } from "next";
import { Suspense } from "react";
import { IncidentTimeline } from "@devgrill/ui/components/devgrill/incident-timeline";
import { IncidentPageHeader } from "@/components/incident-page-header";
import { TIMELINE } from "@/lib/mock";

export const metadata: Metadata = { title: "Postmortem" };

export function generateStaticParams() {
  return [{ attemptId: "inc-4021" }];
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
    hint: "What prevents this class of incident, with owners.",
    value: "",
  },
];

async function Editor({ params }: { params: PageProps<"/incident/[attemptId]/postmortem">["params"] }) {
  const { attemptId } = await params;
  return (
    <>
      <IncidentPageHeader
        context="Postmortem, The Big Sale Meltdown"
        back={{ href: `/incident/${attemptId}/debrief`, label: "Back to the debrief" }}
      />
      <main
        id="main"
        className="mx-auto grid max-w-[72rem] gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_20rem]"
      >
        <form className="flex max-w-[44rem] flex-col gap-8">
          <header className="flex flex-col gap-2">
            <h1 className="font-serif text-display-lg text-fg">
              Postmortem: product pages failed at sale start
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
            <IncidentTimeline events={TIMELINE} label="Incident timeline (read only)" />
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
