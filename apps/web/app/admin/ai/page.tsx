import type { Metadata } from "next";
import { Suspense } from "react";
import { adminMe } from "@devgrill/api-client";
import { AiSpend, ApproachQueue } from "@/components/admin/ai-console";
import { refusal } from "@/components/admin/forbidden";
import { PageSkeleton } from "@/components/page-skeleton";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "AI and fixes" };

async function Sections() {
  const { data, response } = await adminMe({ client: await api() });
  if (!data) return refusal(response, "This page");
  const can = new Set(data.permissions);
  if (!can.has("review_fixes")) return refusal(new Response(null, { status: 403 }), "This page");
  return (
    <>
      {can.has("view_costs") ? (
        <>
          <h2 className="text-heading-md font-semibold text-fg">AI spend</h2>
          <Suspense fallback={<PageSkeleton label="Loading AI spend" />}>
            <AiSpend />
          </Suspense>
        </>
      ) : null}
      <h2 className="mt-6 text-heading-md font-semibold text-fg">Unrecognised fixes</h2>
      <Suspense fallback={<PageSkeleton label="Loading unrecognised fixes" />}>
        <ApproachQueue />
      </Suspense>
    </>
  );
}

/** AI spend (admins) and the queue of fixes the classifier didn't recognise (reviewers). */
export default function AiPage() {
  return (
    <>
      <h1 className="text-heading-lg font-semibold tracking-tight text-fg">AI and fixes</h1>
      <Suspense fallback={<PageSkeleton label="Loading" />}>
        <Sections />
      </Suspense>
    </>
  );
}
