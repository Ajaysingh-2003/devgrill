import { getDebrief } from "@devgrill/api-client";
import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";
import { DEMO_DEBRIEF } from "@/components/debrief/demo";
import { LiveDebrief } from "@/components/debrief/live-debrief";
import { DEMO_ID } from "@/components/workspace/ids";
import { api, unwrap } from "@/lib/api";

export const metadata: Metadata = { title: "Debrief" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function generateStaticParams() {
  return [{ attemptId: DEMO_ID }];
}

async function Debrief({ params }: { params: PageProps<"/incident/[attemptId]/debrief">["params"] }) {
  const { attemptId } = await params;
  if (attemptId === DEMO_ID) return <LiveDebrief d={DEMO_DEBRIEF} />;
  if (!UUID.test(attemptId)) notFound();
  const result = await getDebrief({ client: await api(), path: { attempt_id: attemptId } });
  // Still running: the debrief opens when the incident ends.
  if (result.response?.status === 409) redirect(`/incident/${attemptId}`);
  return <LiveDebrief d={await unwrap(Promise.resolve(result))} />;
}

/** T6 Debrief: Field Manual layer plus the one celebration moment. */
export default function DebriefPage({ params }: PageProps<"/incident/[attemptId]/debrief">) {
  return (
    <Suspense fallback={<p className="p-6 text-body text-fg-muted">Loading your debrief…</p>}>
      <Debrief params={params} />
    </Suspense>
  );
}
