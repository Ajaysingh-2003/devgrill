import type { Metadata } from "next";
import { Suspense } from "react";
import { getMe } from "@devgrill/api-client";
import { PageSkeleton } from "@/components/page-skeleton";
import { api, unwrap } from "@/lib/api";
import { requireSession } from "@/lib/auth";
import { safeNext } from "@/lib/safe-next";
import { OnboardingFlow } from "./onboarding-flow";

export const metadata: Metadata = { title: "Welcome" };

async function Onboarding({ searchParams }: { searchParams: PageProps<"/onboarding">["searchParams"] }) {
  const next = safeNext((await searchParams).next);
  await requireSession(`/onboarding?next=${encodeURIComponent(next)}`);
  const me = await unwrap(getMe({ client: await api() }));
  return (
    <OnboardingFlow
      next={next}
      name={me.display_name}
      experience={me.experience_level ?? null}
      role={me.prefs.job_role ?? null}
    />
  );
}

/** First sign-in: who you are, then an optional six-card calibration (PLAN §8.3). */
export default function OnboardingPage({ searchParams }: PageProps<"/onboarding">) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-8 py-4">
      <Suspense fallback={<PageSkeleton label="Loading" />}>
        <Onboarding searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
