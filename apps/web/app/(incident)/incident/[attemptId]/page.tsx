import { getWorkspace } from "@devgrill/api-client";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { DEMO_ID } from "@/components/workspace/ids";
import { DemoWorkspace, LiveWorkspace } from "@/components/workspace/entry";
import { api, unwrap } from "@/lib/api";

export const metadata: Metadata = { title: "Drill" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function WorkspaceRoute({
  params,
  searchParams,
}: {
  params: PageProps<"/incident/[attemptId]">["params"];
  searchParams: PageProps<"/incident/[attemptId]">["searchParams"];
}) {
  const { attemptId } = await params;
  // The demo also shows the guest tutorial's step-by-step tools (?tutorial=1), for its tests.
  if (attemptId === DEMO_ID) return <DemoWorkspace tutorial={(await searchParams).tutorial === "1"} />;
  if (!UUID.test(attemptId)) notFound();
  // Owned by the caller (user or guest), else 404: another player's incident doesn't exist.
  const info = await unwrap(getWorkspace({ client: await api(), path: { attempt_id: attemptId } }));
  return (
    <LiveWorkspace info={info} briefingHref={`/drills/${info.track_slug}/${info.attempt.scenario_slug}`} />
  );
}

/** T5 incident workspace (full-bleed; no app top bar). */
export default function IncidentPage({ params, searchParams }: PageProps<"/incident/[attemptId]">) {
  return (
    <Suspense fallback={<p className="p-6 text-body text-fg-muted">Opening the drill…</p>}>
      <WorkspaceRoute params={params} searchParams={searchParams} />
    </Suspense>
  );
}
