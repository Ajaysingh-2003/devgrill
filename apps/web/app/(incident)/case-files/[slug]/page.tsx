import { getCaseFile } from "@devgrill/api-client";
import type { Metadata } from "next";
import { Suspense, cache } from "react";
import { CaseWorkspace } from "@/components/case-file/case-workspace";
import { api, unwrap } from "@/lib/api";

const loadCase = cache(async (slug: string) => unwrap(getCaseFile({ client: await api(), path: { slug } })));

export async function generateMetadata({ params }: PageProps<"/case-files/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  return { title: `${(await loadCase(slug)).title}: case file` };
}

async function CaseRoute({ params }: { params: PageProps<"/case-files/[slug]">["params"] }) {
  const { slug } = await params;
  return <CaseWorkspace file={await loadCase(slug)} />;
}

/** A case file (full-bleed, like an incident). The recording itself loads in the browser. */
export default function CaseFilePage({ params }: PageProps<"/case-files/[slug]">) {
  return (
    <Suspense fallback={<p className="p-6 text-body text-fg-muted">Opening the case file…</p>}>
      <CaseRoute params={params} />
    </Suspense>
  );
}
