import type { Metadata } from "next";
import { Suspense } from "react";
import { Workspace } from "@/components/workspace/workspace";

export const metadata: Metadata = { title: "Incident" };

export function generateStaticParams() {
  return [{ attemptId: "inc-4021" }];
}

async function WorkspaceRoute({ params }: { params: PageProps<"/incident/[attemptId]">["params"] }) {
  const { attemptId } = await params;
  return <Workspace attemptId={attemptId} />;
}

/** T5 incident workspace (full-bleed; no app top bar). */
export default function IncidentPage({ params }: PageProps<"/incident/[attemptId]">) {
  return (
    <Suspense fallback={<p className="p-6 text-body text-fg-muted">Opening the incident…</p>}>
      <WorkspaceRoute params={params} />
    </Suspense>
  );
}
